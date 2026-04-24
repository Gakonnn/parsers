from __future__ import annotations

import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from .base import SourceAdapter


class OlxAdapter(SourceAdapter):
    key = "olx"
    title = "OLX.kz"
    implemented = True

    def add_run_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--category-url",
            default="https://www.olx.kz/elektronika/",
            help="Category URL for OLX parser",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Number of ads to parse",
        )
        parser.add_argument(
            "--output",
            default="unified_olx_results.xlsx",
            help="Output XLSX file path",
        )

    def output_path(self, args: Namespace, project_root: Path) -> Path:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = project_root / output_path
        return output_path

    def build_command(self, args: Namespace, project_root: Path) -> list[str]:
        script_path = project_root / "olx_scraper.py"
        output_path = self.output_path(args, project_root)

        command = [
            sys.executable,
            str(script_path),
            "-c",
            str(args.category_url),
            "-l",
            str(max(1, int(args.limit))),
            "-o",
            str(output_path),
        ]
        database_url = str(getattr(args, "database_url", "")).strip()
        if database_url:
            command.extend(["--database-url", database_url])
        return command
