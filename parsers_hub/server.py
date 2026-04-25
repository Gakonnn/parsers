#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

try:
    import psycopg2
except Exception:  # noqa: BLE001
    psycopg2 = None


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
DEFAULT_DATABASE_URL = os.environ.get("PARSERS_HUB_DATABASE_URL", "postgresql://gakon@127.0.0.1:55432/parsers")
DEFAULT_HEADLESS = os.environ.get("PARSERS_DEFAULT_HEADLESS", "true").strip().lower() in {"1", "true", "yes", "on"}


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
            "log": "".join(self.log_lines[-400:]),
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
                {"name": "max_records", "label": "Максимум записей", "type": "number", "required": True, "default": 100},
                {"name": "output_name", "label": "Имя файла", "type": "text", "required": False, "default": ""},
                {"name": "format", "label": "Формат", "type": "select", "required": True, "default": "xlsx", "options": ["xlsx", "csv", "json"]},
                {"name": "start_maximized", "label": "Стартовать окно развёрнутым", "type": "checkbox", "required": False, "default": True},
                {"name": "database_url", "label": "PostgreSQL URL", "type": "text", "required": False, "default": DEFAULT_DATABASE_URL},
            ],
        },
        "krisha": {
            "title": "Krisha.kz",
            "description": "Сбор телефонов с Krisha по странице листинга или одному объявлению с записью в PostgreSQL.",
            "output_ext": "json",
            "fields": [
                {"name": "listing_url", "label": "Ссылка на листинг", "type": "url", "required": True, "default": "https://krisha.kz/prodazha/kvartiry/"},
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


COMMAND_BUILDERS = {
    "olx": build_olx_command,
    "2gis": build_2gis_command,
    "krisha": build_krisha_command,
}


def parse_int(value: str | None, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, parsed))


def query_db_records(params: dict[str, list[str]]) -> dict[str, Any]:
    if psycopg2 is None:
        raise RuntimeError("psycopg2 is not installed in current Python environment.")

    source = (params.get("source", [""])[0] or "").strip().lower()
    run_status = (params.get("run_status", [""])[0] or "").strip().lower()
    has_phone = (params.get("has_phone", [""])[0] or "").strip().lower()
    search = (params.get("search", [""])[0] or "").strip()
    limit = parse_int((params.get("limit") or [None])[0], default=100, min_value=1, max_value=500)
    page = parse_int((params.get("page") or [None])[0], default=1, min_value=1, max_value=10_000)
    offset = (page - 1) * limit
    database_url = (params.get("database_url", [""])[0] or "").strip() or DEFAULT_DATABASE_URL

    where_parts: list[str] = []
    where_values: list[Any] = []

    if source:
        where_parts.append("r.source = %s")
        where_values.append(source)
    if run_status:
        where_parts.append("COALESCE(runs.status, '') = %s")
        where_values.append(run_status)
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
    if search:
        like = f"%{search}%"
        where_parts.append(
            "(r.external_id ILIKE %s OR r.run_id::text ILIKE %s OR r.payload::text ILIKE %s)"
        )
        where_values.extend([like, like, like])

    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    count_sql = (
        "SELECT COUNT(*) "
        "FROM parser_records r "
        "LEFT JOIN parser_runs runs ON runs.run_id = r.run_id "
        f"{where_sql}"
    )
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

    with psycopg2.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(count_sql, where_values)
            total = int(cur.fetchone()[0])
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

    return {
        "filters": {
            "source": source,
            "run_status": run_status,
            "has_phone": has_phone,
            "search": search,
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
            try:
                cleaned[name] = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Поле '{field['label']}' должно быть числом") from exc
        elif field_type == "checkbox":
            cleaned[name] = bool(value)
        else:
            cleaned[name] = "" if value is None else str(value)

        if field.get("required") and field_type != "checkbox" and str(cleaned[name]).strip() == "":
            raise ValueError(f"Поле '{field['label']}' обязательно")
    return cleaned


class AppHandler(BaseHTTPRequestHandler):
    server_version = "ParsersHub/1.0"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/config":
            self._send_json({"parsers": parser_definitions()})
            return
        if parsed.path == "/api/db/records":
            try:
                result = query_db_records(parse_qs(parsed.query))
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": f"DB query failed: {exc}"}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(result)
            return
        if parsed.path == "/api/jobs":
            self._send_json({"jobs": JOB_MANAGER.list_jobs()})
            return
        if parsed.path.startswith("/api/jobs/"):
            job_id = parsed.path.rsplit("/", 1)[-1]
            job = JOB_MANAGER.get_job(job_id)
            if not job:
                self._send_json({"error": "Job not found"}, status=HTTPStatus.NOT_FOUND)
                return
            self._send_json(job.snapshot())
            return
        self._serve_static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/run":
            payload = self._read_json()
            if payload is None:
                return
            parser_key = payload.get("parser_key")
            form_data = payload.get("payload", {})
            try:
                cleaned = validate_payload(parser_key, form_data)
                command, cwd, output_path = COMMAND_BUILDERS[parser_key](cleaned)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            job = JOB_MANAGER.create_job(parser_key, command, cwd, output_path)
            self._send_json({"job": job.snapshot()}, status=HTTPStatus.CREATED)
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
                    self._send_json({"error": "Job not found or not stoppable"}, status=HTTPStatus.NOT_FOUND)
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

    def _serve_static(self, path: str) -> None:
        if path in {"/", ""}:
            target = STATIC_DIR / "index.html"
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
