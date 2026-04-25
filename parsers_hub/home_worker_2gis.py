#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def utc_stamp() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Home worker for remote 2GIS jobs from Parsers Hub.")
    parser.add_argument("--server-url", required=True, help="Parsers Hub base URL, e.g. http://46.62.225.70:8090")
    parser.add_argument("--token", required=True, help="Worker token (PARSERS_WORKER_TOKEN on server)")
    parser.add_argument("--worker-id", default=f"2gis-home-{socket.gethostname()}", help="Worker identifier in logs")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Polling interval in seconds")
    parser.add_argument("--python-bin", default="", help="Python binary for local unified parser")
    return parser.parse_args()


def resolve_python_bin(raw: str) -> str:
    if raw.strip():
        return raw.strip()
    for candidate in (
        PROJECT_ROOT / "venv/bin/python",
        PROJECT_ROOT / ".venv/bin/python",
        PROJECT_ROOT / "unified_sources/2gis/.venv/bin/python",
    ):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def build_local_command(payload: dict[str, Any], python_bin: str, report_path: Path, data_path: Path) -> list[str]:
    command = [
        python_bin,
        "parser_hub.py",
        "run",
        "2gis",
        "--search-url",
        str(payload.get("search_url", "")).strip(),
        "--max-records",
        str(max(1, int(payload.get("max_records", 100)))),
        "--format",
        str(payload.get("format", "xlsx")).strip() or "xlsx",
        "--output",
        str(data_path),
        "--output-target",
        "db",
        "--report-json",
        str(report_path),
    ]
    if payload.get("start_maximized", True):
        command.append("--start-maximized")
    else:
        command.append("--no-start-maximized")
    database_url = str(payload.get("database_url", "")).strip()
    if database_url:
        command.extend(["--database-url", database_url])
    return command


def post_worker(
    session: requests.Session,
    base_url: str,
    worker_id: str,
    token: str,
    path: str,
    payload: dict[str, Any],
) -> None:
    headers = {
        "X-Worker-Token": token,
        "X-Worker-Id": worker_id,
    }
    session.post(f"{base_url}{path}", json=payload, headers=headers, timeout=20)


def main() -> int:
    args = parse_args()
    base_url = args.server_url.rstrip("/")
    token = args.token.strip()
    worker_id = args.worker_id.strip()
    poll_interval = max(0.5, float(args.poll_interval))
    python_bin = resolve_python_bin(args.python_bin)

    session = requests.Session()
    headers = {
        "X-Worker-Token": token,
        "X-Worker-Id": worker_id,
    }

    print(f"[worker] started worker_id={worker_id}")
    print(f"[worker] server={base_url}")
    print(f"[worker] python={python_bin}")
    sys.stdout.flush()

    while True:
        try:
            response = session.get(f"{base_url}/api/worker/2gis/next", headers=headers, timeout=20)
            if response.status_code == 401:
                print("[worker] unauthorized: check token")
                return 2
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            print(f"[worker] poll error: {exc}")
            sys.stdout.flush()
            time.sleep(poll_interval)
            continue

        job = payload.get("job")
        if not job:
            time.sleep(poll_interval)
            continue

        job_id = str(job.get("job_id", "")).strip()
        run_payload = job.get("payload", {}) if isinstance(job.get("payload"), dict) else {}
        run_dir = PROJECT_ROOT / "parsers_hub" / "runs" / "2gis"
        run_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = run_dir / f"2gis_home_{job_id}_{stamp}.json"
        data_format = str(run_payload.get("format", "xlsx")).strip() or "xlsx"
        data_path = run_dir / f"2gis_home_{job_id}_{stamp}_data.{data_format}"
        command = build_local_command(run_payload, python_bin, report_path, data_path)

        start_line = f"[worker] {utc_stamp()} start job={job_id} command={' '.join(command)}"
        print(start_line)
        sys.stdout.flush()
        try:
            post_worker(
                session,
                base_url,
                worker_id,
                token,
                f"/api/worker/2gis/{job_id}/log",
                {"lines": [start_line]},
            )
        except Exception:
            pass

        try:
            process = subprocess.Popen(
                command,
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            assert process.stdout is not None
            batch: list[str] = []
            last_flush = time.monotonic()
            for line in process.stdout:
                clean = line.rstrip("\n")
                print(clean)
                sys.stdout.flush()
                batch.append(clean)
                now = time.monotonic()
                if len(batch) >= 20 or (now - last_flush) >= 1.0:
                    try:
                        post_worker(
                            session,
                            base_url,
                            worker_id,
                            token,
                            f"/api/worker/2gis/{job_id}/log",
                            {"lines": batch},
                        )
                    except Exception:
                        pass
                    batch = []
                    last_flush = now

            return_code = int(process.wait())
            if batch:
                try:
                    post_worker(
                        session,
                        base_url,
                        worker_id,
                        token,
                        f"/api/worker/2gis/{job_id}/log",
                        {"lines": batch},
                    )
                except Exception:
                    pass
            finish_payload = {
                "return_code": return_code,
                "status": "completed" if return_code == 0 else "failed",
                "output_path": str(report_path),
            }
            post_worker(
                session,
                base_url,
                worker_id,
                token,
                f"/api/worker/2gis/{job_id}/finish",
                finish_payload,
            )
            print(f"[worker] {utc_stamp()} finish job={job_id} code={return_code}")
            sys.stdout.flush()
        except Exception as exc:  # noqa: BLE001
            err_line = f"[worker] {utc_stamp()} job={job_id} crashed: {exc}"
            print(err_line)
            sys.stdout.flush()
            try:
                post_worker(
                    session,
                    base_url,
                    worker_id,
                    token,
                    f"/api/worker/2gis/{job_id}/log",
                    {"lines": [err_line]},
                )
                post_worker(
                    session,
                    base_url,
                    worker_id,
                    token,
                    f"/api/worker/2gis/{job_id}/finish",
                    {"return_code": 1, "status": "failed", "output_path": str(report_path)},
                )
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
