#!/usr/bin/env python3
"""Collect phone numbers from kolesa.kz listing ads.

The parser follows the same hub contract as krisha_phone_parser.py:
- collect ad URLs from a listing page page-by-page;
- fetch phones for every ad through the Kolesa mobile API;
- write CSV/JSON output;
- optionally insert every row into PostgreSQL live while parsing.
"""

from __future__ import annotations

import argparse
import csv
import html as html_lib
import json
import os
import random
import re
import ssl
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from unified_parsers.phone_utils import normalize_phone_number, normalize_phone_numbers

try:
    import psycopg2
    from psycopg2.extras import Json
except ModuleNotFoundError:  # pragma: no cover
    psycopg2 = None
    Json = None

try:
    import certifi
except ModuleNotFoundError:  # pragma: no cover
    certifi = None

try:
    from selenium import webdriver
    from selenium.common.exceptions import TimeoutException, WebDriverException
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.support.ui import WebDriverWait
except ModuleNotFoundError:  # pragma: no cover
    webdriver = None

    class _SeleniumUnavailableError(Exception):
        pass

    TimeoutException = WebDriverException = _SeleniumUnavailableError
    Options = Service = WebDriverWait = None

DEFAULT_LISTING_URL = "https://kolesa.kz/cars/"
DEFAULT_APP_ID = os.environ.get("KOLESA_PHONE_APP_ID", "881010608584")
DEFAULT_APP_KEY = os.environ.get("KOLESA_PHONE_APP_KEY", "b6639f8ceebfc82711fdca33977b827e")
DEFAULT_CURRENT_USER = os.environ.get("KOLESA_PHONE_CURRENT_USER", "20822821@auto.kolesa.kz")
DEFAULT_CAPTCHA_TOKEN = os.environ.get("KOLESA_PHONE_CAPTCHA_TOKEN", "")
DEFAULT_COOKIE = os.environ.get("KOLESA_COOKIE", "")
DEFAULT_COOKIE_FILE = os.environ.get("KOLESA_COOKIE_FILE", "")
DEFAULT_AUTH_TOKEN = os.environ.get("KOLESA_AUTH_TOKEN", os.environ.get("KOLESA_PHONE_AUTH_TOKEN", ""))
DEFAULT_IDFA = os.environ.get("KOLESA_IDFA", "")
DEFAULT_PHONE_ID = os.environ.get("KOLESA_PHONE_ID", "")
DEFAULT_APP_LOCATION = os.environ.get("KOLESA_APP_LOCATION", "")
DEFAULT_APP_VERSION = os.environ.get("KOLESA_APP_VERSION", "26.4.18")
DEFAULT_APP_PLATFORM_VERSION = os.environ.get("KOLESA_APP_PLATFORM_VERSION", "17.2.1")
DEFAULT_APP_PUSH_ENABLE = os.environ.get("KOLESA_APP_PUSH_ENABLE", "false")
DEFAULT_SESSIONS_JSON = os.environ.get("KOLESA_SESSIONS_JSON", "")
DEFAULT_SESSIONS_FILE = os.environ.get("KOLESA_SESSIONS_FILE", "")
DEFAULT_SESSION_COOLDOWN_SEC = float(os.environ.get("KOLESA_SESSION_COOLDOWN_SEC", "900") or 900)
DEFAULT_CRAWLBASE_TOKEN = os.environ.get("KOLESA_CRAWLBASE_TOKEN", os.environ.get("CRAWLBASE_TOKEN", ""))
DEFAULT_CRAWLBASE_JS_TOKEN = os.environ.get("KOLESA_CRAWLBASE_JS_TOKEN", os.environ.get("CRAWLBASE_JS_TOKEN", ""))
DIRECT_PROXY = "__DIRECT__"
CHECKPOINT_SUFFIX = ".checkpoint.json"

AD_RE = re.compile(r"(?:https?:)?//kolesa\.kz/a/show/(\d+)|/a/show/(\d+)", re.IGNORECASE)
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
TITLE_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
INLINE_DATA_RE = re.compile(r"<script>\s*var\s+data\s*=\s*(\{.*?\})\s*;\s*</script>", re.IGNORECASE | re.DOTALL)
OFFER_PRICE_RE = re.compile(
    r"<div[^>]+(?:class=[\"'][^\"']*offer__price[^\"']*[\"']|data-test=[\"']offer-price[\"'])[^>]*>(.*?)</div>",
    re.IGNORECASE | re.DOTALL,
)
META_DESCRIPTION_RE = re.compile(
    r"<meta[^>]+name=[\"']description[\"'][^>]+content=[\"']([^\"']*)[\"']",
    re.IGNORECASE | re.DOTALL,
)
SELLER_HTML_RE = re.compile(
    r"<[^>]+(?:class|data-test)=[\"'][^\"']*(?:seller[-_ ]?name|seller[-_ ]?title|owner[-_ ]?name|contact[-_ ]?name|dealer[-_ ]?name)[^\"']*[\"'][^>]*>(.*?)</[^>]+>",
    re.IGNORECASE | re.DOTALL,
)
METADATA_FIELDS = ("title", "price", "description", "seller_name", "city")
ROW_FIELDNAMES = ["ad_url", "ad_id", *METADATA_FIELDS, "phones", "status", "proxy", "error"]

DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-KZ,ru;q=0.9,en;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

API_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": DEFAULT_HEADERS["User-Agent"],
    "Origin": "https://kolesa.kz",
}


@dataclass
class HttpResponse:
    status_code: int
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text)


@dataclass
class ProxyResult:
    response: HttpResponse
    proxy: str


@dataclass
class KolesaSession:
    name: str
    app_id: str
    app_key: str
    current_user: str
    captcha_token: str = ""
    auth_token: str = ""
    cookie: str = ""
    idfa: str = ""
    phone_id: str = ""
    app_location: str = ""
    app_version: str = DEFAULT_APP_VERSION
    app_platform_version: str = DEFAULT_APP_PLATFORM_VERSION
    app_push_enable: str = DEFAULT_APP_PUSH_ENABLE
    unavailable_until: float = 0.0
    captcha_hits: int = 0
    auth_hits: int = 0

    @property
    def label(self) -> str:
        return self.name or "kolesa-session"


