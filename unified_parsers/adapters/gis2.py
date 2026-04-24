from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path

from .base import SourceAdapter


class Gis2Adapter(SourceAdapter):
    key = "2gis"
    title = "2GIS"
    implemented = True

    def add_run_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--search-url",
            default="https://2gis.ru/almaty/search/аптека",
            help="Search URL for 2GIS parser",
        )
        parser.add_argument("--max-records", type=int, default=100, help="Maximum records")
        parser.add_argument("--format", choices=["xlsx", "csv", "json"], default="xlsx", help="Output format")
        parser.add_argument(
            "--start-maximized",
            dest="start_maximized",
            action="store_true",
            help="Start browser maximized",
        )
        parser.add_argument(
            "--no-start-maximized",
            dest="start_maximized",
            action="store_false",
            help="Do not maximize browser window on start",
        )
        parser.add_argument("--output", default="unified_2gis_results.xlsx", help="Output file path")
        parser.set_defaults(start_maximized=True)

    def output_path(self, args: Namespace, project_root: Path) -> Path:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = (project_root / "unified_runs" / "2gis" / output_path).resolve()
        return output_path

    def build_command(self, args: Namespace, project_root: Path) -> list[str]:
        gis_dir = (project_root / "unified_sources" / "2gis").resolve()
        python_bin = gis_dir / ".venv/bin/python"
        if not python_bin.exists():
            python_bin = project_root / "venv/bin/python"

        output_path = self.output_path(args, project_root)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        return [
            str(python_bin),
            "parser-2gis.py",
            "-i",
            str(args.search_url),
            "-o",
            str(output_path),
            "-f",
            str(args.format),
            "--chrome.start-maximized",
            "yes" if args.start_maximized else "no",
            "--parser.max-records",
            str(max(1, int(args.max_records))),
        ]

    def execution_cwd(self, project_root: Path) -> Path:
        return (project_root / "unified_sources" / "2gis").resolve()
