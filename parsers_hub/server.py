#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import select
import shutil
import signal
import subprocess
import threading
import time
import uuid
import unicodedata
import html
import csv
from base64 import b64decode
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urljoin, urlparse
from urllib.request import Request, urlopen
from zipfile import ZipFile
import xml.etree.ElementTree as ET

try:
    import psycopg2
except Exception:  # noqa: BLE001
    psycopg2 = None


def build_job_progress(
    *,
    status: str,
    parser_key: str,
    command: list[str] | None = None,
    payload: dict[str, Any] | None = None,
    log_text: str = "",
) -> dict[str, Any]:
    current, total = extract_progress_from_log(log_text)
    configured_total = extract_total_from_command(command or []) or extract_total_from_payload(payload or {})
    if total <= 0:
        total = configured_total
    if current <= 0 and status == "completed" and total > 0:
        current = total

    if status == "completed":
        percent = 100
    elif total > 0:
        percent = max(0, min(99, int((current / total) * 100)))
    elif status == "running":
        percent = 12
    else:
        percent = 0

    if status in {"failed", "stopped"} and total > 0:
        percent = max(0, min(100, int((current / total) * 100)))

    label = "Ожидание старта"
    if current and total:
        label = f"{current}/{total}"
    elif current:
        label = f"{current} записей"
    elif status == "completed":
        label = "Готово"
    elif status == "running":
        label = "Парсинг идет"
    elif status == "paused":
        label = "Пауза"
    elif status in {"failed", "stopped"}:
        label = "Остановлено"

    return {
        "current": current,
        "total": total,
        "percent": percent,
        "label": label,
        "indeterminate": status == "running" and total <= 0,
        "source": parser_key,
    }


def extract_progress_from_log(log_text: str) -> tuple[int, int]:
    current = 0
    total = 0
    explicit_current = 0
    explicit_total = 0
    has_explicit_progress = False
    for line in (log_text or "").splitlines():
        progress_match = re.search(r"\[progress\]\s+(\d+)\s*/\s*(\d+)", line, re.IGNORECASE)
        if progress_match:
            has_explicit_progress = True
            explicit_current = max(explicit_current, int(progress_match.group(1)))
            explicit_total = max(explicit_total, int(progress_match.group(2)))
            continue

        ratio_match = re.search(r"\[(\d+)\s*/\s*(\d+)\]", line)
        if ratio_match:
            current = max(current, int(ratio_match.group(1)))
            total = max(total, int(ratio_match.group(2)))
            continue

        gis_match = re.search(r"Парсинг\s+\[(\d+)\]", line)
        if gis_match:
            current = max(current, int(gis_match.group(1)))
            continue

        report_match = re.search(r"\[report\].*?\bprocessed=(\d+)", line)
        if report_match:
            current = max(current, int(report_match.group(1)))
            continue

        saved_match = re.search(r"Сохранено\s+(\d+)\s+объявлен", line, re.IGNORECASE)
        if saved_match:
            current = max(current, int(saved_match.group(1)))

    if has_explicit_progress:
        return explicit_current, explicit_total
    return current, total


def extract_total_from_command(command: list[str]) -> int:
    total_flags = {"--limit", "--listing-limit", "--max-records", "--parser.max-records"}
    for index, part in enumerate(command):
        if part in total_flags and index + 1 < len(command):
            try:
                return max(0, int(str(command[index + 1])))
            except (TypeError, ValueError):
                return 0
    return 0


def extract_total_from_payload(payload: dict[str, Any]) -> int:
    for key in ("limit", "listing_limit", "max_records"):
        value = payload.get(key)
        if value in (None, ""):
            continue
        try:
            return max(0, int(str(value)))
        except (TypeError, ValueError):
            continue
    return 0


def command_arg_value(command: list[str], flag: str) -> str:
    try:
        index = command.index(flag)
    except ValueError:
        return ""
    if index + 1 >= len(command):
        return ""
    return str(command[index + 1])


RUN_ID_RE = re.compile(r"\brun_id=([0-9a-fA-F-]{36})\b")


def extract_run_ids(text: str) -> list[str]:
    seen: set[str] = set()
    run_ids: list[str] = []
    for match in RUN_ID_RE.finditer(text or ""):
        run_id = match.group(1)
        if run_id in seen:
            continue
        seen.add(run_id)
        run_ids.append(run_id)
    return run_ids


def cleanup_2gis_unstable_attempt(command: list[str], attempt_log: str, database_url: str) -> tuple[int, int]:
    """Remove partial state from an auto-restart probe attempt.

    2GIS writes live DB rows and checkpoints before we know whether the start is
    stable. If we keep that state, the next attempt resumes from a bad probe and
    progress/DB counts become inflated. A failed probe must be disposable.
    """
    removed_files = 0
    output_value = command_arg_value(command, "--output")
    if output_value:
        output_path = Path(output_value)
        candidates = [
            output_path,
            output_path.with_suffix(output_path.suffix + ".checkpoint.json"),
            output_path.with_suffix(".csv"),
            output_path.with_suffix(".converted.xlsx"),
            output_path.with_suffix(".deduplicated.csv"),
            output_path.with_suffix(".col_cleaned.csv"),
        ]
        for path in candidates:
            try:
                if path.exists():
                    path.unlink()
                    removed_files += 1
            except OSError:
                pass

    deleted_runs = 0
    run_ids = extract_run_ids(attempt_log)
    if database_url and run_ids and psycopg2 is not None:
        try:
            with psycopg2.connect(database_url) as conn:
                with conn.cursor() as cur:
                    for run_id in run_ids:
                        cur.execute("DELETE FROM parser_runs WHERE run_id = %s::uuid", (run_id,))
                        deleted_runs += cur.rowcount
        except Exception:
            deleted_runs = 0

    return removed_files, deleted_runs


def is_clean_empty_2gis_result(process_return_code: int | None, attempt_log: str, parsed_count: int, error_count: int) -> bool:
    if process_return_code != 0 or parsed_count != 0 or error_count != 0:
        return False
    empty_markers = (
        "Точных совпадений нет",
        "Не найдено",
        "processed=0",
    )
    return any(marker in attempt_log for marker in empty_markers)


def _safe_slug(value: str, fallback: str = "default", max_len: int = 96) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", normalized).strip("._-").lower()
    return (slug or fallback)[:max_len].strip("._-") or fallback


def gis2_profile_key_from_command(command: list[str]) -> str:
    """Build a stable 2GIS profile key from domain and city.

    The profile should be reusable across rubrics in the same city, but not
    shared between cities/domains because 2GIS keeps city-scoped state.
    """
    search_url = command_arg_value(command, "--search-url")
    parsed = urlparse(search_url)
    host = parsed.netloc or "2gis"
    path_parts = [part for part in parsed.path.split("/") if part]
    city = path_parts[0] if path_parts else "default"
    return _safe_slug(f"{host}_{city}", fallback="2gis_default")


def _chrome_profile_ignore(_dir: str, names: list[str]) -> set[str]:
    volatile_names = {
        "BrowserMetrics",
        "Crashpad",
        "DevToolsActivePort",
        "DawnCache",
        "GraphiteDawnCache",
        "GrShaderCache",
        "GPUCache",
        "ShaderCache",
        "SingletonCookie",
        "SingletonLock",
        "SingletonSocket",
    }
    ignored = set()
    for name in names:
        if name in volatile_names or name.endswith(".tmp"):
            ignored.add(name)
    return ignored


def copy_chrome_profile(src: Path, dst: Path) -> bool:
    """Copy a Chrome profile without lock files and volatile browser caches."""
    if not src.exists() or not src.is_dir():
        return False
    tmp_dst = dst.with_name(f".{dst.name}.tmp-{uuid.uuid4().hex[:8]}")
    shutil.rmtree(tmp_dst, ignore_errors=True)
    try:
        shutil.copytree(src, tmp_dst, ignore=_chrome_profile_ignore, dirs_exist_ok=True)
        shutil.rmtree(dst, ignore_errors=True)
        tmp_dst.replace(dst)
        return True
    except Exception:
        shutil.rmtree(tmp_dst, ignore_errors=True)
        return False


def prepare_2gis_runtime_profile(runtime_profile_dir: Path, stable_profile_dir: Path | None) -> bool:
    """Reset a job profile and seed it from the last stable profile if present."""
    shutil.rmtree(runtime_profile_dir, ignore_errors=True)
    runtime_profile_dir.mkdir(parents=True, exist_ok=True)
    if stable_profile_dir and copy_chrome_profile(stable_profile_dir, runtime_profile_dir):
        return True
    return False