class ProxyRotator:
    def __init__(
        self,
        proxies: list[str],
        timeout: float = 12.0,
        blocked_proxies: set[str] | None = None,
        *,
        verify_ssl: bool = True,
    ):
        if not proxies:
            raise ValueError("Proxy list is empty")
        self.proxies = proxies
        self.timeout = timeout
        self.current_index = 0
        self.blocked_proxies = blocked_proxies or set()
        self._ssl_context = self._build_ssl_context(verify_ssl=verify_ssl)

    @staticmethod
    def _build_ssl_context(*, verify_ssl: bool) -> ssl.SSLContext:
        if not verify_ssl:
            return ssl._create_unverified_context()  # noqa: SLF001 - required for Kolesa app API cert chain in some environments.
        if certifi is not None:
            return ssl.create_default_context(cafile=certifi.where())
        return ssl.create_default_context()

    @staticmethod
    def _to_proxy_url(raw_proxy: str) -> str:
        if raw_proxy == DIRECT_PROXY:
            return ""
        if "://" in raw_proxy:
            return raw_proxy
        return f"http://{raw_proxy}"

    def _request_once(self, method: str, url: str, headers: dict[str, str], proxy: str) -> HttpResponse:
        proxy_url = self._to_proxy_url(proxy)
        handlers = []
        if proxy_url:
            handlers.append(ProxyHandler({"http": proxy_url, "https": proxy_url}))
        handlers.append(HTTPSHandler(context=self._ssl_context))
        opener = build_opener(*handlers)
        req = Request(url=url, method=method, headers=headers)
        try:
            with opener.open(req, timeout=self.timeout) as resp:
                return HttpResponse(status_code=resp.getcode(), body=resp.read())
        except HTTPError as exc:
            return HttpResponse(status_code=exc.code, body=exc.read())

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        ok_statuses: set[int] | None = None,
        retry_statuses: set[int] | None = None,
    ) -> ProxyResult:
        ok_statuses = ok_statuses or {200}
        retry_statuses = retry_statuses or {403, 407, 410, 429, 500, 502, 503, 504}
        if params:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{urlencode(params)}"
        req_headers = headers or {}
        n = len(self.proxies)
        start = self.current_index
        last_error: Exception | None = None

        for step in range(n):
            idx = (start + step) % n
            proxy = self.proxies[idx]
            if proxy in self.blocked_proxies:
                continue
            try:
                resp = self._request_once(method, url, req_headers, proxy)
            except (URLError, TimeoutError, OSError) as exc:
                last_error = exc
                continue
            if resp.status_code in ok_statuses:
                self.current_index = idx
                return ProxyResult(response=resp, proxy=proxy)
            if resp.status_code in retry_statuses:
                continue
            raise RuntimeError(f"Request failed with status {resp.status_code}: {resp.text[:300]}")

        if last_error:
            raise RuntimeError(f"All proxies failed, last error: {last_error}") from last_error
        raise RuntimeError("All proxies failed with non-success status")


class CrawlbaseClient:
    """Optional fallback transport for Kolesa phone API when the direct IP gets challenged."""

    def __init__(self, token: str, *, timeout: float, verify_ssl: bool = True) -> None:
        self.token = token.strip()
        self.timeout = timeout
        self._ssl_context = ProxyRotator._build_ssl_context(verify_ssl=verify_ssl)

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    @staticmethod
    def _request_headers_param(headers: dict[str, str]) -> str:
        allowed_headers = [
            "accept",
            "accept-language",
            "app-language",
            "app-location",
            "app-photo-format",
            "app-platform",
            "app-platform-version",
            "app-push-enable",
            "app-version",
            "idfa",
            "referer",
            "user-agent",
            "x-app-screen-coefficient",
            "x-auth-token",
            "x-phone-id",
        ]
        parts: list[str] = []
        for key, value in headers.items():
            header_key = key.strip()
            header_value = str(value or "").strip()
            if not header_key or not header_value or header_key.lower() == "cookie":
                continue
            if header_key.lower() not in allowed_headers:
                continue
            parts.append(f"{header_key}:{header_value}")
        return "|".join(parts)

    def request_json(self, target_url: str, *, headers: dict[str, str]) -> tuple[Any, str]:
        if not self.enabled:
            raise RuntimeError("Crawlbase token is not configured")
        params = {
            "token": self.token,
            "url": target_url,
        }
        request_headers = self._request_headers_param(headers)
        if request_headers:
            params["request_headers"] = request_headers
        cookie = headers.get("Cookie", "").strip()
        if cookie:
            params["cookies"] = cookie
        crawlbase_url = f"https://api.crawlbase.com/?{urlencode(params)}"
        req = Request(url=crawlbase_url, method="GET", headers={"Accept": "application/json,*/*"})
        opener = build_opener(HTTPSHandler(context=self._ssl_context))
        try:
            with opener.open(req, timeout=self.timeout) as resp:
                body = resp.read()
        except HTTPError as exc:
            body = exc.read()
        text = body.decode("utf-8", errors="replace")
        payload = json.loads(text)
        if isinstance(payload, dict):
            nested_body = payload.get("body") or payload.get("original_body")
            if isinstance(nested_body, str):
                try:
                    return json.loads(nested_body), "crawlbase"
                except json.JSONDecodeError:
                    pass
        return payload, "crawlbase"


