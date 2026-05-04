from __future__ import annotations

import os
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from .base import SourceAdapter


class KolesaAdapter(SourceAdapter):
    key = "kolesa"
    title = "Kolesa.kz"
    implemented = True

    def add_run_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--listing-url",
            default="https://kolesa.kz/cars/",
            help="Listing URL for Kolesa parser",
        )
        parser.add_argument("--listing-limit", type=int, default=10, help="Ads limit")
        parser.add_argument("--driver", choices=["http", "selenium"], default="http", help="Listing driver mode")
        parser.add_argument("--delay", type=float, default=0.7, help="Delay between ads")
        parser.add_argument("--random-delay-min", type=float, default=1.2, help="Minimum random delay")
        parser.add_argument("--random-delay-max", type=float, default=3.5, help="Maximum random delay")
        parser.add_argument("--no-proxy", dest="no_proxy", action="store_true", help="Disable proxy")
        parser.add_argument("--use-proxy", dest="no_proxy", action="store_false", help="Enable proxy list")
        parser.add_argument("--proxies-file", default="", help="Proxy list file")
        parser.add_argument("--headless", dest="headless", action="store_true", help="Run Selenium fallback headless")
        parser.add_argument("--no-headless", dest="headless", action="store_false", help="Run Selenium fallback visible")
        parser.add_argument("--app-id", default="", help="Kolesa phones API appId")
        parser.add_argument("--app-key", default="", help="Kolesa phones API appKey")
        parser.add_argument("--current-user", default="", help="Kolesa phones API currentUser")
        parser.add_argument("--captcha-token", default="", help="Optional captchaToken")
        parser.add_argument("--auth-token", default="", help="Optional Kolesa mobile X-AUTH-TOKEN")
        parser.add_argument("--idfa", default="", help="Optional Kolesa mobile idfa header")
        parser.add_argument("--phone-id", default="", help="Optional Kolesa mobile X-PHONE-ID header")
        parser.add_argument("--app-location", default="", help="Optional Kolesa mobile app-location header")
        parser.add_argument("--sessions-json", default="", help="JSON list with Kolesa mobile sessions")
        parser.add_argument("--sessions-file", default="", help="Path to JSON file with Kolesa mobile sessions")
        parser.add_argument("--session-cooldown-sec", type=float, default=900.0, help="Cooldown after Kolesa captcha/auth")
        parser.add_argument("--phone-max-session-attempts", type=int, default=20, help="Max Kolesa session attempts per phone")
        parser.add_argument("--cookie", default="", help="Cookie header string")
        parser.add_argument("--cookie-file", default="", help="Path to file with cookie header")
        parser.add_argument("--verify-ssl", dest="verify_ssl", action="store_true", help="Verify Kolesa SSL certificates")
        parser.add_argument("--insecure-ssl", dest="verify_ssl", action="store_false", help="Disable Kolesa SSL verification")
        parser.add_argument("--fetch-metadata", action="store_true", help="Compatibility option; metadata is always fetched")
        parser.add_argument("--output", default="kolesa_results.csv", help="Output CSV file path")
        parser.set_defaults(no_proxy=True, headless=True, verify_ssl=False)

    def output_path(self, args: Namespace, project_root: Path) -> Path:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = (project_root / "unified_runs" / "kolesa" / output_path).resolve()
        return output_path

    def build_command(self, args: Namespace, project_root: Path) -> list[str]:
        kolesa_dir = (project_root / "unified_sources" / "kolesa").resolve()
        python_bin = kolesa_dir / ".venv/bin/python"
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
            "kolesa_phone_parser.py",
            "--driver",
            str(args.driver),
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
        app_id = str(args.app_id).strip()
        if app_id:
            command.extend(["--app-id", app_id])
        app_key = str(args.app_key).strip()
        if app_key:
            command.extend(["--app-key", app_key])
        current_user = str(args.current_user).strip()
        if current_user:
            command.extend(["--current-user", current_user])
        captcha_token = str(args.captcha_token).strip()
        if captcha_token:
            command.extend(["--captcha-token", captcha_token])
        auth_token = str(args.auth_token).strip()
        if auth_token:
            command.extend(["--auth-token", auth_token])
        idfa = str(args.idfa).strip()
        if idfa:
            command.extend(["--idfa", idfa])
        phone_id = str(args.phone_id).strip()
        if phone_id:
            command.extend(["--phone-id", phone_id])
        app_location = str(args.app_location).strip()
        if app_location:
            command.extend(["--app-location", app_location])
        sessions_json = str(args.sessions_json).strip()
        if sessions_json:
            command.extend(["--sessions-json", sessions_json])
        sessions_file = str(args.sessions_file).strip()
        if sessions_file:
            command.extend(["--sessions-file", sessions_file])
        command.extend(["--session-cooldown-sec", str(args.session_cooldown_sec)])
        command.extend(["--phone-max-session-attempts", str(args.phone_max_session_attempts)])
        if args.no_proxy:
            command.append("--no-proxy")
        else:
            proxies_file = str(args.proxies_file).strip() or str(project_root / "proxyscrape_premium_http_proxies.txt")
            command.extend(["--proxies-file", proxies_file])
        if args.headless:
            command.append("--headless")
        else:
            command.append("--no-headless")
        if args.verify_ssl:
            command.append("--verify-ssl")
        else:
            command.append("--insecure-ssl")
        cookie = str(args.cookie).strip()
        if cookie:
            command.extend(["--cookie", cookie])
        cookie_file = str(args.cookie_file).strip()
        if cookie_file:
            command.extend(["--cookie-file", cookie_file])

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
        return (project_root / "unified_sources" / "kolesa").resolve()