def save_2gis_stable_profile(
    runtime_profile_dir: Path,
    stable_profile_dir: Path,
    metadata: dict[str, Any],
) -> bool:
    stable_profile_dir.parent.mkdir(parents=True, exist_ok=True)
    if not copy_chrome_profile(runtime_profile_dir, stable_profile_dir):
        return False
    meta_path = stable_profile_dir.parent / "metadata.json"
    meta_payload = {
        **metadata,
        "saved_at": utc_now(),
        "profile_dir": str(stable_profile_dir),
    }
    meta_path.write_text(json.dumps(meta_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def invalidate_2gis_stable_profile(stable_profile_dir: Path, reason: str) -> bool:
    if not stable_profile_dir.exists():
        return False
    stamp = timestamp_slug()
    bad_dir = stable_profile_dir.with_name(f"{stable_profile_dir.name}_bad_{stamp}")
    try:
        stable_profile_dir.replace(bad_dir)
        meta_path = stable_profile_dir.parent / "metadata.json"
        meta_payload = {
            "invalidated_at": utc_now(),
            "reason": reason,
            "bad_profile_dir": str(bad_dir),
        }
        meta_path.write_text(json.dumps(meta_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


ROOT_DIR = Path(__file__).resolve().parent
STATIC_DIR = ROOT_DIR / "static"
RUNS_DIR = ROOT_DIR / "runs"
RECOVERY_DIR = RUNS_DIR / "_recovery"
PROJECT_ROOT_RAW = os.environ.get("PARSERS_PROJECT_ROOT", "").strip()
OLX_DIR = Path(PROJECT_ROOT_RAW).resolve() if PROJECT_ROOT_RAW else ROOT_DIR.parent.resolve()
UNIFIED_SOURCES_DIR = OLX_DIR / "unified_sources"
GIS_DIR = UNIFIED_SOURCES_DIR / "2gis"
KRISHA_DIR = UNIFIED_SOURCES_DIR / "krisha"
DEFAULT_PYTHON_BIN = Path(os.environ.get("PARSERS_PYTHON_BIN", "").strip() or str(OLX_DIR / "venv/bin/python"))
DEFAULT_DATABASE_URL = os.environ.get("PARSERS_HUB_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/parsers")
DEFAULT_HEADLESS = os.environ.get("PARSERS_DEFAULT_HEADLESS", "true").strip().lower() in {"1", "true", "yes", "on"}
PARSERS_AGENT_TOKEN = os.environ.get("PARSERS_AGENT_TOKEN", "").strip()
GIS_RUBRICS_XLSX = OLX_DIR / "Data.2gis_рубрики.xlsx"
GIS_CITIES_JSON = GIS_DIR / "parser_2gis/data/cities.json"
_RUBRICS_CACHE: dict[str, Any] | None = None
_RUBRICS_CACHE_MTIME: float | None = None
_GIS_CITIES_CACHE: dict[str, Any] | None = None
_GIS_CITIES_CACHE_MTIME: float | None = None
OLX_SITEMAP_URL = "https://www.olx.kz/sitemap/"
_OLX_CATEGORIES_CACHE: dict[str, Any] | None = None
_OLX_CATEGORIES_CACHE_AT: float = 0.0
_OLX_CATEGORIES_CACHE_TTL_SEC = 1800
_OLX_FORBIDDEN_L1 = {"sitemap", "kk", "mobileapps", "popular"}
_OLX_ALLOWED_L1 = {
    "detskiy-mir",
    "dom-i-sad",
    "elektronika",
    "hobbi-otdyh-i-sport",
    "moda-i-stil",
    "nedvizhimost",
    "otdam-darom",
    "prokat-tovarov",
    "rabota",
    "stroitelstvo-remont",
    "transport",
    "uslugi",
    "zapchasti",
    "zhivotnye",
}


def resolve_python_bin(source_dir: Path) -> str:
    source_venv = source_dir / ".venv/bin/python"
    if source_venv.exists():
        return str(source_venv)
    return str(DEFAULT_PYTHON_BIN)


@dataclass
class Job:
    job_id: str
    parser_key: str
    command: list[str]
    cwd: str
    output_path: str
    created_at: str
    status: str = "queued"
    return_code: int | None = None
    started_at: str | None = None
    finished_at: str | None = None
    log_lines: list[str] = field(default_factory=list)
    process: subprocess.Popen[str] | None = None
    stop_requested: bool = False
    snapshots: list[str] = field(default_factory=list)
    last_snapshot_at: str | None = None

    def snapshot(self) -> dict[str, Any]:
        log_text = "".join(self.log_lines[-400:])
        return {
            "job_id": self.job_id,
            "parser_key": self.parser_key,
            "command": self.command,
            "cwd": self.cwd,
            "output_path": self.output_path,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "return_code": self.return_code,
            "stop_requested": self.stop_requested,
            "snapshots": self.snapshots[-30:],
            "last_snapshot_at": self.last_snapshot_at,
            "log": log_text,
            "progress": build_job_progress(
                status=self.status,
                parser_key=self.parser_key,
                command=self.command,
                log_text=log_text,
            ),
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = [job.snapshot() for job in self._jobs.values()]
        return sorted(jobs, key=lambda item: item["created_at"], reverse=True)

    def get_job(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def create_job(self, parser_key: str, command: list[str], cwd: Path, output_path: Path) -> Job:
        now = utc_now()
        job = Job(
            job_id=uuid.uuid4().hex[:12],
            parser_key=parser_key,
            command=command,
            cwd=str(cwd),
            output_path=str(output_path),
            created_at=now,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        thread = threading.Thread(target=self._run_job, args=(job.job_id,), daemon=True)
        thread.start()
        return job

    def restart_job(self, job_id: str) -> Job | None:
        with self._lock:
            source = self._jobs.get(job_id)
            if not source:
                return None
            if source.status in {"running", "paused", "queued"}:
                return None
            command = list(source.command)
            cwd = Path(source.cwd)
            old_output = Path(source.output_path)
            new_output = self._make_restarted_output_path(old_output)
            command = self._replace_output_in_command(command, old_output, new_output)
            parser_key = source.parser_key

        return self.create_job(parser_key, command, cwd, new_output)

    def stop_job(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            job.stop_requested = True
            process = job.process
        if process and process.poll() is None:
            self._terminate_process_group(process)
        return job

    def pause_job(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status != "running" or not job.process:
                return None
            process = job.process
        if process.poll() is not None:
            return None
        if not self._pause_process_group(process):
            return None
        with self._lock:
            job.status = "paused"
            job.log_lines.append("[hub] Job paused by user.\n")
        return job

    def resume_job(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status != "paused" or not job.process:
                return None
            process = job.process
        if process.poll() is not None:
            return None
        if not self._resume_process_group(process):
            return None
        with self._lock:
            job.status = "running"
            job.log_lines.append("[hub] Job resumed by user.\n")
        return job

    def save_job_snapshot(self, job_id: str, reason: str = "manual") -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            output_path = Path(job.output_path)
            parser_key = job.parser_key
            log_text = "".join(job.log_lines[-1200:])
        snapshot_info = self._persist_snapshot_artifacts(output_path, parser_key, log_text, reason, job_id)
        with self._lock:
            artifact = snapshot_info["file_path"] or snapshot_info["log_path"]
            if artifact:
                job.snapshots.append(artifact)
            job.last_snapshot_at = snapshot_info["saved_at"]
        return snapshot_info

    def _append_log(self, job: Job, line: str) -> None:
        with self._lock:
            job.log_lines.append(line)
            if len(job.log_lines) > 2000:
                job.log_lines = job.log_lines[-2000:]

    def _run_job(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if not job:
            return

        with self._lock:
            job.status = "running"
            job.started_at = utc_now()

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        runtime_profile_dir: Path | None = None
        stable_profile_dir: Path | None = None
        stable_profile_key = ""
        stable_profile_seeded = False
        stable_profile_disabled = False
        stable_profile_should_save = False
        if job.parser_key == "2gis":
            stable_profile_key = gis2_profile_key_from_command(job.command)
            runtime_profile_dir = RUNS_DIR / "_chrome_profiles" / "2gis" / job.job_id
            stable_profile_dir = RUNS_DIR / "_chrome_profiles" / "2gis_stable" / stable_profile_key / "profile"
            env["PARSER_2GIS_CHROME_PROFILE_DIR"] = str(runtime_profile_dir)

        auto_enabled = (
            job.parser_key == "2gis"
            and env.get("PARSERS_HUB_2GIS_AUTO_RESTART", "true").strip().lower() in {"1", "true", "yes", "on"}
        )
        configured_total = extract_total_from_command(job.command)
        default_probe_seconds = 20 if configured_total >= 100 else 14
        default_min_records = 2
        if configured_total >= 300:
            default_min_records = 5
        elif configured_total >= 100:
            default_min_records = 4
        elif configured_total >= 50:
            default_min_records = 3
        default_confirm_records = max(
            default_min_records,
            8 if configured_total >= 300 else 6 if configured_total >= 100 else 4 if configured_total >= 50 else 3,
        )

        auto_max_attempts = max(30, int(env.get("PARSERS_HUB_2GIS_AUTO_MAX_ATTEMPTS", "30")))
        auto_probe_seconds = max(6, int(env.get("PARSERS_HUB_2GIS_AUTO_PROBE_SECONDS", str(default_probe_seconds))))
        auto_first_deadline = max(1.0, float(env.get("PARSERS_HUB_2GIS_AUTO_FIRST_PARSE_DEADLINE", "9")))
        auto_min_records = max(1, int(env.get("PARSERS_HUB_2GIS_AUTO_MIN_RECORDS", str(default_min_records))))
        auto_confirm_records = max(
            auto_min_records,
            int(env.get("PARSERS_HUB_2GIS_AUTO_CONFIRM_RECORDS", str(default_confirm_records))),
        )
        auto_stable_hold_seconds = max(0.0, float(env.get("PARSERS_HUB_2GIS_AUTO_STABLE_HOLD_SECONDS", "4")))
        auto_error_budget = max(0, int(env.get("PARSERS_HUB_2GIS_AUTO_ERROR_BUDGET", "0")))
        job_database_url = command_arg_value(job.command, "--database-url") or DEFAULT_DATABASE_URL

        process: subprocess.Popen[str] | None = None
        attempt = 0
        while True:
            attempt += 1
            if runtime_profile_dir is not None:
                use_stable_profile = stable_profile_dir is not None and not stable_profile_disabled
                stable_profile_seeded = prepare_2gis_runtime_profile(
                    runtime_profile_dir,
                    stable_profile_dir if use_stable_profile else None,
                )
                profile_source = "stable" if stable_profile_seeded else "clean"
                self._append_log(
                    job,
                    f"[profile] 2GIS key={stable_profile_key}, source={profile_source}, "
                    f"runtime={runtime_profile_dir}\n",
                )
            try:
                process = subprocess.Popen(
                    job.command,
                    cwd=job.cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=env,
                    preexec_fn=os.setsid,
                )
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    job.status = "failed"
                    job.finished_at = utc_now()
                    job.return_code = -1
                    job.log_lines.append(f"Failed to start process: {exc}\n")
                return

            with self._lock:
                job.process = process

            if not auto_enabled:
                break

            self._append_log(job, f"[auto] Попытка запуска {attempt}/{auto_max_attempts}\n")
            assert process.stdout is not None
            parsed_count = 0
            error_count = 0
            first_parse_delay: float | None = None
            last_parse_at: float | None = None
            stable_seen = False
            stable_reason = ""
            probe_start = time.monotonic()
            attempt_lines: list[str] = []

            def record_probe_line(line: str) -> None:
                nonlocal parsed_count, error_count, first_parse_delay, last_parse_at
                attempt_lines.append(line)
                self._append_log(job, line)
                if "Парсинг [" in line:
                    parsed_count += 1
                    last_parse_at = time.monotonic()
                    if first_parse_delay is None:
                        first_parse_delay = last_parse_at - probe_start
                if "Данные не получены" in line or "ERROR" in line:
                    error_count += 1

            def has_stable_probe(now: float) -> bool:
                if (
                    first_parse_delay is None
                    or first_parse_delay > auto_first_deadline
                    or parsed_count < auto_min_records
                    or error_count > auto_error_budget
                ):
                    return False
                if parsed_count >= auto_confirm_records:
                    return True
                if last_parse_at is not None and now - last_parse_at >= auto_stable_hold_seconds:
                    return True
                return False

            while time.monotonic() - probe_start < auto_probe_seconds:
                if job.stop_requested:
                    break
                if has_stable_probe(time.monotonic()):
                    stable_seen = True
                    stable_reason = "confirmed-records" if parsed_count >= auto_confirm_records else "quiet-window"
                    break
                if process.poll() is not None:
                    for remaining_line in process.stdout:
                        record_probe_line(remaining_line)
                    break
                ready, _, _ = select.select([process.stdout], [], [], 0.5)
                if not ready:
                    continue
                line = process.stdout.readline()
                if not line:
                    break
                record_probe_line(line)
                if has_stable_probe(time.monotonic()):
                    stable_seen = True
                    stable_reason = "confirmed-records" if parsed_count >= auto_confirm_records else "quiet-window"
                    break

            elapsed = max(0.001, time.monotonic() - probe_start)
            rps = parsed_count / elapsed
            process_return_code = process.poll()
            attempt_log = "".join(attempt_lines)
            clean_empty_result = is_clean_empty_2gis_result(
                process_return_code,
                attempt_log,
                parsed_count,
                error_count,
            )
            clean_finished_result = (
                process_return_code == 0
                and error_count <= auto_error_budget
                and ("Парсинг завершён" in attempt_log or "[report]" in attempt_log)
            )
            stable = (
                stable_seen
                or has_stable_probe(time.monotonic())
            )
            if stable and not stable_reason:
                stable_reason = "confirmed-records" if parsed_count >= auto_confirm_records else "quiet-window"
            self._append_log(
                job,
                f"[auto] Итог попытки {attempt}: records={parsed_count}, "
                f"first={round(first_parse_delay, 2) if first_parse_delay is not None else 'none'}s, "
                f"rps={round(rps, 2)}, errors={error_count}, min_records={auto_min_records}, "
                f"confirm_records={auto_confirm_records}, hold={auto_stable_hold_seconds:g}s"
                f"{', stable=' + stable_reason if stable_reason else ''}\n",
            )

            if job.stop_requested:
                break
            if clean_empty_result:
                self._append_log(
                    job,
                    "[auto] 2GIS вернул пустую выдачу, не перезапускаю этот запрос.\n",
                )
                break
            if clean_finished_result:
                self._append_log(job, "[auto] 2GIS завершил короткий запуск без ошибок.\n")
                break
            if stable:
                self._append_log(job, f"[auto] Стабильный старт найден на попытке {attempt}.\n")
                stable_profile_should_save = runtime_profile_dir is not None and stable_profile_dir is not None
                break
            if attempt >= auto_max_attempts:
                self._append_log(job, "[auto] Лимит попыток исчерпан, продолжаю последний запуск.\n")
                break

            self._append_log(job, "[auto] Нестабильный старт, перезапуск.\n")
            self._terminate_process_group(process)
            process.wait(timeout=10)
            removed_files, deleted_runs = cleanup_2gis_unstable_attempt(
                job.command,
                attempt_log,
                job_database_url,
            )
            if removed_files or deleted_runs:
                self._append_log(
                    job,
                    f"[auto] Очищена неудачная попытка: files={removed_files}, db_runs={deleted_runs}.\n",
                )
            if stable_profile_seeded and stable_profile_dir is not None:
                if invalidate_2gis_stable_profile(stable_profile_dir, "unstable-start"):
                    self._append_log(
                        job,
                        f"[profile] Сохранённый профиль 2GIS key={stable_profile_key} дал нестабильный старт; "
                        "пересобираю профиль заново.\n",
                    )
                stable_profile_disabled = True
            with self._lock:
                if job.process is process:
                    job.process = None
            time.sleep(1)

        assert process is not None
        assert process.stdout is not None
        for line in process.stdout:
            self._append_log(job, line)

        return_code = process.wait()
        with self._lock:
            job.process = None
            job.return_code = return_code
            job.finished_at = utc_now()
            if job.stop_requested:
                job.status = "stopped"
            elif return_code == 0:
                job.status = "completed"
            else:
                job.status = "failed"

        if (
            stable_profile_should_save
            and return_code == 0
            and not job.stop_requested
            and runtime_profile_dir is not None
            and stable_profile_dir is not None
        ):
            log_text = "".join(job.log_lines[-2000:])
            fatal_markers = (
                "Ошибка во время работы парсера.",
                "Вкладка браузера была закрыта.",
                "Работа парсера прервана пользователем.",
            )
            if not any(marker in log_text for marker in fatal_markers):
                saved = save_2gis_stable_profile(
                    runtime_profile_dir,
                    stable_profile_dir,
                    {
                        "key": stable_profile_key,
                        "job_id": job.job_id,
                        "command": job.command,
                        "return_code": return_code,
                    },
                )
                if saved:
                    self._append_log(
                        job,
                        f"[profile] Стабильный профиль 2GIS сохранён: key={stable_profile_key}, "
                        f"path={stable_profile_dir}\n",
                    )
                else:
                    self._append_log(
                        job,
                        f"[profile] Не удалось сохранить стабильный профиль 2GIS: key={stable_profile_key}\n",
                    )

        if return_code != 0:
            reason = "interrupted" if job.stop_requested else "error"
            snapshot_info = self.save_job_snapshot(job.job_id, reason=reason)
            if snapshot_info:
                extra = snapshot_info.get("file_path") or snapshot_info.get("log_path")
                if extra:
                    self._append_log(job, f"[hub] Recovery snapshot ({reason}) saved: {extra}\n")

    def _persist_snapshot_artifacts(
        self,
        output_path: Path,
        parser_key: str,
        log_text: str,
        reason: str,
        job_id: str,
    ) -> dict[str, str]:
        target_dir = RECOVERY_DIR / parser_key
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = timestamp_slug()
        file_snapshot = ""
        if output_path.exists() and output_path.is_file() and output_path.stat().st_size > 0:
            suffix = output_path.suffix or ".dat"
            safe_name = f"{output_path.stem}_{reason}_{stamp}{suffix}"
            dst = target_dir / safe_name
            shutil.copy2(output_path, dst)
            file_snapshot = str(dst)

        log_snapshot = target_dir / f"{output_path.stem}_{reason}_{stamp}.log.txt"
        log_snapshot.write_text(log_text or "No logs captured yet.\n", encoding="utf-8")

        return {
            "saved_at": utc_now(),
            "file_path": file_snapshot,
            "log_path": str(log_snapshot),
            "reason": reason,
            "job_id": job_id,
        }

    @staticmethod
    def _make_restarted_output_path(output_path: Path) -> Path:
        stamp = timestamp_slug()
        return output_path.with_name(f"{output_path.stem}_restart_{stamp}{output_path.suffix}")

    @staticmethod
    def _replace_output_in_command(command: list[str], old_output: Path, new_output: Path) -> list[str]:
        patched = list(command)
        old_out = str(old_output)
        flags = {"-o", "--output", "--output-path"}
        for idx, token in enumerate(patched):
            if token in flags and idx + 1 < len(patched):
                patched[idx + 1] = str(new_output)
                return patched
            if token == old_out:
                patched[idx] = str(new_output)
                return patched
        patched.append(str(new_output))
        return patched

    @staticmethod
    def _terminate_process_group(process: subprocess.Popen[str]) -> None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except Exception:  # noqa: BLE001
            process.terminate()

    @staticmethod
    def _pause_process_group(process: subprocess.Popen[str]) -> bool:
        try:
            os.killpg(process.pid, signal.SIGSTOP)
            return True
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _resume_process_group(process: subprocess.Popen[str]) -> bool:
        try:
            os.killpg(process.pid, signal.SIGCONT)
            return True
        except Exception:  # noqa: BLE001
            return False


JOB_MANAGER = JobManager()


@dataclass
class AgentJob:
    job_id: str
    parser_key: str
    payload: dict[str, Any]
    created_at: str
    status: str = "queued"
    return_code: int | None = None
    started_at: str | None = None
    finished_at: str | None = None
    output_path: str = ""
    cwd: str = "agent://remote"
    command: list[str] = field(default_factory=list)
    log_lines: list[str] = field(default_factory=list)
    agent_id: str = ""
    error: str = ""
    stop_requested: bool = False
    snapshots: list[str] = field(default_factory=list)
    last_snapshot_at: str | None = None

    def snapshot(self) -> dict[str, Any]:
        log_text = "".join(self.log_lines[-400:])
        return {
            "job_id": self.job_id,
            "parser_key": self.parser_key,
            "command": self.command,
            "cwd": self.cwd,
            "output_path": self.output_path,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "return_code": self.return_code,
            "stop_requested": self.stop_requested,
            "snapshots": self.snapshots[-30:],
            "last_snapshot_at": self.last_snapshot_at,
            "log": log_text,
            "agent_id": self.agent_id,
            "error": self.error,
            "progress": build_job_progress(
                status=self.status,
                parser_key=self.parser_key,
                command=self.command,
                payload=self.payload,
                log_text=log_text,
            ),
        }


class AgentJobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, AgentJob] = {}
        self._lock = threading.Lock()

    def create_job(self, parser_key: str, payload: dict[str, Any]) -> AgentJob:
        job = AgentJob(
            job_id=f"ag_{uuid.uuid4().hex[:10]}",
            parser_key=parser_key,
            payload=payload,
            created_at=utc_now(),
            command=["agent://2gis", payload.get("search_url", "")],
        )
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = [job.snapshot() for job in self._jobs.values()]
        return sorted(jobs, key=lambda item: item["created_at"], reverse=True)

    def get_job(self, job_id: str) -> AgentJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def stop_job(self, job_id: str) -> AgentJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            if job.status in {"completed", "failed", "stopped"}:
                return None
            job.stop_requested = True
            if job.status == "queued":
                job.status = "stopped"
                job.finished_at = utc_now()
            return job

    def claim_next(self, agent_id: str) -> AgentJob | None:
        with self._lock:
            for job in sorted(self._jobs.values(), key=lambda item: item.created_at):
                if job.status != "queued":
                    continue
                if job.stop_requested:
                    job.status = "stopped"
                    job.finished_at = utc_now()
                    continue
                job.status = "running"
                job.started_at = utc_now()
                job.agent_id = agent_id
                job.log_lines.append(f"[agent] Claimed by {agent_id}\n")
                return job
        return None

    def append_log(self, job_id: str, agent_id: str, lines: list[str]) -> AgentJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.agent_id != agent_id:
                return None
            for line in lines:
                job.log_lines.append(str(line))
            if len(job.log_lines) > 2000:
                job.log_lines = job.log_lines[-2000:]
            return job

    def complete_job(
        self,
        job_id: str,
        agent_id: str,
        return_code: int,
        output_name: str,
        output_b64: str,
        logs: list[str] | None = None,
        error: str = "",
    ) -> AgentJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.agent_id != agent_id:
                return None
            if logs:
                for line in logs:
                    job.log_lines.append(str(line))
            if len(job.log_lines) > 2000:
                job.log_lines = job.log_lines[-2000:]

        saved_path = ""
        if output_b64:
            try:
                raw = b64decode(output_b64.encode("utf-8"), validate=True)
                out_dir = ensure_runs_dir(job.parser_key)
                safe_name = output_name.strip() or f"{job.job_id}_data.bin"
                safe_name = safe_name.replace("/", "_")
                dst = out_dir / safe_name
                dst.write_bytes(raw)
                saved_path = str(dst)
            except Exception:
                error = error or "Failed to decode output file from agent."

        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            job.return_code = int(return_code)
            job.finished_at = utc_now()
            if saved_path:
                job.output_path = saved_path
            job.error = error
            if job.stop_requested:
                job.status = "stopped"
            elif return_code == 0 and not error:
                job.status = "completed"
            else:
                job.status = "failed"
            if error:
                job.log_lines.append(f"[agent] ERROR: {error}\n")
            return job


AGENT_JOB_MANAGER = AgentJobManager()


@dataclass
class ExportJob:
    job_id: str
    created_at: str
    status: str = "queued"
    format: str = "xlsx"
    file_name: str = ""
    output_path: str = ""
    filters: dict[str, Any] = field(default_factory=dict)
    fields: list[str] = field(default_factory=list)
    total_rows: int = 0
    exported_rows: int = 0
    progress: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    error: str = ""
    stop_requested: bool = False

    def snapshot(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "format": self.format,
            "file_name": self.file_name,
            "output_path": self.output_path,
            "filters": self.filters,
            "fields": self.fields,
            "total_rows": self.total_rows,
            "exported_rows": self.exported_rows,
            "progress": self.progress,
            "error": self.error,
            "stop_requested": self.stop_requested,
        }


def _sanitize_excel_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text)


def _excel_col_name(index: int) -> str:
    n = index + 1
    result = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def _write_xlsx(path: Path, headers: list[str], rows: list[dict[str, Any]], fields: list[str]) -> None:
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
    workbook = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Export" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""
    styles = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="1"><fill><patternFill patternType="none"/></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
</styleSheet>"""

    def row_to_xml(row_idx: int, values: list[Any]) -> str:
        cells: list[str] = []
        for col_idx, value in enumerate(values):
            cell_ref = f"{_excel_col_name(col_idx)}{row_idx}"
            text = html.escape(_sanitize_excel_text(value))
            cells.append(f'<c r="{cell_ref}" t="inlineStr"><is><t>{text}</t></is></c>')
        return f'<row r="{row_idx}">{"".join(cells)}</row>'

    sheet_rows: list[str] = [row_to_xml(1, headers)]
    row_number = 2
    for item in rows:
        sheet_rows.append(row_to_xml(row_number, [_field_value(item, field) for field in fields]))
        row_number += 1

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData>'
        "</worksheet>"
    )

    with ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/styles.xml", styles)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)


class ExportJobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, ExportJob] = {}
        self._lock = threading.Lock()

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = [job.snapshot() for job in self._jobs.values()]
        return sorted(jobs, key=lambda item: item["created_at"], reverse=True)

    def get_job(self, job_id: str) -> ExportJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def create_job(self, payload: dict[str, Any]) -> ExportJob:
        fmt = str(payload.get("format", "xlsx")).strip().lower()
        if fmt not in {"xlsx", "csv"}:
            raise ValueError("Поддерживаемые форматы: xlsx, csv")
        requested_fields = payload.get("fields", [])
        if not isinstance(requested_fields, list):
            raise ValueError("fields должен быть списком")
        fields: list[str] = []
        for raw_field in requested_fields:
            field = str(raw_field).strip()
            if not field:
                continue
            if field in EXPORT_FIELD_KEYS:
                fields.append(field)
                continue
            if field.startswith("payload.") and re.fullmatch(r"payload\.[A-Za-z0-9_]+", field):
                fields.append(field)
        if not fields:
            fields = [item["key"] for item in EXPORT_FIELDS]

        file_name = str(payload.get("file_name", "")).strip()
        if file_name and not file_name.endswith(f".{fmt}"):
            file_name = f"{file_name}.{fmt}"
        if not file_name:
            file_name = f"db_export_{timestamp_slug()}.{fmt}"

        filters = payload.get("filters", {})
        if not isinstance(filters, dict):
            filters = {}
        source = str(filters.get("source", "")).strip().lower()
        run_status = str(filters.get("run_status", "")).strip().lower()
        has_phone = str(filters.get("has_phone", "")).strip().lower()
        search = str(filters.get("search", "")).strip()
        date_from = str(filters.get("date_from", "")).strip()
        date_to = str(filters.get("date_to", "")).strip()
        database_url = str(filters.get("database_url", "")).strip() or DEFAULT_DATABASE_URL
        max_rows = parse_int(str(filters.get("max_rows", "50000")), default=50000, min_value=1, max_value=500000)

        job = ExportJob(
            job_id=f"exp_{uuid.uuid4().hex[:10]}",
            created_at=utc_now(),
            format=fmt,
            file_name=file_name,
            filters={
                "source": source,
                "run_status": run_status,
                "has_phone": has_phone,
                "search": search,
                "date_from": date_from,
                "date_to": date_to,
                "database_url": database_url,
                "max_rows": max_rows,
            },
            fields=fields,
        )
        with self._lock:
            self._jobs[job.job_id] = job

        thread = threading.Thread(target=self._run_job, args=(job.job_id,), daemon=True)
        thread.start()
        return job

    def stop_job(self, job_id: str) -> ExportJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            if job.status in {"completed", "failed", "stopped"}:
                return None
            job.stop_requested = True
            return job

    def _run_job(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if not job:
            return
        with self._lock:
            job.status = "running"
            job.started_at = utc_now()
            job.progress = 1

        if psycopg2 is None:
            with self._lock:
                job.status = "failed"
                job.error = "psycopg2 is not installed."
                job.finished_at = utc_now()
            return

        output_dir = ensure_runs_dir("exports")
        output_path = output_dir / job.file_name
        filters = dict(job.filters)
        where_sql, where_values = _build_db_where(filters)

        try:
            with psycopg2.connect(filters["database_url"]) as conn:
                total = _count_db_rows(conn, where_sql, where_values)
                max_rows = int(filters.get("max_rows", 50000))
                target_rows = min(total, max_rows)
                with self._lock:
                    job.total_rows = target_rows

                selected_fields = list(job.fields)
                headers = [_field_label(field) for field in selected_fields]

                offset = 0
                batch_size = 1000
                all_rows: list[dict[str, Any]] = []

                while offset < target_rows:
                    if job.stop_requested:
                        with self._lock:
                            job.status = "stopped"
                            job.finished_at = utc_now()
                            job.progress = 100 if job.total_rows == 0 else int((job.exported_rows / max(job.total_rows, 1)) * 100)
                        return
                    chunk = _fetch_db_rows(conn, where_sql, where_values, min(batch_size, target_rows - offset), offset)
                    if not chunk:
                        break
                    all_rows.extend(chunk)
                    offset += len(chunk)
                    with self._lock:
                        job.exported_rows = len(all_rows)
                        if job.total_rows > 0:
                            job.progress = min(99, int((job.exported_rows / job.total_rows) * 100))
                        else:
                            job.progress = 99

                if job.format == "csv":
                    with output_path.open("w", newline="", encoding="utf-8-sig") as file_obj:
                        writer = csv.writer(file_obj)
                        writer.writerow(headers)
                        for row in all_rows:
                            writer.writerow([_field_value(row, field) for field in selected_fields])
                else:
                    _write_xlsx(output_path, headers, all_rows, selected_fields)

            with self._lock:
                job.output_path = str(output_path)
                job.progress = 100
                job.status = "completed"
                job.finished_at = utc_now()
                job.exported_rows = len(all_rows)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                job.status = "failed"
                job.error = str(exc)
                job.finished_at = utc_now()


EXPORT_JOB_MANAGER = ExportJobManager()


def utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def ensure_runs_dir(parser_key: str) -> Path:
    path = RUNS_DIR / parser_key
    path.mkdir(parents=True, exist_ok=True)
    return path


def timestamp_slug() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def parser_definitions() -> dict[str, Any]:
    return {
        "olx": {
            "title": "OLX.kz",
            "description": "Категорийный парсер OLX с записью объявлений и телефонов продавцов в PostgreSQL.",
            "output_ext": "json",
            "fields": [
                {"name": "olx_category_selector", "label": "Категории OLX (3 уровня)", "type": "olx_category_selector", "required": False, "default": ""},
                {"name": "category_url", "label": "Ссылка на категорию", "type": "url", "required": True, "default": "https://www.olx.kz/elektronika/"},
                {"name": "limit", "label": "Лимит объявлений", "type": "number", "required": True, "default": 10},
                {"name": "output_name", "label": "Имя файла", "type": "text", "required": False, "default": ""},
                {"name": "database_url", "label": "PostgreSQL URL", "type": "text", "required": False, "default": DEFAULT_DATABASE_URL},
            ],
        },
        "2gis": {
            "title": "2GIS",
            "description": "Поисковый парсер 2GIS с запуском Chrome и записью данных в PostgreSQL.",
            "output_ext": "json",
            "fields": [
                {"name": "search_url", "label": "Ссылка поиска 2GIS", "type": "url", "required": True, "default": "https://2gis.ru/almaty/search/аптека"},
                {"name": "rubric_selector", "label": "Рубрики (3 уровня)", "type": "2gis_rubric_selector", "required": False, "default": ""},
                {"name": "max_records", "label": "Максимум записей", "type": "number", "required": True, "default": 100},
                {"name": "delay_between_clicks", "label": "Задержка между кликами (мс)", "type": "number", "required": False, "default": 800},
                {"name": "output_name", "label": "Имя файла", "type": "text", "required": False, "default": ""},
                {"name": "format", "label": "Формат", "type": "select", "required": True, "default": "xlsx", "options": ["xlsx", "csv", "json"]},
                {"name": "start_maximized", "label": "Стартовать окно развёрнутым", "type": "checkbox", "required": False, "default": False},
                {"name": "run_via_agent", "label": "Запускать через mini-агент (ПК пользователя)", "type": "checkbox", "required": False, "default": False},
                {"name": "database_url", "label": "PostgreSQL URL", "type": "text", "required": False, "default": DEFAULT_DATABASE_URL},
            ],
        },
        "krisha": {
            "title": "Krisha.kz",
            "description": "Сбор телефонов с Krisha по странице листинга или одному объявлению с записью в PostgreSQL.",
            "output_ext": "json",
            "fields": [
                {"name": "krisha_location_selector", "label": "Регион Krisha (область / город / район)", "type": "krisha_location_selector", "required": False, "default": ""},
                {"name": "listing_url", "label": "Ссылка на листинг", "type": "url", "required": True, "default": "https://krisha.kz/prodazha/kvartiry/"},
                {"name": "deal_type", "label": "Сделка", "type": "select", "required": False, "default": "prodazha", "options": ["prodazha", "arenda"]},
                {"name": "property_type", "label": "Тип недвижимости", "type": "select", "required": False, "default": "kvartiry", "options": ["kvartiry", "doma-dachi", "garazhi", "uchastkov", "kommercheskaya-nedvizhimost", "biznes", "prombazy", "zarubezhnoj-nedvizhimosti"]},
                {"name": "rooms", "label": "Комнаты", "type": "select", "required": False, "default": "", "options": ["", "1", "2", "3", "4", "5+"]},
                {"name": "price_from", "label": "Цена от, ₸", "type": "number", "required": False, "default": ""},
                {"name": "price_to", "label": "Цена до, ₸", "type": "number", "required": False, "default": ""},
                {"name": "has_photo", "label": "Есть фото", "type": "checkbox", "required": False, "default": False},
                {"name": "new_buildings", "label": "Новостройки", "type": "checkbox", "required": False, "default": False},
                {"name": "from_owner", "label": "От хозяев", "type": "checkbox", "required": False, "default": False},
                {"name": "from_agent", "label": "От Крыша Агентов", "type": "checkbox", "required": False, "default": False},
                {"name": "listing_limit", "label": "Лимит объявлений", "type": "number", "required": True, "default": 10},
                {"name": "output_name", "label": "Имя файла", "type": "text", "required": False, "default": "result_random.json"},
                {"name": "driver", "label": "Режим", "type": "select", "required": True, "default": "selenium", "options": ["selenium", "http"]},
                {"name": "browser", "label": "Браузер", "type": "select", "required": True, "default": "chrome", "options": ["chrome", "safari"]},
                {"name": "no_proxy", "label": "Без proxy", "type": "checkbox", "required": False, "default": True},
                {"name": "headless", "label": "Headless режим", "type": "checkbox", "required": False, "default": DEFAULT_HEADLESS},
                {"name": "cookie_file", "label": "Файл cookie", "type": "text", "required": False, "default": ""},
                {"name": "account_login", "label": "Логин аккаунта", "type": "text", "required": False, "default": ""},
                {"name": "account_password", "label": "Пароль аккаунта", "type": "password", "required": False, "default": ""},
                {"name": "database_url", "label": "PostgreSQL URL", "type": "text", "required": False, "default": DEFAULT_DATABASE_URL},
            ],
        },
        "kolesa": {
            "title": "Kolesa.kz",
            "description": "Сбор телефонов с Kolesa по листингу автомобилей с записью результатов в PostgreSQL.",
            "output_ext": "json",
            "fields": [
                {"name": "listing_url", "label": "Ссылка на листинг", "type": "url", "required": True, "default": "https://kolesa.kz/cars/"},
                {"name": "listing_limit", "label": "Лимит объявлений", "type": "number", "required": True, "default": 10},
                {"name": "output_name", "label": "Имя файла", "type": "text", "required": False, "default": "kolesa_results.json"},
                {"name": "driver", "label": "Режим листинга", "type": "select", "required": True, "default": "http", "options": ["http", "selenium"]},
                {"name": "no_proxy", "label": "Без proxy", "type": "checkbox", "required": False, "default": True},
                {"name": "headless", "label": "Headless режим Selenium", "type": "checkbox", "required": False, "default": DEFAULT_HEADLESS},
                {"name": "verify_ssl", "label": "Проверять SSL Kolesa API", "type": "checkbox", "required": False, "default": os.environ.get("KOLESA_VERIFY_SSL", "false").strip().lower() in {"1", "true", "yes", "on"}},
                {"name": "database_url", "label": "PostgreSQL URL", "type": "text", "required": False, "default": DEFAULT_DATABASE_URL},
            ],
        },
    }


def normalize_output_name(raw_name: str, fallback_prefix: str, ext: str) -> str:
    base_name = raw_name.strip() or f"{fallback_prefix}_{timestamp_slug()}.{ext}"
    if not base_name.endswith(f".{ext}"):
        base_name += f".{ext}"
    return base_name


def build_olx_command(payload: dict[str, Any]) -> tuple[list[str], Path, Path]:
    output_dir = ensure_runs_dir("olx")
    output_name = normalize_output_name(payload.get("output_name", ""), "olx", "json")
    output_path = output_dir / output_name
    data_output_path = output_dir / f"{output_path.stem}_data_{timestamp_slug()}.xlsx"
    database_url = payload.get("database_url", "").strip()
    command = [
        resolve_python_bin(OLX_DIR),
        "parser_hub.py",
        "run",
        "olx",
        "--category-url",
        payload["category_url"].strip(),
        "--limit",
        str(int(payload["limit"])),
        "--output",
        str(data_output_path),
        "--output-target",
        "db",
        "--report-json",
        str(output_path),
    ]
    if database_url:
        command.extend(["--database-url", database_url])
    return command, OLX_DIR, output_path


def build_2gis_command(payload: dict[str, Any]) -> tuple[list[str], Path, Path]:
    fmt = payload.get("format", "xlsx")
    output_dir = ensure_runs_dir("2gis")
    output_name = normalize_output_name(payload.get("output_name", ""), "2gis", "json")
    output_path = output_dir / output_name
    data_output_path = output_dir / f"{output_path.stem}_data_{timestamp_slug()}.{fmt}"
    database_url = payload.get("database_url", "").strip()
    command = [
        resolve_python_bin(OLX_DIR),
        "parser_hub.py",
        "run",
        "2gis",
        "--search-url",
        payload["search_url"].strip(),
        "--max-records",
        str(int(payload["max_records"])),
        "--delay-between-clicks",
        str(max(0, int(payload.get("delay_between_clicks", 800)))),
        "--format",
        fmt,
        "--output",
        str(data_output_path),
        "--output-target",
        "db",
        "--report-json",
        str(output_path),
    ]
    if payload.get("start_maximized", True):
        command.append("--start-maximized")
    else:
        command.append("--no-start-maximized")
    if database_url:
        command.extend(["--database-url", database_url])
    return command, OLX_DIR, output_path


def build_krisha_command(payload: dict[str, Any]) -> tuple[list[str], Path, Path]:
    output_dir = ensure_runs_dir("krisha")
    output_name = normalize_output_name(payload.get("output_name", ""), "krisha", "json")
    output_path = output_dir / output_name
    data_output_path = output_dir / f"{output_path.stem}_data_{timestamp_slug()}.csv"
    checkpoint_path = data_output_path.with_suffix(data_output_path.suffix + ".checkpoint.json")
    database_url = payload.get("database_url", "").strip()
    command = [
        resolve_python_bin(OLX_DIR),
        "parser_hub.py",
        "run",
        "krisha",
        "--driver",
        payload.get("driver", "selenium"),
        "--browser",
        payload.get("browser", "chrome"),
        "--listing-url",
        payload["listing_url"].strip(),
        "--listing-limit",
        str(int(payload["listing_limit"])),
        "--delay",
        "0.7",
        "--random-delay-min",
        "1.2",
        "--random-delay-max",
        "3.5",
        "--output",
        str(data_output_path),
        "--output-target",
        "db",
        "--report-json",
        str(output_path),
    ]
    for payload_key, flag, default_value in (
        ("deal_type", "--deal-type", "prodazha"),
        ("property_type", "--property-type", "kvartiry"),
        ("rooms", "--rooms", ""),
        ("price_from", "--price-from", ""),
        ("price_to", "--price-to", ""),
    ):
        value = str(payload.get(payload_key, "")).strip()
        if value and value != default_value:
            command.extend([flag, value])
    if payload.get("has_photo", False):
        command.append("--has-photo")
    if payload.get("new_buildings", False):
        command.append("--new-buildings")
    if payload.get("from_owner", False):
        command.append("--from-owner")
    if payload.get("from_agent", False):
        command.append("--from-agent")
    if payload.get("no_proxy", True):
        command.append("--no-proxy")
    if payload.get("headless", False):
        command.append("--headless")
    else:
        command.append("--no-headless")

    cookie_file = payload.get("cookie_file", "").strip()
    if cookie_file:
        command.extend(["--cookie-file", cookie_file])
    account_login = payload.get("account_login", "").strip()
    if account_login:
        command.extend(["--account-login", account_login])
    account_password = payload.get("account_password", "")
    if account_password:
        command.extend(["--account-password", account_password])
    if database_url:
        command.extend(["--database-url", database_url])

    return command, OLX_DIR, output_path


def build_kolesa_command(payload: dict[str, Any]) -> tuple[list[str], Path, Path]:
    output_dir = ensure_runs_dir("kolesa")
    output_name = normalize_output_name(payload.get("output_name", ""), "kolesa", "json")
    output_path = output_dir / output_name
    data_output_path = output_dir / f"{output_path.stem}_data_{timestamp_slug()}.csv"
    database_url = payload.get("database_url", "").strip()
    command = [
        resolve_python_bin(OLX_DIR),
        "parser_hub.py",
        "run",
        "kolesa",
        "--driver",
        payload.get("driver", "http"),
        "--listing-url",
        payload["listing_url"].strip(),
        "--listing-limit",
        str(int(payload["listing_limit"])),
        "--delay",
        "0.7",
        "--random-delay-min",
        "1.2",
        "--random-delay-max",
        "3.5",
        "--output",
        str(data_output_path),
        "--output-target",
        "db",
        "--report-json",
        str(output_path),
    ]
    if payload.get("no_proxy", True):
        command.append("--no-proxy")
    else:
        command.extend(["--proxies-file", str(OLX_DIR / "proxyscrape_premium_http_proxies.txt")])
    if payload.get("headless", False):
        command.append("--headless")
    else:
        command.append("--no-headless")
    if payload.get("verify_ssl", False):
        command.append("--verify-ssl")
    else:
        command.append("--insecure-ssl")
    if database_url:
        command.extend(["--database-url", database_url])
    return command, OLX_DIR, output_path


COMMAND_BUILDERS = {
    "olx": build_olx_command,
    "2gis": build_2gis_command,
    "krisha": build_krisha_command,
    "kolesa": build_kolesa_command,
}


def parse_int(value: str | None, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, parsed))


EXPORT_FIELDS: list[dict[str, str]] = [
    {"key": "created_at", "label": "Время"},
    {"key": "source", "label": "Источник"},
    {"key": "run_id", "label": "Run ID"},
    {"key": "external_id", "label": "External ID"},
    {"key": "title", "label": "Title / Name"},
    {"key": "phone", "label": "Phone"},
    {"key": "price", "label": "Price"},
    {"key": "location", "label": "Location"},
    {"key": "run_status", "label": "Run Status"},
    {"key": "record_status", "label": "Record Status"},
    {"key": "error", "label": "Error"},
    {"key": "url", "label": "URL"},
]
EXPORT_FIELD_KEYS = {field["key"] for field in EXPORT_FIELDS}
KNOWN_SOURCES = {"olx", "krisha", "kolesa", "2gis"}


def _field_label(field: str) -> str:
    base_map = {item["key"]: item["label"] for item in EXPORT_FIELDS}
    if field in base_map:
        return base_map[field]
    if field.startswith("payload."):
        return field.split(".", 1)[1]
    return field


def _field_value(row: dict[str, Any], field: str) -> Any:
    if field.startswith("payload."):
        key = field.split(".", 1)[1]
        payload = row.get("payload", {})
        if isinstance(payload, dict):
            return payload.get(key, "")
        return ""
    return row.get(field, "")


def _load_export_fields(database_url: str, source: str) -> list[dict[str, str]]:
    src = (source or "").strip().lower()
    if src and src not in KNOWN_SOURCES:
        raise ValueError("Некорректный source")
    fields = [dict(item) for item in EXPORT_FIELDS]
    if psycopg2 is None:
        return fields

    sql = (
        "SELECT DISTINCT key "
        "FROM parser_records r "
        "CROSS JOIN LATERAL jsonb_object_keys(COALESCE(r.payload, '{}'::jsonb)) AS key "
        "WHERE (%s = '' OR r.source = %s) "
        "ORDER BY key "
        "LIMIT 500"
    )
    with psycopg2.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, [src, src])
            keys = [str(row[0]) for row in cur.fetchall() if row and row[0]]

    for key in keys:
        if not re.fullmatch(r"[A-Za-z0-9_]+", key):
            continue
        fields.append({"key": f"payload.{key}", "label": key})
    return fields


def _parse_iso_dt(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _extract_db_filters(params: dict[str, list[str]]) -> dict[str, Any]:
    return {
        "source": (params.get("source", [""])[0] or "").strip().lower(),
        "run_status": (params.get("run_status", [""])[0] or "").strip().lower(),
        "has_phone": (params.get("has_phone", [""])[0] or "").strip().lower(),
        "search": (params.get("search", [""])[0] or "").strip(),
        "date_from": (params.get("date_from", [""])[0] or "").strip(),
        "date_to": (params.get("date_to", [""])[0] or "").strip(),
        "database_url": (params.get("database_url", [""])[0] or "").strip() or DEFAULT_DATABASE_URL,
        "limit": parse_int((params.get("limit") or [None])[0], default=100, min_value=1, max_value=500),
        "page": parse_int((params.get("page") or [None])[0], default=1, min_value=1, max_value=10_000),
    }


def _build_db_where(filters: dict[str, Any]) -> tuple[str, list[Any]]:
    where_parts: list[str] = []
    where_values: list[Any] = []

    source = filters.get("source", "")
    if source:
        where_parts.append("r.source = %s")
        where_values.append(source)

    run_status = filters.get("run_status", "")
    if run_status:
        where_parts.append("COALESCE(runs.status, '') = %s")
        where_values.append(run_status)

    has_phone = filters.get("has_phone", "")
    if has_phone == "yes":
        where_parts.append(
            """COALESCE(
                r.payload->>'seller_phone',
                r.payload->>'phones',
                r.payload->>'phone_1',
                ''
            ) <> ''"""
        )
    elif has_phone == "no":
        where_parts.append(
            """COALESCE(
                r.payload->>'seller_phone',
                r.payload->>'phones',
                r.payload->>'phone_1',
                ''
            ) = ''"""
        )

    search = filters.get("search", "")
    if search:
        like = f"%{search}%"
        where_parts.append("(r.external_id ILIKE %s OR r.run_id::text ILIKE %s OR r.payload::text ILIKE %s)")
        where_values.extend([like, like, like])

    date_from = _parse_iso_dt(filters.get("date_from", ""))
    if filters.get("date_from", "") and date_from is None:
        raise ValueError("Некорректный формат date_from")
    if date_from is not None:
        where_parts.append("r.created_at >= %s")
        where_values.append(date_from)

    date_to = _parse_iso_dt(filters.get("date_to", ""))
    if filters.get("date_to", "") and date_to is None:
        raise ValueError("Некорректный формат date_to")
    if date_to is not None:
        where_parts.append("r.created_at <= %s")
        where_values.append(date_to)

    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    return where_sql, where_values


def _count_db_rows(conn: Any, where_sql: str, where_values: list[Any]) -> int:
    count_sql = (
        "SELECT COUNT(*) "
        "FROM parser_records r "
        "LEFT JOIN parser_runs runs ON runs.run_id = r.run_id "
        f"{where_sql}"
    )
    with conn.cursor() as cur:
        cur.execute(count_sql, where_values)
        return int(cur.fetchone()[0])


def _fetch_db_rows(conn: Any, where_sql: str, where_values: list[Any], limit: int, offset: int) -> list[dict[str, Any]]:
    rows_sql = (
        "SELECT "
        "r.id, "
        "r.run_id::text, "
        "r.source, "
        "r.external_id, "
        "r.created_at, "
        "COALESCE(runs.status, '') AS run_status, "
        "COALESCE(r.payload->>'title', r.payload->>'name', '') AS title, "
        "COALESCE(r.payload->>'seller_phone', r.payload->>'phones', r.payload->>'phone_1', '') AS phone, "
        "COALESCE(r.payload->>'price', '') AS price, "
        "COALESCE(r.payload->>'location', r.payload->>'city', r.payload->>'address', '') AS location, "
        "COALESCE(r.payload->>'source_url', r.payload->>'ad_url', r.payload->>'url', '') AS url, "
        "COALESCE(r.payload->>'status', '') AS record_status, "
        "COALESCE(r.payload->>'error', '') AS error, "
        "r.payload "
        "FROM parser_records r "
        "LEFT JOIN parser_runs runs ON runs.run_id = r.run_id "
        f"{where_sql} "
        "ORDER BY r.created_at DESC "
        "LIMIT %s OFFSET %s"
    )
    with conn.cursor() as cur:
        cur.execute(rows_sql, [*where_values, limit, offset])
        fetched = cur.fetchall()

    records: list[dict[str, Any]] = []
    for row in fetched:
        created_at = row[4].isoformat() if row[4] else ""
        payload = row[13] if isinstance(row[13], dict) else {}
        records.append(
            {
                "id": row[0],
                "run_id": row[1],
                "source": row[2],
                "external_id": row[3],
                "created_at": created_at,
                "run_status": row[5],
                "title": row[6],
                "phone": row[7],
                "price": row[8],
                "location": row[9],
                "url": row[10],
                "record_status": row[11],
                "error": row[12],
                "payload": payload,
            }
        )
    return records


def query_db_records(params: dict[str, list[str]]) -> dict[str, Any]:
    if psycopg2 is None:
        raise RuntimeError("psycopg2 is not installed in current Python environment.")
    filters = _extract_db_filters(params)
    limit = int(filters["limit"])
    page = int(filters["page"])
    offset = (page - 1) * limit
    database_url = str(filters["database_url"])
    where_sql, where_values = _build_db_where(filters)

    with psycopg2.connect(database_url) as conn:
        total = _count_db_rows(conn, where_sql, where_values)
        records = _fetch_db_rows(conn, where_sql, where_values, limit, offset)

    return {
        "filters": {
            "source": filters["source"],
            "run_status": filters["run_status"],
            "has_phone": filters["has_phone"],
            "search": filters["search"],
            "date_from": filters["date_from"],
            "date_to": filters["date_to"],
            "limit": limit,
            "page": page,
        },
        "total": total,
        "pages": max(1, (total + limit - 1) // limit),
        "records": records,
    }


def validate_payload(parser_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    definitions = parser_definitions()
    parser_info = definitions.get(parser_key)
    if not parser_info:
        raise ValueError("Unknown parser")

    cleaned: dict[str, Any] = {}
    for field in parser_info["fields"]:
        name = field["name"]
        value = payload.get(name, field.get("default"))
        field_type = field["type"]
        if field_type == "number":
            if value in ("", None):
                if field.get("required"):
                    raise ValueError(f"Поле '{field['label']}' обязательно")
                cleaned[name] = ""
                continue
            try:
                cleaned[name] = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Поле '{field['label']}' должно быть числом") from exc
        elif field_type == "checkbox":
            cleaned[name] = bool(value)
        elif field_type in {"2gis_rubric_selector", "olx_category_selector"}:
            cleaned[name] = "" if value is None else str(value)
        else:
            cleaned[name] = "" if value is None else str(value)

        if field.get("required") and field_type != "checkbox" and str(cleaned[name]).strip() == "":
            raise ValueError(f"Поле '{field['label']}' обязательно")
    return cleaned


def _load_2gis_rubrics_tree() -> dict[str, Any]:
    if not GIS_RUBRICS_XLSX.exists():
        raise FileNotFoundError(f"Rubrics file not found: {GIS_RUBRICS_XLSX}")

    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    shared_strings: list[str] = []
    nested: dict[str, dict[str, list[str]]] = {}

    with ZipFile(GIS_RUBRICS_XLSX) as archive:
        if "xl/sharedStrings.xml" in archive.namelist():
            sst_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for si in sst_root.findall("m:si", ns):
                text = "".join((t.text or "") for t in si.findall(".//m:t", ns)).strip()
                shared_strings.append(text)

        sheet_root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        rows = sheet_root.findall(".//m:sheetData/m:row", ns)

        for idx, row in enumerate(rows):
            if idx == 0:
                continue
            values: list[str] = []
            for cell in row.findall("m:c", ns):
                value_node = cell.find("m:v", ns)
                raw = value_node.text if value_node is not None else ""
                if cell.attrib.get("t") == "s" and raw:
                    try:
                        text = shared_strings[int(raw)]
                    except Exception:
                        text = ""
                else:
                    text = raw or ""
                values.append(text.strip())

            if len(values) < 3:
                continue
            level1, level2, rubric = values[0], values[1], values[2]
            if not level1 or not level2 or not rubric:
                continue

            level2_map = nested.setdefault(level1, {})
            rubrics = level2_map.setdefault(level2, [])
            if rubric not in rubrics:
                rubrics.append(rubric)

    level1_items: list[dict[str, Any]] = []
    for level1_name in sorted(nested.keys(), key=lambda x: x.lower()):
        level2_map = nested[level1_name]
        level2_items: list[dict[str, Any]] = []
        for level2_name in sorted(level2_map.keys(), key=lambda x: x.lower()):
            rubrics = sorted(level2_map[level2_name], key=lambda x: x.lower())
            level2_items.append({"name": level2_name, "rubrics": rubrics})
        level1_items.append({"name": level1_name, "level2": level2_items})

    total_rubrics = sum(len(level2["rubrics"]) for lvl1 in level1_items for level2 in lvl1["level2"])
    return {
        "updated_at": utc_now(),
        "source_file": str(GIS_RUBRICS_XLSX),
        "level1": level1_items,
        "stats": {"level1_count": len(level1_items), "rubrics_count": total_rubrics},
    }


def get_2gis_rubrics_tree() -> dict[str, Any]:
    global _RUBRICS_CACHE, _RUBRICS_CACHE_MTIME
    mtime = GIS_RUBRICS_XLSX.stat().st_mtime if GIS_RUBRICS_XLSX.exists() else None
    if _RUBRICS_CACHE is None or _RUBRICS_CACHE_MTIME != mtime:
        _RUBRICS_CACHE = _load_2gis_rubrics_tree()
        _RUBRICS_CACHE_MTIME = mtime
    return _RUBRICS_CACHE


def _load_2gis_cities() -> dict[str, Any]:
    if not GIS_CITIES_JSON.exists():
        raise FileNotFoundError(f"2GIS cities file not found: {GIS_CITIES_JSON}")

    with GIS_CITIES_JSON.open("r", encoding="utf-8") as fh:
        raw_items = json.load(fh)

    cities: list[dict[str, str]] = []
    for item in raw_items if isinstance(raw_items, list) else []:
        name = str(item.get("name", "")).strip()
        code = str(item.get("code", "")).strip()
        domain = str(item.get("domain", "")).strip().lower()
        country_code = str(item.get("country_code", "")).strip().lower()
        if not (name and code and domain):
            continue
        # 2GIS still accepts /astana/ in the public URL; keep that familiar slug in the hub UI.
        if domain == "kz" and code == "nur_sultan":
            code = "astana"
        cities.append({"name": name, "code": code, "domain": domain, "country_code": country_code})

    cities.sort(key=lambda x: (x["domain"] != "kz", x["domain"], x["name"].lower()))
    domains = sorted({item["domain"] for item in cities})
    return {
        "updated_at": utc_now(),
        "source_file": str(GIS_CITIES_JSON),
        "cities": cities,
        "domains": domains,
        "stats": {"city_count": len(cities), "domain_count": len(domains)},
    }


def get_2gis_cities() -> dict[str, Any]:
    global _GIS_CITIES_CACHE, _GIS_CITIES_CACHE_MTIME
    mtime = GIS_CITIES_JSON.stat().st_mtime if GIS_CITIES_JSON.exists() else None
    if _GIS_CITIES_CACHE is None or _GIS_CITIES_CACHE_MTIME != mtime:
        _GIS_CITIES_CACHE = _load_2gis_cities()
        _GIS_CITIES_CACHE_MTIME = mtime
    return _GIS_CITIES_CACHE


class _OlxSitemapAnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_map = dict(attrs)
        href = attrs_map.get("href")
        if href:
            self._href = href
            self._chunks = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a":
            return
        if self._href is None:
            return
        text = html.unescape(" ".join(self._chunks)).strip()
        if self._href:
            self.links.append((self._href, text))
        self._href = None
        self._chunks = []


def _slug_to_title(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.split("-") if part)


def _clean_category_text(raw: str) -> str:
    text = re.sub(r"\(\s*[\d\s\xa0]+\s*\)$", "", raw or "").strip()
    text = re.sub(r"\.css-[\w\-]+\{[^}]*\}", "", text)
    if "{" in text or "}" in text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _extract_olx_path_parts(href: str) -> tuple[str, ...] | None:
    parsed = urlparse(urljoin(OLX_SITEMAP_URL, href))
    if parsed.netloc and parsed.netloc not in {"www.olx.kz", "olx.kz"}:
        return None
    path = parsed.path or ""
    parts = [segment for segment in path.split("/") if segment]
    if not parts or len(parts) > 3:
        return None
    if any(not re.fullmatch(r"[a-z0-9\-]+", segment) for segment in parts):
        return None
    if parts[0] in _OLX_FORBIDDEN_L1:
        return None
    if parts[0] not in _OLX_ALLOWED_L1:
        return None
    return tuple(parts)


def _fetch_olx_categories_tree() -> dict[str, Any]:
    request = Request(
        OLX_SITEMAP_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            )
        },
    )
    with urlopen(request, timeout=30) as response:
        html_text = response.read().decode("utf-8", errors="replace")

    parser = _OlxSitemapAnchorParser()
    parser.feed(html_text)

    tree: dict[str, Any] = {}

    for href, raw_text in parser.links:
        parts = _extract_olx_path_parts(href)
        if not parts:
            continue
        text = _clean_category_text(raw_text)
        l1 = parts[0]
        l1_node = tree.setdefault(
            l1,
            {
                "slug": l1,
                "name": text or _slug_to_title(l1),
                "url": f"https://www.olx.kz/{l1}/",
                "level2": {},
            },
        )
        if len(parts) == 1:
            if text:
                l1_node["name"] = text
            continue

        l2 = parts[1]
        l2_map = l1_node["level2"]
        l2_node = l2_map.setdefault(
            l2,
            {
                "slug": l2,
                "name": text or _slug_to_title(l2),
                "url": f"https://www.olx.kz/{l1}/{l2}/",
                "level3": {},
            },
        )
        if len(parts) == 2:
            if text:
                l2_node["name"] = text
            continue

        l3 = parts[2]
        l3_map = l2_node["level3"]
        l3_node = l3_map.setdefault(
            l3,
            {
                "slug": l3,
                "name": text or _slug_to_title(l3),
                "url": f"https://www.olx.kz/{l1}/{l2}/{l3}/",
            },
        )
        if text:
            l3_node["name"] = text

    level1_items: list[dict[str, Any]] = []
    for l1_slug, l1_node in tree.items():
        level2_items: list[dict[str, Any]] = []
        for _, l2_node in l1_node["level2"].items():
            level3_items = sorted(l2_node["level3"].values(), key=lambda item: item["name"].lower())
            level2_items.append(
                {
                    "slug": l2_node["slug"],
                    "name": l2_node["name"],
                    "url": l2_node["url"],
                    "level3": level3_items,
                }
            )
        level2_items.sort(key=lambda item: item["name"].lower())
        level1_items.append(
            {
                "slug": l1_node["slug"],
                "name": l1_node["name"],
                "url": l1_node["url"],
                "level2": level2_items,
            }
        )

    level1_items.sort(key=lambda item: item["name"].lower())
    level2_count = sum(len(item["level2"]) for item in level1_items)
    level3_count = sum(len(item2["level3"]) for item1 in level1_items for item2 in item1["level2"])

    return {
        "source_url": OLX_SITEMAP_URL,
        "updated_at": utc_now(),
        "level1": level1_items,
        "stats": {
            "level1_count": len(level1_items),
            "level2_count": level2_count,
            "level3_count": level3_count,
        },
    }


def get_olx_categories_tree() -> dict[str, Any]:
    global _OLX_CATEGORIES_CACHE, _OLX_CATEGORIES_CACHE_AT
    now_ts = datetime.now().timestamp()
    if _OLX_CATEGORIES_CACHE and (now_ts - _OLX_CATEGORIES_CACHE_AT) < _OLX_CATEGORIES_CACHE_TTL_SEC:
        return _OLX_CATEGORIES_CACHE
    _OLX_CATEGORIES_CACHE = _fetch_olx_categories_tree()
    _OLX_CATEGORIES_CACHE_AT = now_ts
    return _OLX_CATEGORIES_CACHE


class AppHandler(BaseHTTPRequestHandler):
    server_version = "ParsersHub/1.0"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/config":
            self._send_json({"parsers": parser_definitions()})
            return
        if parsed.path == "/api/2gis/rubrics":
            try:
                self._send_json(get_2gis_rubrics_tree())
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": f"Failed to load 2GIS rubrics: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/2gis/cities":
            try:
                self._send_json(get_2gis_cities())
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": f"Failed to load 2GIS cities: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/olx/categories":
            try:
                self._send_json(get_olx_categories_tree())
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": f"Failed to load OLX categories: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/db/records":
            try:
                result = query_db_records(parse_qs(parsed.query))
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": f"DB query failed: {exc}"}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(result)
            return
        if parsed.path == "/api/db/export/config":
            query = parse_qs(parsed.query)
            source = (query.get("source", [""])[0] or "").strip().lower()
            database_url = (query.get("database_url", [""])[0] or "").strip() or DEFAULT_DATABASE_URL
            try:
                fields = _load_export_fields(database_url=database_url, source=source)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": f"Failed to load export fields: {exc}"}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"fields": fields, "formats": ["xlsx", "csv"], "source": source})
            return
        if parsed.path == "/api/db/exports":
            self._send_json({"jobs": EXPORT_JOB_MANAGER.list_jobs()})
            return
        if parsed.path.startswith("/api/db/exports/"):
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 4:
                job_id = parts[3]
                job = EXPORT_JOB_MANAGER.get_job(job_id)
                if not job:
                    self._send_json({"error": "Export job not found"}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_json({"job": job.snapshot()})
                return
            if len(parts) == 5 and parts[4] == "download":
                job_id = parts[3]
                job = EXPORT_JOB_MANAGER.get_job(job_id)
                if not job or not job.output_path:
                    self._send_json({"error": "Export file not found"}, status=HTTPStatus.NOT_FOUND)
                    return
                export_path = Path(job.output_path)
                if not export_path.exists():
                    self._send_json({"error": "Export file not found"}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_file(export_path, download_name=job.file_name)
                return
        if parsed.path == "/api/jobs":
            jobs = JOB_MANAGER.list_jobs() + AGENT_JOB_MANAGER.list_jobs()
            jobs_sorted = sorted(jobs, key=lambda item: item["created_at"], reverse=True)
            self._send_json({"jobs": jobs_sorted})
            return
        if parsed.path.startswith("/api/jobs/"):
            job_id = parsed.path.rsplit("/", 1)[-1]
            job = JOB_MANAGER.get_job(job_id)
            if not job:
                agent_job = AGENT_JOB_MANAGER.get_job(job_id)
                if not agent_job:
                    self._send_json({"error": "Job not found"}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_json(agent_job.snapshot())
                return
            self._send_json(job.snapshot())
            return
        self._serve_static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/db/export":
            payload = self._read_json()
            if payload is None:
                return
            try:
                job = EXPORT_JOB_MANAGER.create_job(payload)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"job": job.snapshot()}, status=HTTPStatus.CREATED)
            return

        if parsed.path.startswith("/api/db/exports/") and parsed.path.endswith("/stop"):
            parts = parsed.path.strip("/").split("/")
            if len(parts) != 5:
                self._send_json({"error": "Bad request"}, status=HTTPStatus.BAD_REQUEST)
                return
            job_id = parts[3]
            job = EXPORT_JOB_MANAGER.stop_job(job_id)
            if not job:
                self._send_json({"error": "Export job not found or not stoppable"}, status=HTTPStatus.NOT_FOUND)
                return
            self._send_json({"job": job.snapshot()})
            return

        if parsed.path == "/api/run":
            payload = self._read_json()
            if payload is None:
                return
            parser_key = payload.get("parser_key")
            form_data = payload.get("payload", {})
            try:
                cleaned = validate_payload(parser_key, form_data)
                if parser_key == "2gis" and cleaned.get("run_via_agent", False):
                    job = AGENT_JOB_MANAGER.create_job(parser_key, cleaned)
                    self._send_json({"job": job.snapshot()}, status=HTTPStatus.CREATED)
                    return
                command, cwd, output_path = COMMAND_BUILDERS[parser_key](cleaned)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            job = JOB_MANAGER.create_job(parser_key, command, cwd, output_path)
            self._send_json({"job": job.snapshot()}, status=HTTPStatus.CREATED)
            return

        if parsed.path == "/api/agent/next":
            payload = self._read_json()
            if payload is None:
                return
            if not self._validate_agent_token(payload):
                self._send_json({"error": "Forbidden"}, status=HTTPStatus.FORBIDDEN)
                return
            agent_id = str(payload.get("agent_id", "")).strip() or "agent"
            job = AGENT_JOB_MANAGER.claim_next(agent_id)
            if not job:
                self._send_json({"job": None})
                return
            self._send_json(
                {
                    "job": {
                        "job_id": job.job_id,
                        "parser_key": job.parser_key,
                        "payload": job.payload,
                        "created_at": job.created_at,
                    }
                }
            )
            return

        if parsed.path.startswith("/api/agent/jobs/"):
            payload = self._read_json()
            if payload is None:
                return
            if not self._validate_agent_token(payload):
                self._send_json({"error": "Forbidden"}, status=HTTPStatus.FORBIDDEN)
                return
            parts = parsed.path.strip("/").split("/")
            if len(parts) != 5:
                self._send_json({"error": "Bad request"}, status=HTTPStatus.BAD_REQUEST)
                return
            job_id = parts[3]
            action = parts[4]
            agent_id = str(payload.get("agent_id", "")).strip() or "agent"

            if action == "log":
                lines = payload.get("lines", [])
                if not isinstance(lines, list):
                    lines = [str(lines)]
                job = AGENT_JOB_MANAGER.append_log(job_id, agent_id, [str(x) for x in lines])
                if not job:
                    self._send_json({"error": "Job not found"}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_json({"ok": True})
                return

            if action == "complete":
                return_code = int(payload.get("return_code", 1))
                output_name = str(payload.get("output_name", "")).strip()
                output_b64 = str(payload.get("output_b64", "")).strip()
                logs = payload.get("logs", [])
                if not isinstance(logs, list):
                    logs = []
                error = str(payload.get("error", "")).strip()
                job = AGENT_JOB_MANAGER.complete_job(
                    job_id=job_id,
                    agent_id=agent_id,
                    return_code=return_code,
                    output_name=output_name,
                    output_b64=output_b64,
                    logs=[str(x) for x in logs],
                    error=error,
                )
                if not job:
                    self._send_json({"error": "Job not found"}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_json({"job": job.snapshot()})
                return

        if parsed.path.startswith("/api/jobs/"):
            parts = parsed.path.strip("/").split("/")
            if len(parts) != 4:
                self._send_json({"error": "Bad request"}, status=HTTPStatus.BAD_REQUEST)
                return
            job_id = parts[2]
            action = parts[3]

            if action == "stop":
                job = JOB_MANAGER.stop_job(job_id)
                if not job:
                    remote_job = AGENT_JOB_MANAGER.stop_job(job_id)
                    if not remote_job:
                        self._send_json({"error": "Job not found or not stoppable"}, status=HTTPStatus.NOT_FOUND)
                        return
                    self._send_json({"job": remote_job.snapshot()})
                    return
                self._send_json({"job": job.snapshot()})
                return

            if action == "pause":
                job = JOB_MANAGER.pause_job(job_id)
                if not job:
                    self._send_json({"error": "Job not found or not pausable"}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json({"job": job.snapshot()})
                return

            if action == "start":
                job = JOB_MANAGER.resume_job(job_id)
                if not job:
                    self._send_json({"error": "Job not found or not resumable"}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json({"job": job.snapshot()})
                return

            if action == "restart":
                job = JOB_MANAGER.restart_job(job_id)
                if not job:
                    self._send_json({"error": "Job not found or restart not available"}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json({"job": job.snapshot()}, status=HTTPStatus.CREATED)
                return

            if action == "save":
                snapshot = JOB_MANAGER.save_job_snapshot(job_id, reason="manual")
                if not snapshot:
                    self._send_json({"error": "Job not found"}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_json({"snapshot": snapshot})
                return

        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json(self) -> dict[str, Any] | None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(content_length)
            return json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            self._send_json({"error": "Invalid JSON"}, status=HTTPStatus.BAD_REQUEST)
            return None

    @staticmethod
    def _validate_agent_token(payload: dict[str, Any]) -> bool:
        if not PARSERS_AGENT_TOKEN:
            return True
        token = str(payload.get("token", "")).strip()
        return bool(token) and token == PARSERS_AGENT_TOKEN

    def _serve_static(self, path: str) -> None:
        if path in {"/", ""}:
            target = STATIC_DIR / "index.html"
        elif path in {"/db", "/db/"}:
            target = STATIC_DIR / "db.html"
        elif path in {"/export", "/export/"}:
            target = STATIC_DIR / "export.html"
        else:
            safe_path = path.lstrip("/")
            target = (STATIC_DIR / safe_path).resolve()
            if not str(target).startswith(str(STATIC_DIR.resolve())):
                self.send_error(HTTPStatus.FORBIDDEN)
                return

        if not target.exists() or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
        }.get(target.suffix, "application/octet-stream")
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, file_path: Path, download_name: str | None = None) -> None:
        suffix = file_path.suffix.lower()
        content_type = "application/octet-stream"
        if suffix == ".csv":
            content_type = "text/csv; charset=utf-8"
        elif suffix == ".xlsx":
            content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        file_size = file_path.stat().st_size
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(file_size))
        if download_name:
            ascii_name = _ascii_filename(download_name)
            encoded_name = quote(download_name)
            self.send_header(
                "Content-Disposition",
                f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded_name}",
            )
        self.end_headers()
        with file_path.open("rb") as file_obj:
            shutil.copyfileobj(file_obj, self.wfile)


def _ascii_filename(name: str) -> str:
    cleaned = name.replace('"', "").replace("\n", " ").replace("\r", " ").strip()
    if not cleaned:
        return "export"
    normalized = unicodedata.normalize("NFKD", cleaned)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").strip()
    ascii_only = re.sub(r"[^A-Za-z0-9._ -]", "_", ascii_only)
    ascii_only = re.sub(r"\s+", "_", ascii_only)
    ascii_only = ascii_only.strip("._")
    return ascii_only or "export"


def main() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    host = os.environ.get("PARSERS_HUB_HOST", "127.0.0.1")
    port = int(os.environ.get("PARSERS_HUB_PORT", "8090"))
    server = ThreadingHTTPServer((host, port), AppHandler)
    print(f"Parsers Hub started: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
