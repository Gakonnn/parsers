from __future__ import annotations

import os
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from .base import SourceAdapter


class KrishaAdapter(SourceAdapter):
    key = "krisha"
    title = "Krisha.kz"
    implemented = True

    def add_run_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--listing-url",
            default="https://krisha.kz/prodazha/kvartiry/",
            help="Listing URL for Krisha parser",
        )
        parser.add_argument("--listing-limit", type=int, default=10, help="Ads limit")
        parser.add_argument("--deal-type", default="", help="Krisha deal filter: prodazha/arenda")
        parser.add_argument("--property-type", default="", help="Krisha property filter, e.g. kvartiry")
        parser.add_argument("--krisha-location", default="", help="Krisha location alias")
        parser.add_argument("--rooms", default="", help="Comma-separated room filters, e.g. 1,2,5+")
        parser.add_argument("--price-from", default="", help="Minimum listing price in KZT")
        parser.add_argument("--price-to", default="", help="Maximum listing price in KZT")
        parser.add_argument("--has-photo", action="store_true", help="Only listings with photos")
        parser.add_argument("--new-buildings", action="store_true", help="Only new-building listings")
        parser.add_argument("--from-owner", action="store_true", help="Only owner listings")
        parser.add_argument("--from-agent", action="store_true", help="Only Krisha Agent listings")
        parser.add_argument("--driver", choices=["selenium", "http"], default="selenium", help="Driver mode")
        parser.add_argument("--browser", choices=["chrome", "safari"], default="chrome", help="Selenium browser")
        parser.add_argument("--delay", type=float, default=0.7, help="Delay between ads")
        parser.add_argument("--random-delay-min", type=float, default=1.2, help="Minimum random delay")
        parser.add_argument("--random-delay-max", type=float, default=3.5, help="Maximum random delay")
        parser.add_argument("--no-proxy", dest="no_proxy", action="store_true", help="Disable proxy")
        parser.add_argument("--use-proxy", dest="no_proxy", action="store_false", help="Enable proxy list")
        parser.add_argument("--headless", dest="headless", action="store_true", help="Run in headless mode")
        parser.add_argument("--no-headless", dest="headless", action="store_false", help="Run with visible browser")
        parser.add_argument("--cookie-file", default="", help="Path to cookie file")
        parser.add_argument("--account-login", default="", help="Account login")
        parser.add_argument("--account-password", default="", help="Account password")
        parser.add_argument("--output", default="result_random.csv", help="Output CSV file path")
        parser.set_defaults(no_proxy=True, headless=False)

    def output_path(self, args: Namespace, project_root: Path) -> Path:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = (project_root / "unified_runs" / "krisha" / output_path).resolve()
        return output_path

    def build_command(self, args: Namespace, project_root: Path) -> list[str]:
        krisha_dir = (project_root / "unified_sources" / "krisha").resolve()
        python_bin = krisha_dir / ".venv/bin/python"
        if not python_bin.exists():
            fallback = project_root / "venv/bin/python"
            if fallback.exists():
                python_bin = fallback
            else:
                env_python = os.environ.get("PARSERS_PYTHON_BIN", "").strip()
                python_bin = Path(env_python) if env_python else Path(sys.executable)

        output_path = self.output_path(args, project_root)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        command = [
            str(python_bin),
            "krisha_phone_parser.py",
            "--driver",
            str(args.driver),
            "--browser",
            str(args.browser),
            "--listing-url",
            str(args.listing_url),
            "--listing-limit",
            str(max(1, int(args.listing_limit))),
            "--delay",
            str(args.delay),
            "--random-delay-min",
            str(args.random_delay_min),
            "--random-delay-max",
            str(args.random_delay_max),
            "--output",
            str(output_path),
        ]

        for flag, value in (
            ("--deal-type", getattr(args, "deal_type", "")),
            ("--property-type", getattr(args, "property_type", "")),
            ("--krisha-location", getattr(args, "krisha_location", "")),
            ("--rooms", getattr(args, "rooms", "")),
            ("--price-from", getattr(args, "price_from", "")),
            ("--price-to", getattr(args, "price_to", "")),
        ):
            clean_value = str(value).strip()
            if clean_value:
                command.extend([flag, clean_value])

        if getattr(args, "has_photo", False):
            command.append("--has-photo")
        if getattr(args, "new_buildings", False):
            command.append("--new-buildings")
        if getattr(args, "from_owner", False):
            command.append("--from-owner")
        if getattr(args, "from_agent", False):
            command.append("--from-agent")

        if args.no_proxy:
            command.append("--no-proxy")
        if args.headless:
            command.append("--headless")
        else:
            command.append("--no-headless")

        cookie_file = str(args.cookie_file).strip()
        if cookie_file:
            command.extend(["--cookie-file", cookie_file])
        account_login = str(args.account_login).strip()
        if account_login:
            command.extend(["--account-login", account_login])
        account_password = str(args.account_password)
        if account_password:
            command.extend(["--account-password", account_password])
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
            command.extend(["--chrome-binary", chrome_binary])
        database_url = str(getattr(args, "database_url", "")).strip()
        if database_url:
            command.extend(["--database-url", database_url])

        return command

    def execution_cwd(self, project_root: Path) -> Path:
        return (project_root / "unified_sources" / "krisha").resolve()
