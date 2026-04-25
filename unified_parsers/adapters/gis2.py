from __future__ import annotations

import os
import sys
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
        parser.add_argument(
            "--selenium-html",
            action="store_true",
            help="Use experimental Selenium HTML parser instead of parser-2gis API mode",
        )
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
            fallback = project_root / "venv/bin/python"
            if fallback.exists():
                python_bin = fallback
            else:
                env_python = os.environ.get("PARSERS_PYTHON_BIN", "").strip()
                python_bin = Path(env_python) if env_python else Path(sys.executable)

        output_path = self.output_path(args, project_root)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if bool(getattr(args, "selenium_html", False)):
            command = [
                str(python_bin),
                "selenium_html_parser.py",
                "--search-url",
                str(args.search_url),
                "--max-records",
                str(max(1, int(args.max_records))),
                "--format",
                str(args.format),
                "--output",
                str(output_path),
            ]
            remote_url = os.environ.get("SELENIUM_REMOTE_URL", "").strip()
            if remote_url:
                command.extend(["--remote-url", remote_url])
            headless_env = os.environ.get("PARSERS_2GIS_HEADLESS", "").strip().lower()
            if not headless_env and Path("/.dockerenv").exists():
                headless_env = "yes"
            if headless_env in {"1", "true", "yes", "on"}:
                command.extend(["--headless", "yes"])
            else:
                command.extend(["--headless", "no"])
            return command

        command = [
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

        chrome_binary = (
            os.environ.get("CHROME_BINARY", "").strip()
            or os.environ.get("CHROMIUM_BINARY", "").strip()
        )
        if not chrome_binary:
            for candidate in ("/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"):
                if Path(candidate).exists():
                    chrome_binary = candidate
                    break
        if chrome_binary:
            command.extend(["--chrome.binary_path", chrome_binary])

        headless_env = os.environ.get("PARSERS_2GIS_HEADLESS", "").strip().lower()
        if not headless_env and Path("/.dockerenv").exists():
            headless_env = "yes"
        if headless_env in {"1", "true", "yes", "on"}:
            command.extend(["--chrome.headless", "yes"])

        return command

    def execution_cwd(self, project_root: Path) -> Path:
        return (project_root / "unified_sources" / "2gis").resolve()