class LiveDbWriter:
    def __init__(self, database_url: str, *, source: str = "kolesa", run_id: str = "") -> None:
        if psycopg2 is None or Json is None:
            raise RuntimeError("psycopg2 is required for live DB mode")
        self.source = source
        self.run_id = run_id.strip() or str(uuid.uuid4())
        self._conn = psycopg2.connect(database_url)
        self._conn.autocommit = True
        self._processed = 0
        self._seen_external_ids: set[str] = set()
        self._ensure_schema()
        self._start_run()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS parser_runs (
                    run_id UUID PRIMARY KEY,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS parser_records (
                    id BIGSERIAL PRIMARY KEY,
                    run_id UUID NOT NULL REFERENCES parser_runs(run_id) ON DELETE CASCADE,
                    source TEXT NOT NULL,
                    external_id TEXT NOT NULL DEFAULT '',
                    payload JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_parser_records_source_external "
                "ON parser_records (source, external_id)"
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_parser_records_run_id ON parser_records (run_id)")

    def _start_run(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO parser_runs (run_id, source, status, metrics)
                VALUES (%s::uuid, %s, %s, %s::jsonb)
                ON CONFLICT (run_id) DO NOTHING
                """,
                (self.run_id, self.source, "running", json.dumps({})),
            )

    def insert_row(self, row: dict[str, str]) -> None:
        external_id = str(row.get("ad_id", "") or row.get("ad_url", "")).strip()
        if external_id and external_id in self._seen_external_ids:
            return
        with self._conn.cursor() as cur:
            if external_id:
                cur.execute(
                    """
                    SELECT 1 FROM parser_records
                    WHERE run_id = %s::uuid AND external_id = %s
                    LIMIT 1
                    """,
                    (self.run_id, external_id),
                )
                if cur.fetchone():
                    self._seen_external_ids.add(external_id)
                    return
            cur.execute(
                """
                INSERT INTO parser_records (run_id, source, external_id, payload)
                VALUES (%s::uuid, %s, %s, %s)
                """,
                (self.run_id, self.source, external_id, Json(row)),
            )
        if external_id:
            self._seen_external_ids.add(external_id)
        self._processed += 1

    def finish(self, *, status: str, skipped: int = 0, errors: int = 0, output_path: str = "") -> None:
        metrics = {
            "processed": self._processed,
            "skipped": skipped,
            "errors": errors,
            "output_path": output_path,
        }
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE parser_runs
                SET status = %s, metrics = %s::jsonb
                WHERE run_id = %s::uuid
                """,
                (status, json.dumps(metrics, ensure_ascii=False), self.run_id),
            )

    def close(self) -> None:
        self._conn.close()


def load_lines(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_optional_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_cookie_header(raw_cookie: str, cookie_file: str) -> str:
    cookie = raw_cookie.strip()
    if cookie_file and Path(cookie_file).exists():
        cookie = Path(cookie_file).read_text(encoding="utf-8").strip()
    return cookie


def load_kolesa_sessions(args: argparse.Namespace) -> list[KolesaSession]:
    def clean(value: Any) -> str:
        return str(value or "").strip()

    def build_session(item: dict[str, Any], index: int) -> KolesaSession:
        return KolesaSession(
            name=clean(item.get("name")) or f"session-{index + 1}",
            app_id=clean(item.get("app_id") or item.get("appId")) or args.app_id.strip(),
            app_key=clean(item.get("app_key") or item.get("appKey")) or args.app_key.strip(),
            current_user=clean(item.get("current_user") or item.get("currentUser")) or args.current_user.strip(),
            captcha_token=clean(item.get("captcha_token") or item.get("captchaToken")) or args.captcha_token.strip(),
            auth_token=clean(item.get("auth_token") or item.get("authToken") or item.get("x_auth_token")),
            cookie=clean(item.get("cookie") or item.get("cookies")),
            idfa=clean(item.get("idfa")),
            phone_id=clean(item.get("phone_id") or item.get("phoneId") or item.get("x_phone_id")),
            app_location=clean(item.get("app_location") or item.get("appLocation")),
            app_version=clean(item.get("app_version") or item.get("appVersion")) or args.app_version.strip() or DEFAULT_APP_VERSION,
            app_platform_version=(
                clean(item.get("app_platform_version") or item.get("appPlatformVersion"))
                or args.app_platform_version.strip()
                or DEFAULT_APP_PLATFORM_VERSION
            ),
            app_push_enable=clean(item.get("app_push_enable") or item.get("appPushEnable")) or args.app_push_enable.strip() or DEFAULT_APP_PUSH_ENABLE,
        )

    raw_sessions = args.sessions_json.strip() or DEFAULT_SESSIONS_JSON.strip()
    sessions_path = args.sessions_file.strip() or DEFAULT_SESSIONS_FILE.strip()
    if not raw_sessions and sessions_path and Path(sessions_path).exists():
        raw_sessions = Path(sessions_path).read_text(encoding="utf-8")

    sessions: list[KolesaSession] = []
    if raw_sessions:
        try:
            payload = json.loads(raw_sessions)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid Kolesa sessions JSON: {exc}") from exc
        if isinstance(payload, dict):
            payload = payload.get("sessions", [])
        if not isinstance(payload, list):
            raise ValueError("Kolesa sessions JSON must be a list or an object with sessions list")
        for index, item in enumerate(payload):
            if isinstance(item, dict):
                sessions.append(build_session(item, index))

    if not sessions:
        sessions.append(
            KolesaSession(
                name="env-session",
                app_id=args.app_id.strip(),
                app_key=args.app_key.strip(),
                current_user=args.current_user.strip(),
                captcha_token=args.captcha_token.strip(),
                auth_token=args.auth_token.strip(),
                cookie=load_cookie_header(args.cookie, args.cookie_file),
                idfa=args.idfa.strip(),
                phone_id=args.phone_id.strip(),
                app_location=args.app_location.strip(),
                app_version=args.app_version.strip() or DEFAULT_APP_VERSION,
                app_platform_version=args.app_platform_version.strip() or DEFAULT_APP_PLATFORM_VERSION,
                app_push_enable=args.app_push_enable.strip() or DEFAULT_APP_PUSH_ENABLE,
            )
        )
    return sessions


def build_headers(cookie: str = "") -> dict[str, str]:
    headers = dict(DEFAULT_HEADERS)
    if cookie:
        headers["Cookie"] = cookie
    return headers


def build_phone_api_headers(base_headers: dict[str, str], ad_url: str, session: KolesaSession) -> dict[str, str]:
    if session.auth_token.strip():
        headers = {
            "Accept": "*/*",
            "app-version": session.app_version.strip() or DEFAULT_APP_VERSION,
            "app-language": "ru",
            "app-platform": "ios",
            "APP-PHOTO-FORMAT": "webp",
            "Accept-Language": "ru-KZ;q=1.0, kk-KZ;q=0.9",
            "X-APP-SCREEN-COEFFICIENT": "2.0",
            "app-push-enable": session.app_push_enable.strip() or DEFAULT_APP_PUSH_ENABLE,
            "X-AUTH-TOKEN": session.auth_token.strip(),
            "app-platform-version": session.app_platform_version.strip() or DEFAULT_APP_PLATFORM_VERSION,
            "User-Agent": (
                f"KolesaKz/{session.app_version.strip() or DEFAULT_APP_VERSION} "
                f"(kz.kolesa.advapp; build:2; iOS {session.app_platform_version.strip() or DEFAULT_APP_PLATFORM_VERSION}) "
                "Alamofire/5.9.1"
            ),
        }
        if session.idfa.strip():
            headers["idfa"] = session.idfa.strip()
        if session.phone_id.strip():
            headers["X-PHONE-ID"] = session.phone_id.strip()
        if session.app_location.strip():
            headers["app-location"] = session.app_location.strip()
    else:
        headers = dict(API_HEADERS)

    if base_headers.get("Cookie"):
        headers["Cookie"] = base_headers["Cookie"]
    headers["Referer"] = ad_url
    return headers


class KolesaSessionManager:
    def __init__(self, sessions: list[KolesaSession], *, cooldown_sec: float) -> None:
        self.sessions = sessions or []
        self.cooldown_sec = max(0.0, cooldown_sec)
        self.current_index = 0

    def active_count(self) -> int:
        now = time.time()
        return sum(1 for session in self.sessions if session.unavailable_until <= now)

    def next_session(self) -> KolesaSession | None:
        if not self.sessions:
            return None
        now = time.time()
        for step in range(len(self.sessions)):
            idx = (self.current_index + step) % len(self.sessions)
            session = self.sessions[idx]
            if session.unavailable_until <= now:
                self.current_index = (idx + 1) % len(self.sessions)
                return session
        return None

    def mark_unavailable(self, session: KolesaSession, reason: str) -> None:
        if reason == "captcha_required":
            session.captcha_hits += 1
        elif reason == "auth_required":
            session.auth_hits += 1
        session.unavailable_until = time.time() + self.cooldown_sec
        print(f"  -> kolesa session cooldown: {session.label}, reason={reason}, cooldown={int(self.cooldown_sec)}s")

    def mark_captcha(self, session: KolesaSession) -> None:
        self.mark_unavailable(session, "captcha_required")

    def mark_auth_required(self, session: KolesaSession) -> None:
        self.mark_unavailable(session, "auth_required")

    def base_headers_for(self, session: KolesaSession | None = None) -> dict[str, str]:
        if session is None:
            session = self.sessions[0] if self.sessions else None
        return build_headers(session.cookie if session else "")


def checkpoint_path_for_output(output_path: Path, explicit_path: str = "") -> Path:
    if explicit_path.strip():
        return Path(explicit_path).expanduser().resolve()
    return output_path.with_suffix(output_path.suffix + CHECKPOINT_SUFFIX)


def load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return payload if isinstance(payload, dict) else {}


def save_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def remove_checkpoint(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass


def parse_ad_id(url: str) -> str | None:
    parsed = urlparse(url)
    match = re.search(r"/a/show/(\d+)", parsed.path)
    if match:
        return match.group(1)
    match = re.search(r"/adverts/(\d+)/phones", parsed.path)
    if match:
        return match.group(1)
    return None


def normalize_listing_url(raw_url: str) -> str:
    url = (raw_url or DEFAULT_LISTING_URL).strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://kolesa.kz/{url.lstrip('/')}"
    return url


def page_url_for(listing_url: str, page: int) -> str:
    if page <= 1:
        return listing_url
    sep = "&" if "?" in listing_url else "?"
    return f"{listing_url.rstrip('/')}{sep}page={page}"


def normalize_ad_url(match: tuple[str, str]) -> str:
    ad_id = match[0] or match[1]
    return f"https://kolesa.kz/a/show/{ad_id}"


def extract_listing_ad_urls(html: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for match in AD_RE.findall(html):
        url = normalize_ad_url(match)
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def strip_html(text: Any) -> str:
    text = html_lib.unescape(str(text or ""))
    text = text.replace("\xa0", " ")
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def empty_metadata() -> dict[str, str]:
    return {field: "" for field in METADATA_FIELDS}


def extract_inline_data(page_html: str) -> dict[str, Any]:
    match = INLINE_DATA_RE.search(page_html)
    if not match:
        return {}
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def first_clean_text(*values: Any) -> str:
    for value in values:
        text = strip_html(value)
        if text:
            return text
    return ""


def extract_offer_price(page_html: str) -> str:
    for match in OFFER_PRICE_RE.finditer(page_html):
        price = strip_html(match.group(1))
        if re.search(r"\d", price):
            return price
    return ""


def format_tenge_price(value: Any) -> str:
    text = strip_html(value)
    if not re.search(r"\d", text):
        return ""
    if "₸" in text or "тг" in text.lower():
        return text
    digits = re.sub(r"\D", "", text)
    if not digits:
        return text
    return f"{int(digits):,}".replace(",", " ") + " ₸"


def extract_seller_name_from_data(data: dict[str, Any]) -> str:
    candidates: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        text = strip_html(value)
        if not text:
            return
        lowered = text.lower()
        if lowered in {"контакты продавца", "показать телефон"} or "телефон" in lowered:
            return
        if len(text) > 120 or text in seen:
            return
        seen.add(text)
        candidates.append(text)

    advert = data.get("advert") if isinstance(data.get("advert"), dict) else {}
    for key in ("sellerName", "ownerName", "contactName", "userName", "dealerName", "managerName"):
        add(advert.get(key))

    def walk(value: Any, parent_key: str = "") -> None:
        if isinstance(value, dict):
            parent = parent_key.lower().replace("_", "")
            parent_is_contact = any(token in parent for token in ("seller", "owner", "dealer", "contact", "user"))
            for key, item in value.items():
                normalized_key = str(key).lower().replace("_", "")
                if normalized_key in {"sellername", "ownername", "contactname", "username", "dealername", "managername"}:
                    add(item)
                elif parent_is_contact and normalized_key in {"name", "title", "login", "username", "displayname"}:
                    add(item)
                if isinstance(item, (dict, list)):
                    walk(item, normalized_key)
        elif isinstance(value, list):
            for item in value:
                walk(item, parent_key)

    walk(data)
    return candidates[0] if candidates else ""


def extract_seller_name_from_html(page_html: str) -> str:
    for match in SELLER_HTML_RE.finditer(page_html):
        text = strip_html(match.group(1))
        lowered = text.lower()
        if not text or len(text) > 120:
            continue
        if any(stop_word in lowered for stop_word in ("контакты", "телефон", "написать", "показать")):
            continue
        return text
    return ""


def infer_dealer_name_from_description(description: str, *, is_verified_dealer: bool) -> str:
    if not is_verified_dealer:
        return ""
    match = re.match(
        r"^([A-Za-zА-Яа-яЁё0-9 .,&\"'«»()/-]{3,80}?)\s+"
        r"(?:предлагает|предлагаем|предлагают|представляет|рады предложить|рад предложить)\b",
        description,
        re.IGNORECASE,
    )
    if not match:
        return ""
    return strip_html(match.group(1))


def extract_page_metadata(html: str) -> dict[str, str]:
    metadata = empty_metadata()
    data = extract_inline_data(html)
    advert = data.get("advert") if isinstance(data.get("advert"), dict) else {}
    product = data.get("product") if isinstance(data.get("product"), dict) else {}

    metadata["title"] = first_clean_text(advert.get("title"))
    metadata["description"] = first_clean_text(advert.get("descriptionText"), advert.get("description"))
    metadata["city"] = first_clean_text(advert.get("region"), advert.get("city"), advert.get("location"))
    metadata["seller_name"] = extract_seller_name_from_data(data)
    metadata["price"] = extract_offer_price(html)
    if not metadata["price"]:
        metadata["price"] = format_tenge_price(advert.get("price") or product.get("price") or product.get("unitPrice"))

    if not metadata["title"]:
        metadata["title"] = first_clean_text(product.get("name"))
    if not metadata["title"]:
        title_match = TITLE_RE.search(html)
        if title_match:
            metadata["title"] = strip_html(title_match.group(1))
    if not metadata["description"]:
        description_match = META_DESCRIPTION_RE.search(html)
        if description_match:
            metadata["description"] = strip_html(description_match.group(1))
    if not metadata["seller_name"]:
        metadata["seller_name"] = extract_seller_name_from_html(html)
    if not metadata["seller_name"]:
        metadata["seller_name"] = infer_dealer_name_from_description(
            metadata["description"],
            is_verified_dealer=bool(advert.get("isVerifiedDealer")),
        )
    return metadata


def extract_phones(payload: Any) -> list[str]:
    phones: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        for phone in normalize_phone_numbers(value):
            if phone not in seen:
                seen.add(phone)
                phones.append(phone)

    def walk(value: Any, key_hint: str = "") -> None:
        if value is None:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                key_text = str(key).lower()
                if "phone" in key_text or "тел" in key_text:
                    add(item)
                walk(item, key_text)
            return
        if isinstance(value, list):
            for item in value:
                walk(item, key_hint)
            return
        if isinstance(value, (str, int)):
            text = str(value)
            if "phone" in key_hint or "тел" in key_hint:
                add(text)
                return
            if PHONE_RE.search(text):
                add(text)

    walk(payload)
    return phones


def detect_api_condition(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("isAuthRequired") is True:
        return "auth_required"
    if payload.get("captchaRequired") is True:
        return "captcha_required"
    status = str(payload.get("status", "")).lower()
    if status and status not in {"success", "ok"}:
        return status
    diagnostic_text = " ".join(
        strip_html(payload.get(key, ""))
        for key in ("error", "message", "reason", "description")
        if payload.get(key)
    ).lower()
    if "auth" in diagnostic_text and "required" in diagnostic_text:
        return "auth_required"
    if "captcha" in diagnostic_text and "required" in diagnostic_text:
        return "captcha_required"
    return None


def sleep_between_requests(delay_sec: float, random_delay_min: float, random_delay_max: float) -> None:
    if random_delay_min > 0 or random_delay_max > 0:
        lo = random_delay_min if random_delay_min > 0 else delay_sec
        hi = random_delay_max if random_delay_max > 0 else max(lo, delay_sec)
        time.sleep(max(0.0, random.uniform(min(lo, hi), max(lo, hi))))
    elif delay_sec > 0:
        time.sleep(delay_sec)


def build_driver(*, headless: bool, chrome_binary: str, timeout: float) -> Any:
    if webdriver is None or Options is None:
        raise RuntimeError("Selenium is not installed. Install it with: python -m pip install selenium")
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument(f"--user-agent={DEFAULT_HEADERS['User-Agent']}")
    if chrome_binary:
        options.binary_location = chrome_binary
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(max(timeout, 10.0))
    return driver


def fetch_listing_page_html_selenium(listing_url: str, page: int, *, timeout: float, headless: bool, chrome_binary: str) -> str:
    driver = build_driver(headless=headless, chrome_binary=chrome_binary, timeout=timeout)
    try:
        driver.get(page_url_for(listing_url, page))
        try:
            WebDriverWait(driver, min(max(timeout, 4.0), 12.0)).until(
                lambda drv: bool(extract_listing_ad_urls(drv.page_source))
            )
        except TimeoutException:
            pass
        return driver.page_source
    finally:
        try:
            driver.quit()
        except Exception:  # noqa: BLE001
            pass


def iter_listing_ad_pages(
    listing_url: str,
    limit: int,
    rotator: ProxyRotator,
    base_headers: dict[str, str],
    *,
    attempts_per_page: int = 3,
    empty_page_tolerance: int = 3,
    use_selenium_fallback: bool = False,
    timeout: float = 12.0,
    headless: bool = True,
    chrome_binary: str = "",
):
    seen: set[str] = set()
    page = 1
    collected = 0
    consecutive_empty_pages = 0

    while collected < limit:
        url = page_url_for(listing_url, page)
        html = ""
        last_error: Exception | None = None
        for attempt in range(max(1, attempts_per_page)):
            try:
                result = rotator.request("GET", url, headers=base_headers)
                html = result.response.text
                break
            except RuntimeError as exc:
                last_error = exc
                if attempt + 1 < attempts_per_page:
                    time.sleep(0.8 * (attempt + 1))

        if not html and use_selenium_fallback:
            html = fetch_listing_page_html_selenium(url, 1, timeout=timeout, headless=headless, chrome_binary=chrome_binary)

        if not html:
            if last_error:
                raise last_error
            break

        page_ads = extract_listing_ad_urls(html)
        print(f"[listing] page={page} url={url} ads={len(page_ads)}")
        if not page_ads:
            consecutive_empty_pages += 1
            if consecutive_empty_pages >= empty_page_tolerance:
                break
            page += 1
            continue

        batch: list[str] = []
        for ad_url in page_ads:
            if ad_url in seen:
                continue
            seen.add(ad_url)
            batch.append(ad_url)
            collected += 1
            if collected >= limit:
                break

        if batch:
            consecutive_empty_pages = 0
            yield batch
        else:
            consecutive_empty_pages += 1
            if consecutive_empty_pages >= empty_page_tolerance:
                break
        page += 1


def fetch_ad_metadata(ad_url: str, rotator: ProxyRotator, base_headers: dict[str, str]) -> dict[str, str]:
    try:
        result = rotator.request("GET", ad_url, headers=base_headers, ok_statuses={200})
        return extract_page_metadata(result.response.text)
    except Exception:  # noqa: BLE001
        return empty_metadata()


def fetch_phone_for_ad(
    ad_url: str,
    rotator: ProxyRotator,
    *,
    session_manager: KolesaSessionManager,
    max_session_attempts: int,
    crawlbase_client: CrawlbaseClient | None = None,
) -> dict[str, str]:
    ad_id = parse_ad_id(ad_url)
    if not ad_id:
        return {
            "ad_url": ad_url,
            "ad_id": "",
            **empty_metadata(),
            "phones": "",
            "status": "error",
            "proxy": "",
            "error": "Cannot parse ad id from url",
        }

    first_session = session_manager.next_session()
    if first_session is None:
        return {
            "ad_url": ad_url,
            "ad_id": ad_id,
            **empty_metadata(),
            "phones": "",
            "status": "retry_later",
            "proxy": "",
            "error": "All Kolesa sessions are in cooldown",
        }

    metadata = fetch_ad_metadata(ad_url, rotator, session_manager.base_headers_for(first_session))

    api_url = f"https://app.kolesa.kz/adverts/{ad_id}/phones"
    attempts = max(1, min(max_session_attempts, max(1, len(session_manager.sessions))))
    last_row: dict[str, str] | None = None
    session = first_session

    def phone_params(current_session: KolesaSession) -> dict[str, str]:
        return {
            "appId": current_session.app_id,
            "appKey": current_session.app_key,
            "captchaToken": current_session.captcha_token,
            "currentUser": current_session.current_user,
        }

    def row_for_condition(current_session: KolesaSession, condition: str, proxy_label: str) -> dict[str, str]:
        if condition == "auth_required":
            error = "Authorization is required by kolesa.kz for this phone"
        elif condition == "captcha_required":
            error = "CAPTCHA token is required by kolesa.kz for this phone"
        else:
            error = f"Kolesa API status: {condition}"
        return {
            "ad_url": ad_url,
            "ad_id": ad_id,
            **metadata,
            "phones": "",
            "status": condition,
            "proxy": proxy_label,
            "error": error,
        }

    def try_crawlbase(current_session: KolesaSession, headers: dict[str, str]) -> dict[str, str] | None:
        if crawlbase_client is None or not crawlbase_client.enabled:
            return None
        target_url = f"{api_url}?{urlencode(phone_params(current_session))}"
        try:
            payload, proxy_label = crawlbase_client.request_json(target_url, headers=headers)
        except Exception as exc:  # noqa: BLE001
            print(f"  -> crawlbase fallback failed: {exc}")
            return None
        phones = extract_phones(payload)
        condition = detect_api_condition(payload)
        if condition in {"auth_required", "captcha_required"}:
            print(f"  -> crawlbase fallback challenged: session={current_session.label}, reason={condition}")
            return row_for_condition(current_session, condition, proxy_label)
        if condition and condition not in {"success", "ok"}:
            return row_for_condition(current_session, condition, proxy_label)
        print(f"  -> crawlbase fallback ok: session={current_session.label}, phones={len(phones)}")
        return {
            "ad_url": ad_url,
            "ad_id": ad_id,
            **metadata,
            "phones": ";".join(phones),
            "status": "ok" if phones else "no_phone",
            "proxy": proxy_label,
            "error": "",
        }

    for attempt in range(1, attempts + 1):
        if session is None:
            break
        base_headers = session_manager.base_headers_for(session)
        headers = build_phone_api_headers(base_headers, ad_url, session)
        try:
            result = rotator.request(
                "GET",
                api_url,
                headers=headers,
                params=phone_params(session),
                ok_statuses={200},
            )
            payload = result.response.json()
            phones = extract_phones(payload)
            condition = detect_api_condition(payload)

            if condition == "auth_required":
                fallback_row = try_crawlbase(session, headers)
                if fallback_row and fallback_row.get("status") not in {"auth_required", "captcha_required"}:
                    return fallback_row
                session_manager.mark_auth_required(session)
                last_row = fallback_row or row_for_condition(session, condition, result.proxy)
                session = session_manager.next_session()
                continue
            if condition == "captcha_required":
                fallback_row = try_crawlbase(session, headers)
                if fallback_row and fallback_row.get("status") not in {"auth_required", "captcha_required"}:
                    return fallback_row
                session_manager.mark_captcha(session)
                last_row = fallback_row or row_for_condition(session, condition, result.proxy)
                session = session_manager.next_session()
                continue
            if condition and condition not in {"success", "ok"}:
                return {
                    "ad_url": ad_url,
                    "ad_id": ad_id,
                    **metadata,
                    "phones": "",
                    "status": "error",
                    "proxy": result.proxy,
                    "error": f"Kolesa API status: {condition}",
                }

            return {
                "ad_url": ad_url,
                "ad_id": ad_id,
                **metadata,
                "phones": ";".join(phones),
                "status": "ok" if phones else "no_phone",
                "proxy": result.proxy,
                "error": "",
            }
        except Exception as exc:  # noqa: BLE001
            fallback_row = try_crawlbase(session, headers)
            if fallback_row:
                if fallback_row.get("status") not in {"auth_required", "captcha_required"}:
                    return fallback_row
                if fallback_row.get("status") == "auth_required":
                    session_manager.mark_auth_required(session)
                elif fallback_row.get("status") == "captcha_required":
                    session_manager.mark_captcha(session)
                last_row = fallback_row
                session = session_manager.next_session()
                continue
            return {
                "ad_url": ad_url,
                "ad_id": ad_id,
                **metadata,
                "phones": "",
                "status": "error",
                "proxy": "",
                "error": str(exc),
            }

    if last_row:
        last_row["status"] = "retry_later" if last_row.get("status") in {"captcha_required", "auth_required"} else last_row.get("status", "error")
        last_row["error"] = f"{last_row.get('error', 'Kolesa session unavailable')}; all available sessions are in cooldown"
        return last_row
    return {
        "ad_url": ad_url,
        "ad_id": ad_id,
        **metadata,
        "phones": "",
        "status": "retry_later",
        "proxy": "",
        "error": "All Kolesa sessions are in cooldown",
    }


def save_csv(rows: list[dict[str, str]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ROW_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def save_json(rows: list[dict[str, str]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kolesa phone collector")
    parser.add_argument("--ads-file", default="", help="Path to file with one ad URL per line")
    parser.add_argument("--ad-url", default="", help="Single Kolesa ad URL")
    parser.add_argument("--listing-url", default=DEFAULT_LISTING_URL, help="Kolesa listing URL")
    parser.add_argument("--listing-limit", type=int, default=10, help="How many ads to parse")
    parser.add_argument("--proxies-file", default="proxyscrape_premium_http_proxies.txt", help="Proxy list file")
    parser.add_argument("--proxy-blacklist-file", default="proxy_blacklist.txt", help="Bad proxy list file")
    parser.add_argument("--no-proxy", action="store_true", help="Run directly without proxy list")
    parser.add_argument("--output", default="kolesa_results.csv", help="Output CSV file")
    parser.add_argument("--json-output", default="", help="Optional JSON output")
    parser.add_argument("--checkpoint-file", default="", help="Path to resume checkpoint JSON")
    parser.add_argument("--database-url", default="", help="PostgreSQL DSN for live per-record insert")
    parser.add_argument("--cookie", default=DEFAULT_COOKIE, help="Cookie header string for authenticated Kolesa session")
    parser.add_argument("--cookie-file", default=DEFAULT_COOKIE_FILE, help="Path to file with Kolesa cookie header")
    parser.add_argument("--timeout", type=float, default=12.0, help="HTTP timeout per request")
    parser.add_argument("--delay", type=float, default=0.7, help="Delay between ads")
    parser.add_argument("--random-delay-min", type=float, default=1.2, help="Minimum random delay")
    parser.add_argument("--random-delay-max", type=float, default=3.5, help="Maximum random delay")
    parser.add_argument("--driver", choices=["http", "selenium"], default="http", help="Listing fallback driver")
    parser.add_argument("--headless", dest="headless", action="store_true", help="Run Selenium headless")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="Run Selenium visible")
    parser.add_argument("--chrome-binary", default="", help="Chrome/Chromium binary path")
    parser.add_argument("--app-id", default=DEFAULT_APP_ID, help="Kolesa phones API appId")
    parser.add_argument("--app-key", default=DEFAULT_APP_KEY, help="Kolesa phones API appKey")
    parser.add_argument("--current-user", default=DEFAULT_CURRENT_USER, help="Kolesa phones API currentUser")
    parser.add_argument("--captcha-token", default=DEFAULT_CAPTCHA_TOKEN, help="Optional captchaToken for phones API")
    parser.add_argument("--auth-token", default=DEFAULT_AUTH_TOKEN, help="Optional Kolesa mobile X-AUTH-TOKEN")
    parser.add_argument("--idfa", default=DEFAULT_IDFA, help="Optional Kolesa mobile idfa header")
    parser.add_argument("--phone-id", default=DEFAULT_PHONE_ID, help="Optional Kolesa mobile X-PHONE-ID header")
    parser.add_argument("--app-location", default=DEFAULT_APP_LOCATION, help="Optional Kolesa mobile app-location header")
    parser.add_argument("--app-version", default=DEFAULT_APP_VERSION, help="Kolesa mobile app-version header")
    parser.add_argument("--app-platform-version", default=DEFAULT_APP_PLATFORM_VERSION, help="Kolesa mobile app-platform-version header")
    parser.add_argument("--app-push-enable", default=DEFAULT_APP_PUSH_ENABLE, help="Kolesa mobile app-push-enable header")
    parser.add_argument("--sessions-json", default=DEFAULT_SESSIONS_JSON, help="JSON list with Kolesa mobile sessions")
    parser.add_argument("--sessions-file", default=DEFAULT_SESSIONS_FILE, help="Path to JSON file with Kolesa mobile sessions")
    parser.add_argument("--session-cooldown-sec", type=float, default=DEFAULT_SESSION_COOLDOWN_SEC, help="Cooldown for a Kolesa session after captcha/auth")
    parser.add_argument("--phone-max-session-attempts", type=int, default=20, help="Max session rotation attempts per advert phone")
    parser.add_argument("--crawlbase-token", default=DEFAULT_CRAWLBASE_TOKEN, help="Optional Crawlbase token for phone API fallback")
    parser.add_argument("--crawlbase-js-token", default=DEFAULT_CRAWLBASE_JS_TOKEN, help="Optional Crawlbase JS token for phone API fallback")
    parser.add_argument(
        "--verify-ssl",
        dest="verify_ssl",
        action="store_true",
        help="Verify SSL certificates for Kolesa requests",
    )
    parser.add_argument(
        "--insecure-ssl",
        dest="verify_ssl",
        action="store_false",
        help="Disable SSL verification for Kolesa requests",
    )
    parser.add_argument("--fetch-metadata", action="store_true", help="Compatibility option; metadata is always fetched")
    parser.add_argument("--shuffle", action="store_true", help="Shuffle ad URLs before processing")
    parser.set_defaults(headless=True, verify_ssl=os.environ.get("KOLESA_VERIFY_SSL", "false").strip().lower() in {"1", "true", "yes", "on"})
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_path = Path(args.output)
    checkpoint_path = checkpoint_path_for_output(output_path, args.checkpoint_file)
    db_url = (
        args.database_url.strip()
        or os.environ.get("PARSER_LIVE_DB_URL", "").strip()
        or os.environ.get("DATABASE_URL", "").strip()
    )
    db_run_id = os.environ.get("PARSER_LIVE_DB_RUN_ID", "").strip()
    db_mode = os.environ.get("PARSER_LIVE_DB_MODE", "").strip().lower()
    explicit_db_arg = bool(args.database_url.strip())
    live_db_enabled = bool(db_url) and (db_mode in {"1", "true", "yes", "on"} or explicit_db_arg)
    live_db_writer: LiveDbWriter | None = None
    if live_db_enabled:
        live_db_writer = LiveDbWriter(db_url, source="kolesa", run_id=db_run_id)
        print(f"[db] live mode enabled run_id={live_db_writer.run_id}")

    proxies = [DIRECT_PROXY] if args.no_proxy else load_lines(Path(args.proxies_file))
    blocked_proxies = set() if args.no_proxy else set(load_optional_lines(Path(args.proxy_blacklist_file)))
    rotator = ProxyRotator(
        proxies=proxies,
        timeout=args.timeout,
        blocked_proxies=blocked_proxies,
        verify_ssl=bool(args.verify_ssl),
    )
    sessions = load_kolesa_sessions(args)
    session_manager = KolesaSessionManager(sessions, cooldown_sec=float(args.session_cooldown_sec))
    crawlbase_token = args.crawlbase_token.strip() or args.crawlbase_js_token.strip()
    crawlbase_client = CrawlbaseClient(crawlbase_token, timeout=args.timeout, verify_ssl=bool(args.verify_ssl)) if crawlbase_token else None
    base_headers = session_manager.base_headers_for()
    print(f"[kolesa] mobile sessions loaded: {len(sessions)}, active={session_manager.active_count()}")
    print(f"[kolesa] crawlbase fallback: {'enabled' if crawlbase_client else 'disabled'}")
    listing_url = normalize_listing_url(args.listing_url)
    rows: list[dict[str, str]] = []
    resume_state = load_checkpoint(checkpoint_path)

    ads: list[str] = []
    if args.ads_file:
        ads.extend(load_lines(Path(args.ads_file)))
    if args.ad_url:
        ads.append(args.ad_url.strip())
    if args.shuffle and len(ads) > 1:
        random.shuffle(ads)

    def persist_checkpoint(ad_index: int, source_ads: list[str]) -> None:
        save_checkpoint(
            checkpoint_path,
            {
                "version": 1,
                "source": "kolesa",
                "listing_url": listing_url,
                "ads": source_ads,
                "ad_index": ad_index,
                "rows": rows,
                "updated_at": time.time(),
            },
        )

    def parse_batch(batch_ads: list[str], total_target: int, start_label: int = 0) -> None:
        total = total_target
        start_index = 0
        if resume_state:
            saved_ads = resume_state.get("ads", [])
            saved_rows = resume_state.get("rows", [])
            if isinstance(saved_ads, list) and saved_ads == batch_ads and isinstance(saved_rows, list):
                rows.extend(row for row in saved_rows if isinstance(row, dict))
                start_index = max(0, min(int(resume_state.get("ad_index", 0)), len(batch_ads)))
                if rows:
                    print(f"  -> resume checkpoint loaded: rows={len(rows)}, next={start_index + 1}")

        for local_idx, ad_url in enumerate(batch_ads[start_index:], start=start_index + 1):
            absolute_idx = start_label + local_idx
            print(f"[{absolute_idx}/{total}] {ad_url}")
            row = fetch_phone_for_ad(
                ad_url,
                rotator,
                session_manager=session_manager,
                max_session_attempts=max(1, int(args.phone_max_session_attempts)),
                crawlbase_client=crawlbase_client,
            )
            rows.append(row)
            if live_db_writer:
                live_db_writer.insert_row(row)
            phones = row.get("phones") or "-"
            proxy = row.get("proxy") or "-"
            print(f"  -> status={row.get('status')}, proxy={proxy}, phones={phones}")
            if row.get("error"):
                print(f"  -> error={row['error']}")
            print(f"[progress] {len(rows)}/{total}")
            persist_checkpoint(local_idx, batch_ads)
            if len(rows) < total:
                sleep_between_requests(args.delay, args.random_delay_min, args.random_delay_max)

    if ads:
        parse_batch(ads, len(ads))
    else:
        limit = max(1, int(args.listing_limit))
        collected = 0
        page_count = 0
        for page_ads in iter_listing_ad_pages(
            listing_url,
            limit,
            rotator,
            base_headers,
            attempts_per_page=1 if args.no_proxy else 3,
            use_selenium_fallback=args.driver == "selenium",
            timeout=args.timeout,
            headless=args.headless,
            chrome_binary=args.chrome_binary.strip(),
        ):
            page_count += 1
            remaining = limit - len(rows)
            batch = page_ads[:remaining]
            collected += len(batch)
            print(f"Collected page {page_count} with {len(batch)} ads. Parsing now...")
            parse_batch(batch, limit, start_label=len(rows))
            if len(rows) >= limit:
                break
        if not rows:
            raise ValueError(f"No ads found on listing page: {listing_url}")
        print(f"Collected {len(rows)} ads from listing pages.")

    save_csv(rows, output_path)
    print(f"Saved CSV: {output_path.resolve()}")
    if args.json_output:
        json_path = Path(args.json_output)
        save_json(rows, json_path)
        print(f"Saved JSON: {json_path.resolve()}")

    if live_db_writer:
        skipped = sum(1 for row in rows if row.get("status") == "skipped")
        errors = sum(1 for row in rows if row.get("status") in {"error", "captcha_required", "auth_required", "retry_later"})
        live_db_writer.finish(
            status="completed",
            skipped=skipped,
            errors=errors,
            output_path=str(output_path.resolve()),
        )
        print(f"[db] live save completed run_id={live_db_writer.run_id}, records={len(rows)}")
        live_db_writer.close()

    remove_checkpoint(checkpoint_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
