from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from .postgres_sink import PostgresSinkError, persist_output_to_postgres
from .registry import get_adapters
from .reporting import MetricsCollector, RunReport, now_iso, refine_metrics_from_output, write_report


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="unified_parsers",
        description="Unified entry point for OLX, Krisha, and 2GIS parsers.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="Show available parser sources")
    list_parser.set_defaults(handler=handle_list)

    run_parser = subparsers.add_parser("run", help="Run parser by source")
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the command without executing the parser",
    )
    run_subparsers = run_parser.add_subparsers(dest="source", required=True)

    adapters = get_adapters()
    for source_key, adapter in adapters.items():
        source_parser = run_subparsers.add_parser(source_key, help=f"Run {adapter.title}")
        source_parser.add_argument(
            "--output-target",
            choices=["file", "db", "both"],
            default="db",
            help="Where to persist parsed data",
        )
        source_parser.add_argument(
            "--database-url",
            default="",
            help="PostgreSQL DSN (fallback: DATABASE_URL env)",
        )
        source_parser.add_argument(
            "--keep-output",
            action="store_true",
            help="Keep output file when output-target is db",
        )
        source_parser.add_argument(
            "--report-json",
            default="",
            help="Optional path to save run report in JSON format",
        )
        adapter.add_run_arguments(source_parser)

    run_parser.set_defaults(handler=handle_run)
    return parser


def handle_list(_: argparse.Namespace) -> int:
    print("Available sources:")
    for key, adapter in get_adapters().items():
        status = "ready" if adapter.implemented else "planned"
        print(f"- {key}: {adapter.title} ({status})")
    return 0


def handle_run(args: argparse.Namespace) -> int:
    adapters = get_adapters()
    adapter = adapters[args.source]
    if not adapter.implemented:
        print(
            f"[ERROR] Source '{adapter.key}' is not migrated yet. "
            "Current stage: scaffold only.",
            file=sys.stderr,
        )
        return 2

    project_root = _project_root()
    command = adapter.build_command(args, project_root)
    execution_cwd = adapter.execution_cwd(project_root)
    output_path = adapter.output_path(args, project_root)
    print(f"[unified] Running {adapter.key}: {' '.join(command)}")
    print(f"[unified] cwd: {execution_cwd}")
    if output_path is not None:
        print(f"[unified] output: {output_path}")

    if getattr(args, "dry_run", False):
        print("[unified] Dry run mode, parser process was not started.")
        return 0

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    output_target = str(getattr(args, "output_target", "file")).strip().lower()
    database_url = str(getattr(args, "database_url", "")).strip() or os.environ.get("DATABASE_URL", "").strip()
    live_db_supported_sources = {"krisha"}
    two_gis_live_db_enabled = os.environ.get("PARSERS_2GIS_LIVE_DB", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if two_gis_live_db_enabled:
        live_db_supported_sources.add("2gis")
    live_db_enabled = (
        adapter.key in live_db_supported_sources
        and output_target in {"db", "both"}
        and bool(database_url)
    )
    if live_db_enabled:
        live_run_id = str(uuid.uuid4())
        env["PARSER_LIVE_DB_MODE"] = "true"
        env["PARSER_LIVE_DB_SOURCE"] = adapter.key
        env["PARSER_LIVE_DB_URL"] = database_url
        env["PARSER_LIVE_DB_RUN_ID"] = live_run_id
    else:
        live_run_id = ""
    started_at_iso = now_iso()
    started_at_monotonic = time.monotonic()
    metrics = MetricsCollector()

    process = subprocess.Popen(
        command,
        cwd=execution_cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        print(line.rstrip("\n"))
        metrics.consume(line)
    exit_code = int(process.wait())

    processed, skipped, errors = metrics.finalize()
    processed, skipped, errors = refine_metrics_from_output(
        source=adapter.key,
        output_path=output_path,
        processed=processed,
        skipped=skipped,
        errors=errors,
        exit_code=exit_code,
    )
    duration_sec = round(time.monotonic() - started_at_monotonic, 2)
    finished_at_iso = now_iso()
    status = "completed" if exit_code == 0 else "failed"
    report = RunReport(
        source=adapter.key,
        status=status,
        exit_code=exit_code,
        started_at=started_at_iso,
        finished_at=finished_at_iso,
        duration_sec=duration_sec,
        output_path=str(output_path) if output_path is not None else "",
        processed=processed,
        skipped=skipped,
        errors=errors,
    )
    output_target = str(getattr(args, "output_target", "file")).strip().lower()
    database_url = str(getattr(args, "database_url", "")).strip() or os.environ.get("DATABASE_URL", "").strip()
    if output_target in {"db", "both"} and not database_url:
        print("[db] DATABASE_URL is required for output-target=db|both", file=sys.stderr)
        report.status = "failed"
        report.exit_code = 3
        report.errors = max(report.errors, 1)
        exit_code = 3

    is_olx_live_db_mode = (
        adapter.key == "olx"
        and output_target in {"db", "both"}
        and bool(database_url)
    )
    if is_olx_live_db_mode and exit_code == 0:
        print("[db] source=olx uses live per-record inserts inside olx_scraper")
    elif live_db_enabled and exit_code == 0:
        report.db_run_id = live_run_id
        report.db_records = report.processed
        print(
            f"[db] source={adapter.key} uses live per-record inserts inside parser process "
            f"(run_id={live_run_id})"
        )
    elif exit_code == 0 and output_target in {"db", "both"} and output_path is not None:
        try:
            db_run_id, db_records = persist_output_to_postgres(
                source=adapter.key,
                output_path=Path(report.output_path),
                database_url=database_url,
                status=report.status,
                metrics={
                    "processed": report.processed,
                    "skipped": report.skipped,
                    "errors": report.errors,
                    "duration_sec": report.duration_sec,
                },
            )
            report.db_run_id = db_run_id
            report.db_records = db_records
            print(f"[db] saved source={adapter.key} run_id={db_run_id} records={db_records}")
        except PostgresSinkError as exc:
            print(f"[db] save failed: {exc}", file=sys.stderr)
            report.status = "failed"
            report.exit_code = 4
            report.errors = max(report.errors, 1)
            exit_code = 4

    if (
        exit_code == 0
        and output_target == "db"
        and output_path is not None
        and not bool(getattr(args, "keep_output", False))
    ):
        try:
            Path(output_path).unlink(missing_ok=True)
            print(f"[unified] temporary output removed: {output_path}")
            report.output_path = ""
        except Exception as exc:  # noqa: BLE001
            print(f"[unified] failed to remove temporary output: {exc}", file=sys.stderr)

    print(
        "[report] "
        f"source={report.source} status={report.status} exit_code={report.exit_code} "
        f"processed={report.processed} skipped={report.skipped} errors={report.errors} "
        f"duration_sec={report.duration_sec}"
    )
    if report.output_path:
        print(f"[report] output_path={report.output_path}")
    if report.db_run_id:
        print(f"[report] db_run_id={report.db_run_id} db_records={report.db_records}")

    report_json_raw = str(getattr(args, "report_json", "")).strip()
    if report_json_raw:
        report_json_path = Path(report_json_raw)
        if not report_json_path.is_absolute():
            report_json_path = (project_root / report_json_path).resolve()
        write_report(report_json_path, report)
        print(f"[report] json_saved={report_json_path}")
    return int(exit_code)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
