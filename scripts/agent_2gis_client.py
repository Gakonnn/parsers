#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib import error, request


def _post_json(url: str, payload: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _build_run_command(
    python_bin: str,
    project_root: Path,
    payload: dict[str, Any],
    output_path: Path,
) -> list[str]:
    command = [
        python_bin,
        str(project_root / "parser_hub.py"),
        "run",
        "2gis",
        "--search-url",
        str(payload.get("search_url", "https://2gis.ru/almaty/search/аптека")),
        "--max-records",
        str(int(payload.get("max_records", 100))),
        "--format",
        str(payload.get("format", "xlsx")),
        "--output",
        str(output_path),
        "--output-target",
        "file",
        "--keep-output",
    ]
    if bool(payload.get("start_maximized", True)):
        command.append("--start-maximized")
    else:
        command.append("--no-start-maximized")
    return command


def _run_local_job(
    python_bin: str,
    project_root: Path,
    payload: dict[str, Any],
) -> tuple[int, list[str], Path]:
    suffix = f".{payload.get('format', 'xlsx')}"
    fd, tmp_name = tempfile.mkstemp(prefix="agent_2gis_", suffix=suffix)
    Path(tmp_name).unlink(missing_ok=True)
    output_path = Path(tmp_name)
    command = _build_run_command(python_bin, project_root, payload, output_path)

    logs: list[str] = [f"[agent] Running: {' '.join(command)}\n"]
    process = subprocess.Popen(
        command,
        cwd=str(project_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        logs.append(line)
    return_code = int(process.wait())
    return return_code, logs[-1200:], output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Mini-agent for remote 2GIS jobs")
    parser.add_argument("--server-url", required=True, help="Parsers Hub URL, example: http://77.246.247.109:8090")
    parser.add_argument("--token", default="", help="Agent token (must match PARSERS_AGENT_TOKEN on server)")
    parser.add_argument("--agent-id", default=platform.node() or "agent-2gis", help="Agent identifier")
    parser.add_argument("--project-root", default=".", help="Project root where parser_hub.py exists")
    parser.add_argument("--python-bin", default=sys.executable, help="Python binary to run parser_hub.py")
    parser.add_argument("--poll-interval", type=float, default=3.0, help="Polling interval in seconds")
    args = parser.parse_args()

    server_url = args.server_url.rstrip("/")
    project_root = Path(args.project_root).resolve()
    if not (project_root / "parser_hub.py").exists():
        print(f"[agent] parser_hub.py not found in {project_root}", file=sys.stderr)
        return 2

    print(f"[agent] started id={args.agent_id} server={server_url}")
    while True:
        try:
            next_payload = _post_json(
                f"{server_url}/api/agent/next",
                {"agent_id": args.agent_id, "token": args.token},
                timeout=40,
            )
            job = next_payload.get("job")
            if not job:
                time.sleep(max(0.5, args.poll_interval))
                continue

            job_id = str(job.get("job_id", "")).strip()
            payload = job.get("payload") or {}
            print(f"[agent] got job {job_id}")
            try:
                return_code, logs, output_path = _run_local_job(
                    python_bin=args.python_bin,
                    project_root=project_root,
                    payload=payload,
                )
                output_b64 = ""
                output_name = output_path.name
                if output_path.exists() and output_path.is_file():
                    output_b64 = base64.b64encode(output_path.read_bytes()).decode("utf-8")
                _post_json(
                    f"{server_url}/api/agent/jobs/{job_id}/complete",
                    {
                        "agent_id": args.agent_id,
                        "token": args.token,
                        "return_code": return_code,
                        "output_name": output_name,
                        "output_b64": output_b64,
                        "logs": logs,
                    },
                    timeout=120,
                )
                output_path.unlink(missing_ok=True)
                print(f"[agent] completed job {job_id} code={return_code}")
            except Exception as exc:  # noqa: BLE001
                _post_json(
                    f"{server_url}/api/agent/jobs/{job_id}/complete",
                    {
                        "agent_id": args.agent_id,
                        "token": args.token,
                        "return_code": 1,
                        "output_name": "",
                        "output_b64": "",
                        "logs": [f"[agent] exception: {exc}\n"],
                        "error": str(exc),
                    },
                    timeout=60,
                )
                print(f"[agent] failed job {job_id}: {exc}", file=sys.stderr)
        except error.HTTPError as exc:
            print(f"[agent] HTTP error: {exc.code} {exc.reason}", file=sys.stderr)
            time.sleep(max(1.0, args.poll_interval))
        except Exception as exc:  # noqa: BLE001
            print(f"[agent] poll error: {exc}", file=sys.stderr)
            time.sleep(max(1.0, args.poll_interval))


if __name__ == "__main__":
    raise SystemExit(main())
