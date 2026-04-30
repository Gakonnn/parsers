
#!/usr/bin/env python3
"""Collect phone numbers from krisha.kz ads using proxy failover.

Usage example:
  python3 krisha_phone_parser.py \
    --ads-file ads.txt \
    --proxies-file proxyscrape_premium_http_proxies.txt \
    --output results.csv \
    --cookie "krishauid=...; krssid=..." \
    --driver selenium
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import random
import re
import shutil
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import ProxyHandler, Request, build_opener

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from unified_parsers.phone_utils import normalize_phone_number, normalize_phone_numbers

try:
    from selenium import webdriver
    from selenium.common.exceptions import InvalidArgumentException, NoSuchElementException, TimeoutException, WebDriverException
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
except ModuleNotFoundError:
    webdriver = None
    class _SeleniumUnavailableError(Exception):
        """Fallback Selenium exception type used when selenium package is missing."""

    InvalidArgumentException = NoSuchElementException = SessionNotCreatedException = _SeleniumUnavailableError
    TimeoutException = WebDriverException = _SeleniumUnavailableError
    Options = Service = By = Keys = EC = WebDriverWait = None

try:
    import psycopg2
    from psycopg2.extras import Json
except ModuleNotFoundError:  # pragma: no cover
    psycopg2 = None
    Json = None

SHOW_URL_RE = re.compile(r"https?://(?:(?:www|m)\.)?krisha\.kz/a/show/(\d+)", re.IGNORECASE)
LISTING_AD_RE = re.compile(r'href="(https?://krisha\.kz/a/show/\d+[^"#]*|/a/show/\d+[^"#]*)"', re.IGNORECASE)
PHONE_RE = re.compile(r"\+?\d[\d\s()\-]{7,}\d")
TOKEN_PATTERNS = [
    re.compile(r'"v3Token"\s*:\s*"([^"]+)"'),
    re.compile(r"v3Token\\u0022:\\u0022([^\\]+)"),
    re.compile(r"data-v3-token=\"([^\"]+)\""),
    re.compile(r"v3Token\s*=\s*'([^']+)'"),
    re.compile(r'v3Token\s*=\s*"([^"]+)"'),
]

DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-KZ,ru;q=0.9,en;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/147.0.0.0 Safari/537.36"
    ),
}
DEFAULT_CHAT_APP_ID = "827741382230"
DEFAULT_CHAT_APP_KEY = "0f886a79655ffbfff79f247d3add8ac3"
DEFAULT_CHAT_CURRENT_USER = "20822821@auto.kolesa.kz"

AJAX_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
}

LOGIN_URL = "https://id.kolesa.kz/login"
LOGIN_FIELD_XPATHS = [
    "//input[@type='tel']",
    "//input[contains(@name, 'login')]",
    "//input[contains(@autocomplete, 'username')]",
    "//input[@type='email']",
    "//input[contains(@placeholder, 'тел')]",
]
PASSWORD_FIELD_XPATHS = [
    "//input[@type='password']",
    "//input[contains(@name, 'password')]",
    "//input[contains(@autocomplete, 'current-password')]",
]
LOGIN_SUBMIT_XPATHS = [
    "//button[@type='submit']",
    "//button[contains(., 'Войти')]",
    "//button[contains(., 'Вход')]",
    "//input[@type='submit']",
]
AUTH_SUCCESS_XPATHS = [
    "//a[contains(., 'Личный кабинет')]",
    "//a[contains(., 'Мой кабинет')]",
    "//a[contains(., 'Профиль')]",
    "//button[contains(., 'Выйти')]",
    "//a[contains(., 'Выйти')]",
]
CAPTCHA_XPATH_CANDIDATES = [
    "//iframe[contains(@src, 'recaptcha')]",
    "//*[contains(@class, 'g-recaptcha')]",
    "//*[contains(@class, 'recaptcha')]",
    "//*[contains(text(), 'Я не робот')]",
    "//*[contains(text(), 'Подтвердите, что вы не робот')]",
]
AUTH_REQUIRED_XPATHS = [
    "//*[contains(text(), 'Необходимо авторизоваться')]",
    "//*[contains(text(), 'Войдите, чтобы')]",
    "//*[contains(text(), 'Требуется авторизация')]",
]
SHOW_PHONE_XPATHS = [
    "//button[@data-test='mes__show-phones-button']",
    "//button[contains(@class, 'mes-ui-button') and @data-test='mes__show-phones-button']",
    "//button[contains(., 'Позвонить')]",
    "//a[contains(., 'Позвонить')]",
    "//*[@role='button'][contains(., 'Позвонить')]",
    "//button[contains(., 'Показать номер')]",
    "//button[contains(., 'Показать телефон')]",
    "//a[contains(., 'Показать номер')]",
    "//a[contains(., 'Показать телефон')]",
    "//*[@role='button'][contains(., 'Показать номер')]",
    "//*[@role='button'][contains(., 'Показать телефон')]",
    "//*[contains(@class, 'show-phone') or contains(@class, 'phone-show')]",
    "//*[self::button or self::a or @role='button'][.//*[contains(text(), 'Показать номер')]]",
    "//*[self::button or self::a or @role='button'][.//*[contains(text(), 'Показать телефон')]]",
    "//*[contains(@aria-label, 'Показать номер') or contains(@title, 'Показать номер')]",
    "//*[contains(@aria-label, 'Показать телефон') or contains(@title, 'Показать телефон')]",
]
MOBILE_CALL_BUTTON_XPATHS = [
    "//button[contains(@class, 'a-call-btn')]",
    "//button[contains(@class, 'kr-btn') and contains(@class, 'a-call-btn')]",
    "//button[normalize-space()='Позвонить']",
]
MOBILE_PHONE_MODAL_LINKS_XPATH = "//*[contains(@class, 'phones-modal__items')]//a[starts-with(@href, 'tel:')]"
MESSAGE_BUTTON_XPATHS = [
    "//button[contains(., 'Написать сообщение')]",
    "//a[contains(., 'Написать сообщение')]",
    "//*[@role='button'][contains(., 'Написать сообщение')]",
    "//button[contains(., 'Написать')]",
    "//a[contains(., 'Написать')]",
    "//*[@role='button'][contains(., 'Написать')]",
    "//*[self::button or self::a or @role='button'][.//*[contains(text(), 'Написать сообщение')]]",
    "//*[contains(@aria-label, 'Написать сообщение') or contains(@title, 'Написать сообщение')]",
]
MESSAGE_PAGE_XPATHS = [
    "//*[contains(., 'Показать номер')]",
    "//*[contains(., 'Сообщение')]",
    "//*[contains(., 'Чат')]",
    "//*[contains(@class, 'chat')]",
    "//*[contains(@class, 'message')]",
    "//textarea",
]
MESSAGE_INPUT_XPATHS = [
    "//textarea",
    "//input[@type='text']",
    "//*[@contenteditable='true']",
    "//*[contains(@class, 'input') and @contenteditable='true']",
    "//*[contains(@placeholder, 'Сообщение')]",
    "//*[contains(@placeholder, 'сообщение')]",
]
MESSAGE_SEND_XPATHS = [
    "//button[@type='submit']",
    "//button[contains(., 'Отправить')]",
    "//button[contains(., 'отправить')]",
    "//button[contains(@class, 'send')]",
    "//button[contains(@class, 'message-send')]",
    "//*[@role='button'][contains(., 'Отправить')]",
]
PHONE_XPATH_CANDIDATES = [
    "//*[self::a or self::button][contains(@href, 'tel:')]",
    "//*[contains(@class, 'phone') or contains(@class, 'offer__phone')]",
    "//*[contains(text(), '+7') or contains(text(), '8 (') or contains(text(), '7 (')]",
]
SELLER_NAME_XPATHS = [
    "//*[@data-test='mes__contact-name']",
    "//*[@data-test='mes__seller-name']",
    "//*[contains(@class, 'contact-name')]",
    "//*[contains(@class, 'seller-name')]",
    "//*[contains(@class, 'chat-user-name')]",
    "//aside//*[self::h1 or self::h2 or self::h3 or self::a or self::span][normalize-space()]",
]
DEFAULT_CHROME_BINARIES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]
DIRECT_PROXY = "__DIRECT__"
DEFAULT_LISTING_URL = "https://krisha.kz/prodazha/kvartiry/"
DEFAULT_CHROME_USER_DATA_DIR = str(Path.home() / "Library/Application Support/Google/Chrome")
DEFAULT_CHROME_PROFILE_DIRECTORY = "Default"
CHECKPOINT_SUFFIX = ".checkpoint.json"


class ProxyUnavailableError(RuntimeError):
    pass


class LiveDbWriter:
    def __init__(self, database_url: str, *, source: str = "krisha", run_id: str = "") -> None:
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
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_parser_records_run_id ON parser_records (run_id)"
            )

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
                    SELECT 1
                    FROM parser_records
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


class ProxyRotator:
    def __init__(self, proxies: list[str], timeout: float = 12.0, blocked_proxies: set[str] | None = None):
        if not proxies:
            raise ValueError("Proxy list is empty")
        self.proxies = proxies
        self.timeout = timeout
        self.current_index = 0
        self.blocked_proxies = blocked_proxies or set()

    @staticmethod
    def _to_proxy_url(raw_proxy: str) -> str:
        if raw_proxy == DIRECT_PROXY:
            return ""
        if "://" in raw_proxy:
            return raw_proxy
        return f"http://{raw_proxy}"

    def _request_once(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        proxy: str,
    ) -> HttpResponse:
        proxy_url = self._to_proxy_url(proxy)
        if proxy_url:
            opener = build_opener(ProxyHandler({"http": proxy_url, "https": proxy_url}))
        else:
            opener = build_opener()
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
        retry_statuses = retry_statuses or {403, 407, 429, 500, 502, 503, 504}

        if params:
            q = urlencode(params)
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{q}"

        req_headers = headers or {}
        start = self.current_index
        n = len(self.proxies)
        last_error: Exception | None = None

        for step in range(n):
            idx = (start + step) % n
            proxy = self.proxies[idx]

            try:
                resp = self._request_once(method, url, req_headers, proxy)
            except URLError as exc:
                last_error = exc
                continue
            except TimeoutError as exc:
                last_error = exc
                continue
            except OSError as exc:
                last_error = exc
                continue

            if resp.status_code in ok_statuses:
                self.current_index = idx
                return ProxyResult(response=resp, proxy=proxy)

            if resp.status_code in retry_statuses:
                continue

            raise RuntimeError(f"Request failed with status {resp.status_code}")

        if last_error:
            raise RuntimeError(f"All proxies failed, last error: {last_error}") from last_error
        raise RuntimeError("All proxies failed with non-success status")

    def proxy_cycle(self):
        start = self.current_index
        n = len(self.proxies)
        for step in range(n):
            idx = (start + step) % n
            proxy = self.proxies[idx]
            if proxy in self.blocked_proxies:
                continue
            yield idx, proxy

    def block_proxy(self, proxy: str) -> None:
        if proxy and proxy != DIRECT_PROXY:
            self.blocked_proxies.add(proxy)


def load_lines(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_optional_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_unique_line(path: Path, value: str) -> None:
    if not value or value == DIRECT_PROXY:
        return
    existing = set(load_optional_lines(path))
    if value in existing:
        return
    with path.open("a", encoding="utf-8") as f:
        if path.stat().st_size > 0:
            f.write("\n")
        f.write(value)


def parse_ad_id(url: str) -> str | None:
    m = SHOW_URL_RE.search(url)
    if m:
        return m.group(1)

    parsed = urlparse(url)
    if parsed.path.endswith("/ajaxPhones"):
        q = parse_qs(parsed.query)
        ad_ids = q.get("id")
        if ad_ids and ad_ids[0].isdigit():
            return ad_ids[0]
    return None


def normalize_listing_ad_url(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"https://krisha.kz{url}"


def prompt_listing_limit() -> int:
    while True:
        raw = input(f"Сколько объявлений парсить с {DEFAULT_LISTING_URL}? ").strip()
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
        print("Введите положительное число, например 10.")


def extract_listing_ad_urls(html: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for match in LISTING_AD_RE.findall(html):
        url = normalize_listing_ad_url(match)
        ad_id = parse_ad_id(url)
        if not ad_id:
            continue
        canonical = f"https://krisha.kz/a/show/{ad_id}"
        if canonical in seen:
            continue
        seen.add(canonical)
        urls.append(canonical)
    return urls


def fetch_ads_from_listing(
    listing_url: str,
    limit: int,
    rotator: ProxyRotator,
    base_headers: dict[str, str],
    *,
    attempts_per_page: int = 3,
) -> list[str]:
    ads: list[str] = []
    seen: set[str] = set()
    page = 1

    while len(ads) < limit:
        page_url = listing_url if page == 1 else f"{listing_url.rstrip('/')}/?page={page}"
        last_error: Exception | None = None
        result: ProxyResult | None = None
        for attempt in range(max(1, attempts_per_page)):
            try:
                result = rotator.request("GET", page_url, headers=base_headers)
                break
            except RuntimeError as exc:
                last_error = exc
                if attempt + 1 >= attempts_per_page:
                    raise
                time.sleep(0.8 * (attempt + 1))
        if result is None:
            if last_error:
                raise last_error
            break
        page_ads = extract_listing_ad_urls(result.response.text)
        if not page_ads:
            break
        added_on_page = 0
        for url in page_ads:
            if url in seen:
                continue
            seen.add(url)
            ads.append(url)
            added_on_page += 1
            if len(ads) >= limit:
                break
        if added_on_page == 0:
            break
        page += 1

    return ads[:limit]


def fetch_ads_from_listing_selenium(
    listing_url: str,
    limit: int,
    *,
    browser: str,
    timeout: float,
    headless: bool,
    chrome_binary: str,
    chrome_user_data_dir: str,
    chrome_profile_directory: str,
    cookie: str,
    cookie_base_file: str,
) -> list[str]:
    driver = None
    ads: list[str] = []
    seen: set[str] = set()
    page = 1

    try:
        driver = build_driver(
            browser,
            DIRECT_PROXY,
            timeout=timeout,
            headless=headless,
            chrome_binary=chrome_binary,
            chrome_user_data_dir=chrome_user_data_dir,
            chrome_profile_directory=chrome_profile_directory,
        )
        browser_cookies = load_browser_cookies(cookie_json_path(cookie_base_file))
        inject_cookies(driver, cookie, browser_cookies)

        while len(ads) < limit:
            page_url = listing_url if page == 1 else f"{listing_url.rstrip('/')}/?page={page}"
            if not safe_get(driver, page_url, timeout_override=max(timeout, 15.0)):
                break
            try:
                WebDriverWait(driver, min(max(timeout, 4.0), 12.0)).until(
                    lambda drv: bool(extract_listing_ad_urls(drv.page_source))
                )
            except TimeoutException:
                pass
            page_ads = extract_listing_ad_urls(driver.page_source)
            if not page_ads:
                break
            added_on_page = 0
            for url in page_ads:
                if url in seen:
                    continue
                seen.add(url)
                ads.append(url)
                added_on_page += 1
                if len(ads) >= limit:
                    break
            if added_on_page == 0:
                break
            page += 1
    finally:
        if driver is not None:
            cleanup_driver(driver)

    return ads[:limit]


def parse_ajax_params(url: str) -> tuple[str | None, str | None]:
    parsed = urlparse(url)
    if not parsed.path.endswith("/ajaxPhones"):
        return None, None
    q = parse_qs(parsed.query)
    ad_id = q.get("id", [None])[0]
    token = q.get("v3Token", [None])[0]
    return ad_id, token


def extract_v3token(html: str) -> str | None:
    for pattern in TOKEN_PATTERNS:
        m = pattern.search(html)
        if m:
            return m.group(1)
    return None


def deep_values(obj: Any):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from deep_values(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from deep_values(item)


def extract_phones(data: Any) -> list[str]:
    phones: set[str] = set()

    if isinstance(data, str):
        phones.update(PHONE_RE.findall(data))

    if isinstance(data, dict):
        for key, value in deep_values(data):
            if isinstance(value, str):
                if "phone" in str(key).lower() or "тел" in str(key).lower():
                    matches = PHONE_RE.findall(value)
                    if matches:
                        phones.update(matches)
                    elif value.strip() and any(ch.isdigit() for ch in value):
                        phones.add(value.strip())
                else:
                    phones.update(PHONE_RE.findall(value))

    normalized = sorted({phone for p in phones for phone in normalize_phone_numbers(p)})
    return normalized


def detect_api_condition(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None

    error_text = str(payload.get("error", "")).lower()
    if "авториз" in error_text or "необходимо авторизоваться" in error_text:
        return "auth_required"

    recaptcha = payload.get("gRecaptcha")
    if isinstance(recaptcha, dict) and recaptcha:
        return "captcha_required"

    return None


def build_base_headers(cookie: str | None) -> dict[str, str]:
    headers = dict(DEFAULT_HEADERS)
    if cookie:
        headers["Cookie"] = cookie
    return headers


def ensure_selenium_available() -> None:
    if webdriver is None:
        raise RuntimeError(
            "Selenium is not installed. Install it with: python3 -m pip install selenium"
        )


def parse_cookie_header(cookie_header: str) -> list[dict[str, str]]:
    cookies: list[dict[str, str]] = []
    for part in cookie_header.split(";"):
        chunk = part.strip()
        if not chunk or "=" not in chunk:
            continue
        name, value = chunk.split("=", 1)
        name = name.strip()
        if not name:
            continue
        cookies.append({"name": name, "value": value.strip()})
    return cookies


def build_chrome_options(
    proxy: str,
    *,
    headless: bool,
    user_agent: str,
    chrome_binary: str,
    chrome_user_data_dir: str,
    chrome_profile_directory: str,
) -> Options:
    options = Options()
    options.page_load_strategy = "eager"
    if chrome_binary:
        options.binary_location = chrome_binary
    if chrome_user_data_dir:
        options.add_argument(f"--user-data-dir={chrome_user_data_dir}")
    if chrome_profile_directory:
        options.add_argument(f"--profile-directory={chrome_profile_directory}")
    if proxy != DIRECT_PROXY:
        options.add_argument(f"--proxy-server=http://{proxy}")
    options.add_argument(f"--user-agent={user_agent}")
    options.add_argument("--window-size=1440,1200")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--lang=ru-RU")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    if headless:
        options.add_argument("--headless=new")
    return options


def resolve_chrome_binary(explicit_binary: str) -> str:
    if explicit_binary:
        return explicit_binary
    for candidate in DEFAULT_CHROME_BINARIES:
        if Path(candidate).exists():
            return candidate
    return ""


def prepare_chrome_profile(
    chrome_user_data_dir: str,
    chrome_profile_directory: str,
) -> tuple[str, str, str]:
    if not chrome_user_data_dir:
        return "", chrome_profile_directory, ""

    source_root = Path(chrome_user_data_dir)
    if not source_root.exists():
        raise RuntimeError(f"Chrome user data dir not found: {source_root}")

    profile_name = chrome_profile_directory or DEFAULT_CHROME_PROFILE_DIRECTORY
    source_profile = source_root / profile_name
    if not source_profile.exists():
        raise RuntimeError(f"Chrome profile directory not found: {source_profile}")

    temp_root = Path(tempfile.mkdtemp(prefix="krisha-chrome-profile-"))
    target_profile = temp_root / profile_name
    shutil.copytree(source_profile, target_profile, dirs_exist_ok=True)

    local_state = source_root / "Local State"
    if local_state.exists():
        shutil.copy2(local_state, temp_root / "Local State")

    first_run = source_root / "First Run"
    if first_run.exists():
        shutil.copy2(first_run, temp_root / "First Run")

    return str(temp_root), profile_name, str(temp_root)


def inject_cookies(driver: Any, cookie_header: str, browser_cookies: list[dict[str, Any]] | None = None) -> None:
    browser_cookies = browser_cookies or []

    if browser_cookies:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for cookie in browser_cookies:
            domain_raw = str(cookie.get("domain") or "").strip()
            domain = domain_raw.lstrip(".")
            if not domain:
                continue
            grouped.setdefault(domain, []).append(cookie)

        for domain, cookies in grouped.items():
            safe_get(driver, f"https://{domain}/")
            for cookie in cookies:
                payload: dict[str, Any] = {
                    "name": cookie.get("name"),
                    "value": cookie.get("value"),
                    "domain": cookie.get("domain") or f".{domain}",
                    "path": cookie.get("path") or "/",
                }
                expiry = cookie.get("expiry")
                if isinstance(expiry, (int, float)):
                    payload["expiry"] = int(expiry)
                if isinstance(cookie.get("secure"), bool):
                    payload["secure"] = cookie["secure"]
                if isinstance(cookie.get("httpOnly"), bool):
                    payload["httpOnly"] = cookie["httpOnly"]
                if isinstance(cookie.get("sameSite"), str) and cookie["sameSite"] in {"Strict", "Lax", "None"}:
                    payload["sameSite"] = cookie["sameSite"]
                if not payload.get("name") or payload.get("value") is None:
                    continue
                try:
                    driver.add_cookie(payload)
                except (InvalidArgumentException, WebDriverException):
                    continue

    if not cookie_header:
        return
    safe_get(driver, "https://krisha.kz/")
    for cookie in parse_cookie_header(cookie_header):
        payload = {
            "name": cookie["name"],
            "value": cookie["value"],
            "domain": ".krisha.kz",
            "path": "/",
        }
        try:
            driver.add_cookie(payload)
        except (InvalidArgumentException, WebDriverException):
            continue


def dump_cookies_to_header(driver: Any) -> str:
    parts: list[str] = []
    for cookie in driver.get_cookies():
        name = cookie.get("name")
        value = cookie.get("value")
        if name and value is not None:
            parts.append(f"{name}={value}")
    return "; ".join(parts)


def save_cookie_header(cookie_header: str, out_path: str) -> None:
    if not out_path or not cookie_header.strip():
        return
    try:
        Path(out_path).write_text(cookie_header, encoding="utf-8")
    except OSError as exc:
        print(f"Warning: could not save cookie header to {out_path}: {exc}")


def cookie_json_path(path_str: str) -> str:
    if not path_str:
        return ""
    return str(Path(path_str).with_suffix(".json"))


def load_browser_cookies(path_str: str) -> list[dict[str, Any]]:
    if not path_str:
        return []
    path = Path(path_str)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def save_browser_cookies(cookies: list[dict[str, Any]], out_path: str) -> None:
    if not out_path:
        return
    try:
        Path(out_path).write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"Warning: could not save browser cookies to {out_path}: {exc}")


def proxy_cookie_path(base_path: str, proxy: str) -> str:
    if not base_path:
        return ""
    base = Path(base_path)
    if proxy == DIRECT_PROXY:
        return str(base)
    safe_proxy = re.sub(r"[^A-Za-z0-9_.-]+", "_", proxy)
    return str(base.with_name(f"{base.stem}_{safe_proxy}{base.suffix or '.txt'}"))


def load_cookie_header(path_str: str) -> str:
    if not path_str:
        return ""
    path = Path(path_str)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def safe_get(driver: Any, url: str, timeout_override: float | None = None) -> bool:
    original_timeout = None
    try:
        if timeout_override is not None:
            original_timeout = driver.timeouts.page_load
            driver.set_page_load_timeout(timeout_override)
        driver.get(url)
        return True
    except TimeoutException:
        try:
            driver.execute_script("window.stop();")
        except WebDriverException:
            pass
        return False
    except WebDriverException:
        return False
    finally:
        if timeout_override is not None and original_timeout is not None:
            try:
                driver.set_page_load_timeout(original_timeout)
            except WebDriverException:
                pass


def build_driver(
    browser: str,
    proxy: str,
    *,
    timeout: float,
    headless: bool,
    chrome_binary: str,
    chrome_user_data_dir: str,
    chrome_profile_directory: str,
) -> Any:
    ensure_selenium_available()
    prepared_user_data_dir, prepared_profile_directory, cleanup_dir = prepare_chrome_profile(
        chrome_user_data_dir,
        chrome_profile_directory,
    )
    options = build_chrome_options(
        proxy,
        headless=headless,
        user_agent=DEFAULT_HEADERS["User-Agent"],
        chrome_binary=chrome_binary,
        chrome_user_data_dir=prepared_user_data_dir,
        chrome_profile_directory=prepared_profile_directory,
    )
    service = Service()
    driver = webdriver.Chrome(service=service, options=options)
    driver._codex_cleanup_dir = cleanup_dir
    driver.set_page_load_timeout(timeout)
    driver.set_script_timeout(timeout)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'languages', {get: () => ['ru-RU', 'ru', 'en-US']});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
            """
        },
    )
    return driver


def cleanup_driver(driver: Any) -> None:
    cleanup_dir = getattr(driver, "_codex_cleanup_dir", "")
    driver.quit()
    if cleanup_dir:
        shutil.rmtree(cleanup_dir, ignore_errors=True)


def find_first_xpath(driver: Any, xpaths: list[str]) -> Any | None:
    for xpath in xpaths:
        try:
            return driver.find_element(By.XPATH, xpath)
        except NoSuchElementException:
            continue
    return None


def wait_for_any_xpath(driver: Any, xpaths: list[str], timeout: float) -> Any | None:
    wait = WebDriverWait(driver, timeout)
    return wait.until(lambda drv: find_first_xpath(drv, xpaths))


def click_element_robust(driver: Any, element: Any) -> None:
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    time.sleep(0.4)
    try:
        element.click()
        return
    except WebDriverException:
        pass
    try:
        driver.execute_script("arguments[0].click();", element)
        return
    except WebDriverException:
        pass
    parent = driver.execute_script(
        """
        let el = arguments[0];
        while (el && el.parentElement) {
            el = el.parentElement;
            const text = (el.innerText || el.textContent || '').trim();
            if (text.includes('Показать номер')) return el;
        }
        return null;
        """,
        element,
    )
    if parent is not None:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", parent)
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", parent)


def click_show_phone_button(driver: Any, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for xpath in SHOW_PHONE_XPATHS:
            for element in driver.find_elements(By.XPATH, xpath):
                try:
                    if not element.is_displayed():
                        continue
                    click_element_robust(driver, element)
                    time.sleep(1)
                    if extract_phone_text_from_page(driver) or detect_page_condition(driver) is not None:
                        return True
                except WebDriverException:
                    continue
        try:
            clicked = driver.execute_script(
                """
                const btn = document.querySelector('[data-test="mes__show-phones-button"]');
                if (!btn) return false;
                btn.scrollIntoView({block: 'center'});
                btn.click();
                return true;
                """
            )
            if clicked:
                time.sleep(1)
                if extract_phone_text_from_page(driver) or detect_page_condition(driver) is not None:
                    return True
        except WebDriverException:
            pass
        time.sleep(1)
    return False


def has_mobile_call_button(driver: Any) -> bool:
    for xpath in MOBILE_CALL_BUTTON_XPATHS:
        for element in driver.find_elements(By.XPATH, xpath):
            try:
                if element.is_displayed():
                    return True
            except WebDriverException:
                continue
    try:
        return bool(driver.execute_script("return Boolean(document.querySelector('button.a-call-btn'));"))
    except WebDriverException:
        return False


def extract_phone_text_from_mobile_modal(driver: Any) -> list[str]:
    found: set[str] = set()
    for element in driver.find_elements(By.XPATH, MOBILE_PHONE_MODAL_LINKS_XPATH):
        href = element.get_attribute("href") or ""
        tel_value = href.removeprefix("tel:") if href.startswith("tel:") else ""
        candidates = [tel_value, element.text or ""]
        for candidate in candidates:
            for phone in PHONE_RE.findall(candidate):
                normalized = normalize_phone_candidate(phone)
                if normalized:
                    found.add(normalized)
            normalized_raw = normalize_phone_candidate(candidate)
            if normalized_raw:
                found.add(normalized_raw)
    return sorted(found)


def click_mobile_call_button(driver: Any, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        # Wait specifically for the mobile call button when available.
        try:
            WebDriverWait(driver, 1.2).until(
                lambda drv: bool(drv.find_elements(By.CSS_SELECTOR, "button.a-call-btn"))
            )
        except TimeoutException:
            pass
        for xpath in MOBILE_CALL_BUTTON_XPATHS:
            for element in driver.find_elements(By.XPATH, xpath):
                try:
                    if not element.is_displayed():
                        continue
                    click_element_robust(driver, element)
                    time.sleep(0.8)
                    if extract_phone_text_from_mobile_modal(driver):
                        return True
                except WebDriverException:
                    continue
        try:
            clicked = driver.execute_script(
                """
                const btn = document.querySelector('button.a-call-btn');
                if (!btn) return false;
                btn.scrollIntoView({block: 'center'});
                btn.click();
                return true;
                """
            )
            if clicked:
                time.sleep(0.8)
                if extract_phone_text_from_mobile_modal(driver):
                    return True
        except WebDriverException:
            pass
        time.sleep(0.5)
    return False


def has_show_phone_button(driver: Any) -> bool:
    for xpath in SHOW_PHONE_XPATHS:
        for element in driver.find_elements(By.XPATH, xpath):
            try:
                if element.is_displayed():
                    return True
            except WebDriverException:
                continue
    try:
        return bool(
            driver.execute_script(
                "return Boolean(document.querySelector('[data-test=\"mes__show-phones-button\"]'));"
            )
        )
    except WebDriverException:
        return False


def switch_to_new_window(driver: Any, known_handles: list[str], timeout: float) -> bool:
    deadline = time.time() + timeout
    known_set = set(known_handles)
    while time.time() < deadline:
        current_handles = driver.window_handles
        extra_handles = [handle for handle in current_handles if handle not in known_set]
        if extra_handles:
            driver.switch_to.window(extra_handles[-1])
            return True
        time.sleep(0.2)
    return False


def click_button_by_text_js(driver: Any, texts: list[str]) -> bool:
    script = """
    const texts = arguments[0];
    const nodes = Array.from(document.querySelectorAll('button, a, [role="button"], [aria-label], [title]'));
    for (const node of nodes) {
        const content = [
            node.innerText || '',
            node.textContent || '',
            node.getAttribute('aria-label') || '',
            node.getAttribute('title') || '',
        ].join(' ').trim();
        if (!content) continue;
        if (!texts.some(text => content.includes(text))) continue;
        node.scrollIntoView({block: 'center'});
        node.click();
        return true;
    }
    return false;
    """
    try:
        return bool(driver.execute_script(script, texts))
    except WebDriverException:
        return False


def normalize_target_url(raw_url: str) -> str:
    if not raw_url:
        return ""
    if raw_url.startswith("http://") or raw_url.startswith("https://"):
        return raw_url
    if raw_url.startswith("/"):
        return f"https://krisha.kz{raw_url}"
    return raw_url


def build_message_url(ad_id: str) -> str:
    return f"https://krisha.kz/my/messages/?advertId={ad_id}#/"


def build_mobile_ad_url(ad_id: str) -> str:
    return f"https://m.krisha.kz/a/show/{ad_id}"


def open_message_page(driver: Any, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        clicked = False
        for xpath in MESSAGE_BUTTON_XPATHS:
            for button in driver.find_elements(By.XPATH, xpath):
                try:
                    if not button.is_displayed():
                        continue
                    start_url = driver.current_url
                    known_handles = list(driver.window_handles)
                    target_url = normalize_target_url(button.get_attribute("href") or "")
                    if target_url:
                        if safe_get(driver, target_url, timeout_override=min(5.0, timeout)):
                            return True
                        continue
                    click_element_robust(driver, button)
                    clicked = True

                    if switch_to_new_window(driver, known_handles, min(5.0, timeout)):
                        return True

                    WebDriverWait(driver, min(5.0, timeout)).until(
                        lambda drv: drv.current_url != start_url
                        or find_first_xpath(drv, MESSAGE_PAGE_XPATHS) is not None
                        or find_first_xpath(drv, SHOW_PHONE_XPATHS) is not None
                        or detect_page_condition(drv) is not None
                    )
                    return True
                except (TimeoutException, WebDriverException):
                    continue

        if not clicked:
            for xpath in MESSAGE_BUTTON_XPATHS:
                for button in driver.find_elements(By.XPATH, xpath):
                    try:
                        target_url = normalize_target_url(button.get_attribute("href") or "")
                        if target_url and safe_get(driver, target_url, timeout_override=min(5.0, timeout)):
                            return True
                    except WebDriverException:
                        continue

        if not clicked and click_button_by_text_js(driver, ["Написать сообщение", "Написать"]):
            try:
                WebDriverWait(driver, min(5.0, timeout)).until(
                    lambda drv: find_first_xpath(drv, MESSAGE_PAGE_XPATHS) is not None
                    or find_first_xpath(drv, SHOW_PHONE_XPATHS) is not None
                    or detect_page_condition(drv) is not None
                )
                return True
            except TimeoutException:
                pass

        time.sleep(0.5)
    return False


def message_seen_in_chat(driver: Any, message_text: str) -> bool:
    snippet = normalize_text_value(message_text)[:24]
    if not snippet:
        return False
    try:
        source = driver.page_source
    except WebDriverException:
        return False
    return snippet in source


def fill_message_input(driver: Any, element: Any, message_text: str) -> bool:
    try:
        click_element_robust(driver, element)
    except WebDriverException:
        pass
    try:
        tag = (element.tag_name or "").lower()
    except WebDriverException:
        tag = ""
    try:
        is_contenteditable = (element.get_attribute("contenteditable") or "").lower() == "true"
    except WebDriverException:
        is_contenteditable = False

    if tag in {"textarea", "input"}:
        try:
            element.clear()
        except WebDriverException:
            pass
        try:
            element.send_keys(message_text)
            return True
        except WebDriverException:
            return False

    if is_contenteditable:
        try:
            driver.execute_script(
                """
                const el = arguments[0];
                const text = arguments[1];
                el.focus();
                el.innerHTML = '';
                el.textContent = text;
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                """,
                element,
                message_text,
            )
            return True
        except WebDriverException:
            return False
    return False


def send_chat_message(driver: Any, message_text: str, timeout: float) -> bool:
    text = normalize_text_value(message_text)
    if not text:
        return False

    deadline = time.time() + timeout
    while time.time() < deadline:
        input_element = find_first_xpath(driver, MESSAGE_INPUT_XPATHS)
        if input_element is None:
            time.sleep(0.4)
            continue

        if not fill_message_input(driver, input_element, text):
            time.sleep(0.4)
            continue

        send_button = find_first_xpath(driver, MESSAGE_SEND_XPATHS)
        if send_button is not None:
            try:
                click_element_robust(driver, send_button)
            except WebDriverException:
                pass
        else:
            try:
                input_element.send_keys(Keys.ENTER)
            except WebDriverException:
                pass

        time.sleep(1.0)
        if message_seen_in_chat(driver, text):
            return True
        return True
    return False


def normalize_phone_candidate(raw: str) -> str | None:
    return normalize_phone_number(raw) or None


def normalize_text_value(raw: str) -> str:
    return re.sub(r"\s+", " ", raw or "").strip()


def strip_html_tags(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    return normalize_text_value(html.unescape(text))


def parse_window_data_from_html(html_source: str) -> dict[str, Any]:
    match = re.search(r"window\.data\s*=\s*(\{.*?\});\s*</script>", html_source, re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def extract_description_from_html(html_source: str) -> str:
    match = re.search(r'<div class="js-description[^"]*"[^>]*>(.*?)</div>', html_source, re.DOTALL)
    if not match:
        return ""
    return strip_html_tags(match.group(1))


def extract_ad_metadata_from_html_source(html_source: str) -> dict[str, str]:
    payload = parse_window_data_from_html(html_source)
    advert = payload.get("advert", {}) if isinstance(payload, dict) else {}
    adverts = payload.get("adverts", []) if isinstance(payload, dict) else []
    first = adverts[0] if isinstance(adverts, list) and adverts else {}
    if not isinstance(advert, dict):
        advert = {}
    if not isinstance(first, dict):
        first = {}

    title = normalize_text_value(str(advert.get("title") or first.get("title") or ""))

    price = ""
    raw_price = first.get("price")
    if raw_price:
        price = strip_html_tags(str(raw_price))
    elif isinstance(advert.get("price"), int):
        amount = int(advert["price"])
        price = f"{amount:,}".replace(",", " ") + " 〒"

    description = extract_description_from_html(html_source)
    if not description:
        description = normalize_text_value(str(first.get("description") or ""))

    city = normalize_text_value(str(first.get("city") or ""))
    street = normalize_text_value(str(first.get("address") or advert.get("addressTitle") or ""))
    seller_name = normalize_text_value(str(advert.get("ownerName") or ""))
    app_id = normalize_text_value(str(payload.get("appId") or ""))
    app_key = normalize_text_value(str(payload.get("appKey") or ""))

    phones_url = normalize_text_value(str(payload.get("phonesUrl") or ""))

    return {
        "title": title,
        "price": price,
        "description": description,
        "city": city,
        "street": street,
        "seller_name": seller_name,
        "phones_url": phones_url,
        "app_id": app_id,
        "app_key": app_key,
    }


def merge_ad_metadata(base: dict[str, str], candidate: dict[str, str]) -> dict[str, str]:
    merged = dict(base)
    for key in ("title", "price", "description", "city", "street", "seller_name", "phones_url", "app_id", "app_key"):
        if not merged.get(key):
            merged[key] = candidate.get(key, "")
    return merged


def has_required_ad_metadata(data: dict[str, str]) -> bool:
    return bool(data.get("title") and data.get("price"))


def wait_for_ad_metadata_from_html(driver: Any, timeout: float) -> dict[str, str]:
    deadline = time.time() + timeout
    best = {
        "title": "",
        "price": "",
        "description": "",
        "city": "",
        "street": "",
        "seller_name": "",
        "phones_url": "",
        "app_id": "",
        "app_key": "",
    }
    while time.time() < deadline:
        candidate = extract_ad_metadata_from_html_source(driver.page_source)
        best = merge_ad_metadata(best, candidate)
        if has_required_ad_metadata(best):
            return best
        time.sleep(0.3)
    return best


def extract_seller_name_from_messages(driver: Any) -> str:
    forbidden = ("показать", "телефон", "сообщение", "квартира", "описание", "адрес")
    for xpath in SELLER_NAME_XPATHS:
        for element in driver.find_elements(By.XPATH, xpath):
            try:
                if not element.is_displayed():
                    continue
                value = normalize_text_value(element.text)
            except WebDriverException:
                continue
            if not value:
                continue
            if any(ch.isdigit() for ch in value):
                continue
            if len(value) > 60:
                continue
            lowered = value.lower()
            if any(token in lowered for token in forbidden):
                continue
            return value
    return ""


def extract_chat_thread_phones(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    thread = payload.get("thread")
    if not isinstance(thread, dict):
        return []
    reply_speed = thread.get("reply_speed")
    if not isinstance(reply_speed, dict):
        return []
    raw_phones = reply_speed.get("phones")
    if not isinstance(raw_phones, list):
        return []
    found: set[str] = set()
    for item in raw_phones:
        if not isinstance(item, str):
            continue
        normalized = normalize_phone_candidate(item)
        if normalized:
            found.add(normalized)
    return sorted(found)


def extract_app_getphones(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    raw_phones = data.get("phones")
    if not isinstance(raw_phones, list):
        return []
    found: set[str] = set()
    for item in raw_phones:
        if not isinstance(item, str):
            continue
        normalized = normalize_phone_candidate(item)
        if normalized:
            found.add(normalized)
    return sorted(found)


def fetch_phones_from_app_getphones_api(
    driver: Any,
    *,
    ad_id: str,
    app_id: str,
    app_key: str,
    current_user: str,
) -> tuple[list[str], str | None]:
    if not (ad_id and app_id and app_key and current_user):
        return [], None
    url = (
        "https://app.krisha.kz/a/getPhones"
        f"?appId={app_id}&appKey={app_key}&currentUser={current_user}&id={ad_id}"
    )

    headers = dict(DEFAULT_HEADERS)
    headers["Accept"] = "application/json, text/plain, */*"
    headers["Referer"] = f"https://krisha.kz/a/show/{ad_id}"
    cookie_header = dump_cookies_to_header(driver)
    if cookie_header:
        headers["Cookie"] = cookie_header
    req = Request(url=url, method="GET", headers=headers)
    opener = build_opener()

    text = ""
    status_code = 0
    try:
        with opener.open(req, timeout=8.0) as resp:
            status_code = resp.getcode()
            text = resp.read().decode("utf-8", errors="replace").strip()
    except HTTPError as exc:
        status_code = exc.code
        text = exc.read().decode("utf-8", errors="replace").strip()
    except URLError:
        return [], None

    if status_code in {401, 403}:
        return [], "auth_required"
    if not text:
        return [], None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return [], None

    phones = extract_app_getphones(payload)
    if phones:
        return phones, None
    error_text = str(payload.get("error", "")).lower() if isinstance(payload, dict) else ""
    if "авториз" in error_text:
        return [], "auth_required"
    if "captcha" in error_text or "recaptcha" in error_text:
        return [], "captcha_required"
    return [], None


def fetch_phones_from_chat_thread_api(
    driver: Any,
    *,
    ad_id: str,
    app_id: str,
    app_key: str,
) -> tuple[list[str], str, str | None]:
    if not (ad_id and app_id and app_key):
        return [], "", None
    url = (
        "https://chat.krisha.kz/ms/chat/v1/messages/getThread.json"
        f"?advert_id={ad_id}&appId={app_id}&appKey={app_key}&limit=20"
    )
    safe_get(driver, "https://krisha.kz/", timeout_override=6.0)
    if not safe_get(driver, url, timeout_override=10.0):
        return [], "", None
    current = (driver.current_url or "").lower()
    if "/signin" in current or "id.kolesa.kz/login" in current:
        return [], "", "auth_required"
    status_code = 0
    try:
        status_code = int(driver.execute_script("return (window.performance.getEntriesByType('navigation')[0] || {}).responseStatus || 0;"))
    except (WebDriverException, ValueError, TypeError):
        status_code = 0
    if status_code in {401, 403}:
        return [], "", "auth_required"

    text = ""
    try:
        text = str(
            driver.execute_script(
                "return (document.body && (document.body.innerText || document.body.textContent)) || '';"
            )
        ).strip()
    except WebDriverException:
        text = ""
    if not text:
        try:
            text = normalize_text_value(driver.page_source)
        except WebDriverException:
            text = ""
    if "http error 403" in text.lower() or "доступ к chat.krisha.kz запрещен" in text.lower():
        return [], "", "auth_required"
    if not text:
        return [], "", None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return [], "", None

    seller_name = ""
    if isinstance(payload, dict):
        thread = payload.get("thread")
        if isinstance(thread, dict):
            other = thread.get("other")
            if isinstance(other, dict):
                seller_name = normalize_text_value(str(other.get("name") or other.get("nameWith") or ""))

    phones = extract_chat_thread_phones(payload)
    if phones:
        return phones, seller_name, None

    error_text = ""
    if isinstance(payload, dict):
        error_text = str(payload.get("error", "")).lower()
    if "авториз" in error_text:
        return [], seller_name, "auth_required"
    if "captcha" in error_text or "recaptcha" in error_text:
        return [], seller_name, "captcha_required"
    return [], seller_name, None


def normalize_phone_endpoint(raw: str) -> str:
    value = normalize_text_value(raw)
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if value.startswith("/"):
        return f"https://krisha.kz{value}"
    return ""


def fetch_phones_via_page_endpoint(driver: Any, endpoint: str) -> tuple[list[str], str | None]:
    target = normalize_phone_endpoint(endpoint)
    if not target:
        return [], None
    script = """
    const url = arguments[0];
    const done = arguments[arguments.length - 1];
    fetch(url, {
        method: 'GET',
        credentials: 'include',
        headers: {
            'Accept': 'application/json, text/plain, */*',
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(resp => resp.text().then(text => done({ok: resp.ok, status: resp.status, text})))
    .catch(err => done({ok: false, status: 0, error: String(err)}));
    """
    try:
        raw = driver.execute_async_script(script, target)
    except WebDriverException:
        return [], None
    if not isinstance(raw, dict):
        return [], None

    text = str(raw.get("text") or "").strip()
    if not text:
        return [], None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return [], None
    phones = extract_phones(payload)
    return phones, detect_api_condition(payload)


def is_logged_in(driver: Any) -> bool:
    if find_first_xpath(driver, AUTH_SUCCESS_XPATHS):
        return True
    current = (driver.current_url or "").lower()
    if "/signin" in current or "id.kolesa.kz/login" in current:
        return False
    try:
        is_guest = driver.execute_script(
            "return Boolean(window.data && window.data.user && window.data.user.isGuest);"
        )
        if isinstance(is_guest, bool):
            return not is_guest
    except WebDriverException:
        pass
    cookies = {item.get("name", "") for item in driver.get_cookies()}
    return any(name in cookies for name in ("sessionid", "passport", "kolesa_session"))


def wait_for_manual_login(driver: Any, *, timeout: float) -> None:
    print("Browser opened for manual login on Krisha. Complete login in the window, then return here.")
    safe_get(driver, LOGIN_URL)
    if sys.stdin.isatty():
        input("Press Enter after login is complete...")

    def looks_logged_in_without_reload() -> bool:
        current = (driver.current_url or "").lower()
        if "id.kolesa.kz/login" in current or "/signin" in current:
            return False
        if "krisha.kz" not in current:
            return False
        if is_logged_in(driver):
            return True
        try:
            body_text = (driver.find_element(By.TAG_NAME, "body").text or "").lower()
        except WebDriverException:
            return False
        if "войти" in body_text and "регистрация" in body_text:
            return False
        return True

    deadline = time.time() + timeout
    while time.time() < deadline:
        if looks_logged_in_without_reload():
            return
        time.sleep(2)

    raise RuntimeError("Manual login was not detected before timeout")


def wait_for_manual_captcha(driver: Any, *, timeout: float) -> bool:
    auto_wait_deadline = time.time() + min(timeout, 12.0)
    while time.time() < auto_wait_deadline:
        phones = extract_phone_text_from_page(driver)
        if phones:
            return True
        if detect_page_condition(driver) != "captcha_required":
            return True
        time.sleep(1)

    print("reCAPTCHA detected. Solve it in the browser window, then return here.")
    if sys.stdin.isatty():
        input("Press Enter after captcha is solved...")

    deadline = time.time() + timeout
    while time.time() < deadline:
        phones = extract_phone_text_from_page(driver)
        if phones:
            return True
        if detect_page_condition(driver) != "captcha_required":
            return True
        time.sleep(2)
    return False


def ensure_authenticated_session(
    driver: Any,
    *,
    account_login: str,
    account_password: str,
    auth_timeout: float,
    headless: bool,
    force_manual_login: bool = False,
    cookies_only: bool = False,
) -> bool:
    def has_messages_access() -> bool:
        safe_get(driver, "https://krisha.kz/my/messages/")
        if detect_page_condition(driver) == "auth_required":
            return False
        current = (driver.current_url or "").lower()
        if "id.kolesa.kz/login" in current:
            return False
        return True

    safe_get(driver, "https://krisha.kz/")
    if cookies_only and is_logged_in(driver):
        return False
    if cookies_only and not (account_login and account_password):
        return False
    if force_manual_login:
        if headless:
            raise RuntimeError("Manual login requires visible browser (--no-headless)")
        wait_for_manual_login(driver, timeout=auth_timeout)
        if has_messages_access():
            return True
        raise RuntimeError("Manual login did not grant access to messages")

    if is_logged_in(driver) and has_messages_access():
        return False

    if account_login and account_password:
        try:
            login_with_password(
                driver,
                account_login=account_login,
                account_password=account_password,
                timeout=auth_timeout,
            )
            if has_messages_access():
                return True
        except RuntimeError:
            if not headless:
                print("Auto-login failed, switching to manual login...")
                wait_for_manual_login(driver, timeout=auth_timeout)
                if has_messages_access():
                    return True
            raise

    if not headless:
        wait_for_manual_login(driver, timeout=auth_timeout)
        if has_messages_access():
            return True

    raise RuntimeError("Authorization is required by krisha.kz")


def login_with_password(
    driver: Any,
    *,
    account_login: str,
    account_password: str,
    timeout: float,
) -> None:
    if not account_login or not account_password:
        return

    safe_get(driver, LOGIN_URL)
    if is_logged_in(driver):
        return

    login_input = wait_for_any_xpath(driver, LOGIN_FIELD_XPATHS, timeout)
    password_input = wait_for_any_xpath(driver, PASSWORD_FIELD_XPATHS, timeout)
    if login_input is None or password_input is None:
        raise RuntimeError("Login form was not found on krisha.kz")

    def fill_field(field: Any, value: str) -> None:
        try:
            click_element_robust(driver, field)
        except WebDriverException:
            pass
        try:
            field.clear()
        except WebDriverException:
            pass
        try:
            field.send_keys(value)
            return
        except WebDriverException:
            pass
        # Fallback: set value via JS for masked/non-interactable inputs.
        driver.execute_script(
            """
            const el = arguments[0];
            const val = arguments[1];
            el.focus();
            el.value = '';
            el.setAttribute('value', '');
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.value = val;
            el.setAttribute('value', val);
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            """,
            field,
            value,
        )

    fill_field(login_input, account_login)
    fill_field(password_input, account_password)

    submit = find_first_xpath(driver, LOGIN_SUBMIT_XPATHS)
    if submit is not None:
        driver.execute_script("arguments[0].click();", submit)
    else:
        password_input.submit()

    WebDriverWait(driver, timeout).until(lambda drv: is_logged_in(drv) or detect_page_condition(drv) is not None)
    if not is_logged_in(driver):
        condition = detect_page_condition(driver)
        if condition == "captcha_required":
            raise RuntimeError("Login blocked by captcha")
        raise RuntimeError("Krisha login failed")


def extract_phone_text_from_page(driver: Any) -> list[str]:
    found: set[str] = set()
    tel_elements = driver.find_elements(By.XPATH, "//a[starts-with(@href, 'tel:')]")
    for element in tel_elements:
        href = element.get_attribute("href") or ""
        if not href.startswith("tel:"):
            continue
        tel_value = href.removeprefix("tel:")
        normalized = normalize_phone_candidate(tel_value)
        if normalized:
            found.add(normalized)
        for phone in PHONE_RE.findall(element.text or ""):
            normalized = normalize_phone_candidate(phone)
            if normalized:
                found.add(normalized)

    if found:
        return sorted(found)

    for xpath in PHONE_XPATH_CANDIDATES:
        for element in driver.find_elements(By.XPATH, xpath):
            href = element.get_attribute("href") or ""
            text = " ".join(part for part in [element.text, href] if part).strip()
            for phone in PHONE_RE.findall(text):
                normalized = normalize_phone_candidate(phone)
                if normalized:
                    found.add(normalized)
    return sorted(found)


def detect_page_condition(driver: Any) -> str | None:
    if extract_phone_text_from_page(driver):
        return None
    if find_first_xpath(driver, CAPTCHA_XPATH_CANDIDATES):
        return "captcha_required"
    visible_text = (driver.find_element(By.TAG_NAME, "body").text or "").lower()
    if "не робот" in visible_text or "подтвердите" in visible_text and "робот" in visible_text:
        return "captcha_required"
    if find_first_xpath(driver, AUTH_REQUIRED_XPATHS):
        return "auth_required"
    if "необходимо авторизоваться" in visible_text or "требуется авторизация" in visible_text:
        return "auth_required"
    return None


def display_proxy(proxy: str) -> str:
    return "direct" if proxy == DIRECT_PROXY else proxy


def compute_random_delay(delay_sec: float, random_delay_min: float, random_delay_max: float) -> float:
    if random_delay_min > 0 and random_delay_max > 0:
        low = min(random_delay_min, random_delay_max)
        high = max(random_delay_min, random_delay_max)
    else:
        base = max(delay_sec, 0.0)
        if base <= 0:
            return 0.0
        low = max(0.2, base * 0.7)
        high = max(low, base * 2.0)
    return random.uniform(low, high)


def sleep_between_requests(
    *,
    delay_sec: float,
    random_delay_min: float,
    random_delay_max: float,
) -> None:
    wait_sec = compute_random_delay(delay_sec, random_delay_min, random_delay_max)
    if wait_sec <= 0:
        return
    print(f"  -> wait={wait_sec:.2f}s")
    time.sleep(wait_sec)


def fetch_phone_with_active_driver(
    driver: Any,
    ad_url: str,
    *,
    proxy: str,
    rotator: ProxyRotator,
    current_cookie_file: str,
    proxy_blacklist_file: str,
    timeout: float,
    proxy_failover_timeout: float,
    auth_timeout: float,
    delay_sec: float,
    headless: bool,
    chat_message: str,
    send_chat_message_enabled: bool,
    chat_app_id: str,
    chat_app_key: str,
    chat_current_user: str,
) -> dict[str, str]:
    ad_id = parse_ad_id(ad_url)
    if not ad_id:
        return {
            "ad_url": ad_url,
            "ad_id": "",
            "title": "",
            "price": "",
            "description": "",
            "city": "",
            "street": "",
            "seller_name": "",
            "phones": "",
            "status": "error",
            "proxy": "",
            "error": "Cannot parse ad id from url",
        }

    page_timeout = proxy_failover_timeout if proxy != DIRECT_PROXY else None
    if not safe_get(driver, ad_url, timeout_override=page_timeout):
        raise ProxyUnavailableError(f"Proxy did not load ad page in time: {display_proxy(proxy)}")
    ad_metadata = wait_for_ad_metadata_from_html(driver, timeout=min(max(timeout, 4.0), 12.0))
    seller_name = ad_metadata.get("seller_name", "")
    phones_url = ad_metadata.get("phones_url", "")
    app_id = ad_metadata.get("app_id", "") or chat_app_id
    app_key = ad_metadata.get("app_key", "") or chat_app_key

    def build_row(
        *,
        status: str,
        phones_value: str = "",
        error_text: str = "",
        proxy_value: str | None = None,
    ) -> dict[str, str]:
        return {
            "ad_url": ad_url,
            "ad_id": ad_id,
            "title": ad_metadata["title"],
            "price": ad_metadata["price"],
            "description": ad_metadata["description"],
            "city": ad_metadata["city"],
            "street": ad_metadata["street"],
            "seller_name": seller_name,
            "phones": phones_value,
            "status": status,
            "proxy": proxy_value if proxy_value is not None else display_proxy(proxy),
            "error": error_text,
        }

    def save_session_cookies() -> None:
        if current_cookie_file:
            save_cookie_header(dump_cookies_to_header(driver), current_cookie_file)
            save_browser_cookies(driver.get_cookies(), cookie_json_path(current_cookie_file))

    app_phones, app_condition = fetch_phones_from_app_getphones_api(
        driver,
        ad_id=ad_id,
        app_id=chat_app_id,
        app_key=chat_app_key,
        current_user=chat_current_user,
    )
    if app_phones:
        save_session_cookies()
        return build_row(status="ok", phones_value=";".join(app_phones))
    if app_condition == "auth_required":
        rotator.block_proxy(proxy)
        if proxy_blacklist_file:
            append_unique_line(Path(proxy_blacklist_file), proxy)
        return build_row(status="auth_required", error_text="Authorization is required by krisha.kz for this phone")
    if app_condition == "captcha_required":
        return build_row(status="captcha_required", error_text="reCAPTCHA is required by krisha.kz for this phone")

    chat_api_phones, chat_api_seller, chat_api_condition = fetch_phones_from_chat_thread_api(
        driver,
        ad_id=ad_id,
        app_id=app_id,
        app_key=app_key,
    )
    if chat_api_seller:
        seller_name = chat_api_seller
    if chat_api_phones:
        save_session_cookies()
        return build_row(status="ok", phones_value=";".join(chat_api_phones))
    if chat_api_condition == "auth_required":
        rotator.block_proxy(proxy)
        if proxy_blacklist_file:
            append_unique_line(Path(proxy_blacklist_file), proxy)
        return build_row(status="auth_required", error_text="Authorization is required by krisha.kz for this phone")
    if chat_api_condition == "captcha_required":
        return build_row(status="captcha_required", error_text="reCAPTCHA is required by krisha.kz for this phone")
    # Chat API is primary source. If it responded without phone, return no_phone and don't parse UI.
    if app_id and app_key:
        return build_row(status="no_phone")

    mobile_url = build_mobile_ad_url(ad_id)
    if not safe_get(driver, mobile_url, timeout_override=min(6.0, timeout)):
        raise RuntimeError("Mobile ad page could not be opened")

    phones = extract_phone_text_from_mobile_modal(driver)
    if not phones and has_mobile_call_button(driver):
        click_mobile_call_button(driver, timeout)
        try:
            WebDriverWait(driver, timeout).until(
                lambda drv: bool(extract_phone_text_from_mobile_modal(drv))
            )
        except TimeoutException:
            pass
        time.sleep(delay_sec)
        phones = extract_phone_text_from_mobile_modal(driver)

    if not phones:
        condition = detect_page_condition(driver)
        if condition == "captcha_required" and not headless:
            if wait_for_manual_captcha(driver, timeout=auth_timeout):
                safe_get(driver, mobile_url, timeout_override=min(6.0, timeout))
                if has_mobile_call_button(driver):
                    click_mobile_call_button(driver, timeout)
                    time.sleep(delay_sec)
                phones = extract_phone_text_from_mobile_modal(driver)
            else:
                return build_row(status="captcha_required", error_text="reCAPTCHA is required by krisha.kz for this phone")
        elif condition == "captcha_required":
            return build_row(status="captcha_required", error_text="reCAPTCHA is required by krisha.kz for this phone")

        if not phones and condition == "auth_required":
            rotator.block_proxy(proxy)
            if proxy_blacklist_file:
                append_unique_line(Path(proxy_blacklist_file), proxy)
            return build_row(status="auth_required", error_text="Authorization is required by krisha.kz for this phone")

    if not phones and not has_mobile_call_button(driver) and not has_show_phone_button(driver):
        phones_via_endpoint, endpoint_condition = fetch_phones_via_page_endpoint(driver, phones_url)
        if phones_via_endpoint:
            save_session_cookies()
            return build_row(status="ok", phones_value=";".join(phones_via_endpoint))
        if endpoint_condition == "auth_required":
            rotator.block_proxy(proxy)
            if proxy_blacklist_file:
                append_unique_line(Path(proxy_blacklist_file), proxy)
            return build_row(status="auth_required", error_text="Authorization is required by krisha.kz for this phone")
        if endpoint_condition == "captcha_required":
            return build_row(status="captcha_required", error_text="reCAPTCHA is required by krisha.kz for this phone")

    if phones:
        save_session_cookies()
        return build_row(status="ok", phones_value=";".join(phones))

    if not send_chat_message_enabled:
        return build_row(status="no_phone")

    message_url = build_message_url(ad_id)
    if not safe_get(driver, message_url, timeout_override=min(6.0, timeout)):
        return build_row(status="no_phone")

    seller_from_chat = extract_seller_name_from_messages(driver)
    if seller_from_chat:
        seller_name = seller_from_chat

    send_chat_message(driver, chat_message, timeout=min(8.0, timeout))
    click_show_phone_button(driver, timeout)
    try:
        WebDriverWait(driver, timeout).until(
            lambda drv: bool(extract_phone_text_from_page(drv)) or detect_page_condition(drv) is not None
        )
    except TimeoutException:
        pass
    phones = extract_phone_text_from_page(driver)
    if phones:
        save_session_cookies()
        return build_row(status="ok", phones_value=";".join(phones))
    return build_row(status="no_phone")


def open_phone_with_selenium(
    ad_url: str,
    rotator: ProxyRotator,
    *,
    cookie: str,
    cookie_base_file: str,
    proxy_blacklist_file: str,
    account_login: str,
    account_password: str,
    timeout: float,
    proxy_failover_timeout: float,
    auth_timeout: float,
    delay_sec: float,
    headless: bool,
    manual_login: bool,
    cookies_only: bool,
    chat_message: str,
    send_chat_message_enabled: bool,
    chat_app_id: str,
    chat_app_key: str,
    chat_current_user: str,
    chrome_binary: str,
    chrome_user_data_dir: str,
    chrome_profile_directory: str,
) -> dict[str, str]:
    ad_id = parse_ad_id(ad_url) or ""
    last_error = ""

    for idx, proxy in rotator.proxy_cycle():
        driver = None
        try:
            current_cookie_file = proxy_cookie_path(cookie_base_file, proxy)
            current_cookie_json_file = cookie_json_path(current_cookie_file)
            current_cookie = load_cookie_header(current_cookie_file) or cookie
            current_browser_cookies = load_browser_cookies(current_cookie_json_file)
            driver = build_driver(
                "chrome",
                proxy,
                timeout=timeout,
                headless=headless,
                chrome_binary=chrome_binary,
                chrome_user_data_dir=chrome_user_data_dir,
                chrome_profile_directory=chrome_profile_directory,
            )
            inject_cookies(driver, current_cookie, current_browser_cookies)
            if current_cookie_file and (current_cookie or current_browser_cookies):
                save_cookie_header(dump_cookies_to_header(driver), current_cookie_file)
                save_browser_cookies(driver.get_cookies(), current_cookie_json_file)
            row = fetch_phone_with_active_driver(
                driver,
                ad_url,
                proxy=proxy,
                rotator=rotator,
                current_cookie_file=current_cookie_file,
                proxy_blacklist_file=proxy_blacklist_file,
                timeout=timeout,
                proxy_failover_timeout=proxy_failover_timeout,
                auth_timeout=auth_timeout,
                delay_sec=delay_sec,
                headless=headless,
                chat_message=chat_message,
                send_chat_message_enabled=send_chat_message_enabled,
                chat_app_id=chat_app_id,
                chat_app_key=chat_app_key,
                chat_current_user=chat_current_user,
            )
            rotator.current_index = idx
            return row
        except Exception as exc:  # noqa: BLE001 - collect per-proxy errors
            last_error = str(exc)
        finally:
            if driver is not None:
                cleanup_driver(driver)

    return {
        "ad_url": ad_url,
        "ad_id": ad_id,
        "phones": "",
        "status": "error",
        "proxy": "",
        "error": last_error or "All Selenium proxies failed",
    }


def fetch_phones_for_ads_selenium(
    ads: list[str],
    rotator: ProxyRotator,
    *,
    browser: str,
    cookie: str,
    cookie_base_file: str,
    proxy_blacklist_file: str,
    account_login: str,
    account_password: str,
    timeout: float,
    proxy_failover_timeout: float,
    auth_timeout: float,
    delay_sec: float,
    random_delay_min: float,
    random_delay_max: float,
    headless: bool,
    manual_login: bool,
    cookies_only: bool,
    chat_message: str,
    send_chat_message_enabled: bool,
    chat_app_id: str,
    chat_app_key: str,
    chat_current_user: str,
    chrome_binary: str,
    chrome_user_data_dir: str,
    chrome_profile_directory: str,
    checkpoint_path: Path | None = None,
    resume_state: dict[str, Any] | None = None,
    listing_url: str = "",
    on_row: Callable[[dict[str, str]], None] | None = None,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    total = len(ads)
    driver = None
    current_cookie_file = ""
    proxy = ""
    ad_index = 0

    if resume_state:
        saved_listing = str(resume_state.get("listing_url", "")).strip()
        saved_ads = resume_state.get("ads", [])
        if saved_listing == listing_url and isinstance(saved_ads, list) and saved_ads == ads:
            saved_rows = resume_state.get("rows", [])
            if isinstance(saved_rows, list):
                rows = [row for row in saved_rows if isinstance(row, dict)]
            ad_index = max(0, min(int(resume_state.get("ad_index", 0)), total))
            print(f"  -> resume checkpoint loaded: rows={len(rows)}, next={ad_index + 1}")

    def persist_checkpoint() -> None:
        if checkpoint_path is None:
            return
        save_checkpoint(
            checkpoint_path,
            {
                "version": 1,
                "source": "krisha",
                "listing_url": listing_url,
                "ads": ads,
                "ad_index": ad_index,
                "rows": rows,
                "updated_at": time.time(),
            },
        )

    def start_driver_for_proxy(next_proxy: str) -> tuple[Any, str]:
        next_cookie_file = proxy_cookie_path(cookie_base_file, next_proxy)
        next_cookie_json_file = cookie_json_path(next_cookie_file)
        next_cookie = load_cookie_header(next_cookie_file) or cookie
        next_browser_cookies = load_browser_cookies(next_cookie_json_file)
        next_driver = build_driver(
            browser,
            next_proxy,
            timeout=timeout,
            headless=headless,
            chrome_binary=chrome_binary,
            chrome_user_data_dir=chrome_user_data_dir,
            chrome_profile_directory=chrome_profile_directory,
        )
        fast_timeout = proxy_failover_timeout if next_proxy != DIRECT_PROXY else None
        if not safe_get(next_driver, "https://krisha.kz/", timeout_override=fast_timeout):
            next_driver.quit()
            raise ProxyUnavailableError(f"Proxy did not open krisha.kz in time: {display_proxy(next_proxy)}")
        inject_cookies(next_driver, next_cookie, next_browser_cookies)
        if next_cookie_file and (next_cookie or next_browser_cookies):
            save_cookie_header(dump_cookies_to_header(next_driver), next_cookie_file)
            save_browser_cookies(next_driver.get_cookies(), next_cookie_json_file)
        return next_driver, next_cookie_file

    try:
        while ad_index < total:
            chosen = next(rotator.proxy_cycle(), None)
            if chosen is None:
                break

            idx, proxy = chosen
            try:
                if driver is not None:
                    driver.quit()
                driver, current_cookie_file = start_driver_for_proxy(proxy)
            except (TimeoutException, WebDriverException, ProxyUnavailableError) as exc:
                rotator.block_proxy(proxy)
                if proxy_blacklist_file:
                    append_unique_line(Path(proxy_blacklist_file), proxy)
                print(f"  -> proxy skipped={display_proxy(proxy)}, error={exc}")
                driver = None
                if proxy == DIRECT_PROXY:
                    for failed_url in ads[ad_index:]:
                        rows.append(
                            {
                                "ad_url": failed_url,
                                "ad_id": parse_ad_id(failed_url) or "",
                                "phones": "",
                                "status": "error",
                                "proxy": "direct",
                                "error": f"Direct session failed: {exc}",
                            }
                        )
                        if on_row:
                            on_row(rows[-1])
                        persist_checkpoint()
                    ad_index = total
                    persist_checkpoint()
                    break
                continue

            while ad_index < total:
                ad_url = ads[ad_index]
                print(f"[{ad_index + 1}/{total}] {ad_url}")
                try:
                    row = fetch_phone_with_active_driver(
                        driver,
                        ad_url,
                        proxy=proxy,
                        rotator=rotator,
                        current_cookie_file=current_cookie_file,
                        proxy_blacklist_file=proxy_blacklist_file,
                        timeout=timeout,
                        proxy_failover_timeout=proxy_failover_timeout,
                        auth_timeout=auth_timeout,
                        delay_sec=delay_sec,
                        headless=headless,
                        chat_message=chat_message,
                        send_chat_message_enabled=send_chat_message_enabled,
                        chat_app_id=chat_app_id,
                        chat_app_key=chat_app_key,
                        chat_current_user=chat_current_user,
                    )
                except (ProxyUnavailableError, WebDriverException) as exc:
                    rotator.block_proxy(proxy)
                    if proxy_blacklist_file:
                        append_unique_line(Path(proxy_blacklist_file), proxy)
                    print(f"  -> proxy failed={display_proxy(proxy)}, error={exc}")
                    try:
                        if driver is not None:
                            cleanup_driver(driver)
                    finally:
                        driver = None
                    break

                if row["status"] == "skipped":
                    ad_index += 1
                    persist_checkpoint()
                    if ad_index < total:
                        sleep_between_requests(
                            delay_sec=delay_sec,
                            random_delay_min=random_delay_min,
                            random_delay_max=random_delay_max,
                        )
                    continue
                rows.append(row)
                if on_row:
                    on_row(row)
                status = row["status"]
                proxy_label = row["proxy"] or "-"
                phones = row["phones"] or "-"
                print(f"  -> status={status}, proxy={proxy_label}, phones={phones}")
                if row["error"]:
                    print(f"  -> error={row['error']}")
                ad_index += 1
                persist_checkpoint()
                if ad_index < total:
                    sleep_between_requests(
                        delay_sec=delay_sec,
                        random_delay_min=random_delay_min,
                        random_delay_max=random_delay_max,
                    )

            rotator.current_index = idx

        if ad_index < total:
            for failed_url in ads[ad_index:]:
                rows.append(
                    {
                        "ad_url": failed_url,
                        "ad_id": parse_ad_id(failed_url) or "",
                        "phones": "",
                        "status": "error",
                        "proxy": "",
                        "error": "No available proxies after failover",
                    }
                )
                if on_row:
                    on_row(rows[-1])
                persist_checkpoint()
            ad_index = total
            persist_checkpoint()
        return rows
    finally:
        if driver is not None:
            cleanup_driver(driver)


def fetch_phone_for_ad(
    ad_url: str,
    rotator: ProxyRotator,
    base_headers: dict[str, str],
    delay_sec: float,
    random_delay_min: float,
    random_delay_max: float,
) -> dict[str, str]:
    ajax_ad_id, ajax_token = parse_ajax_params(ad_url)
    ad_id = ajax_ad_id or parse_ad_id(ad_url)
    if not ad_id:
        return {
            "ad_url": ad_url,
            "ad_id": "",
            "phones": "",
            "status": "error",
            "proxy": "",
            "error": "Cannot parse ad id from url",
        }

    try:
        referer = f"https://krisha.kz/a/show/{ad_id}"
        ajax_headers = dict(base_headers)
        ajax_headers.update(AJAX_HEADERS)
        ajax_headers["Referer"] = referer

        # 1) Try modern flow first: id-only request.
        ajax_result = rotator.request(
            "GET",
            "https://krisha.kz/a/ajaxPhones",
            headers=ajax_headers,
            params={"id": ad_id},
            ok_statuses={200},
        )
        payload = ajax_result.response.json()
        phones = extract_phones(payload)
        condition = detect_api_condition(payload)

        # 2) Fallback to legacy v3Token flow only when needed.
        if not phones and condition is None:
            token = ajax_token
            if not token:
                show_headers = dict(base_headers)
                show_result = rotator.request("GET", ad_url, headers=show_headers)
                token = extract_v3token(show_result.response.text)

            if token:
                ajax_result = rotator.request(
                    "GET",
                    "https://krisha.kz/a/ajaxPhones",
                    headers=ajax_headers,
                    params={"id": ad_id, "v3Token": token},
                    ok_statuses={200},
                )
                payload = ajax_result.response.json()
                phones = extract_phones(payload)
                condition = detect_api_condition(payload)

        sleep_between_requests(
            delay_sec=delay_sec,
            random_delay_min=random_delay_min,
            random_delay_max=random_delay_max,
        )

        if condition == "auth_required":
            return {
                "ad_url": ad_url,
                "ad_id": ad_id,
                "phones": "",
                "status": "auth_required",
                "proxy": ajax_result.proxy,
                "error": "Authorization is required by krisha.kz for this phone",
            }

        if condition == "captcha_required":
            return {
                "ad_url": ad_url,
                "ad_id": ad_id,
                "phones": "",
                "status": "captcha_required",
                "proxy": ajax_result.proxy,
                "error": "reCAPTCHA is required by krisha.kz for this phone",
            }

        return {
            "ad_url": ad_url,
            "ad_id": ad_id,
            "phones": ";".join(phones),
            "status": "ok" if phones else "no_phone",
            "proxy": ajax_result.proxy,
            "error": "",
        }

    except Exception as exc:  # noqa: BLE001 - collect per-row errors
        return {
            "ad_url": ad_url,
            "ad_id": ad_id,
            "phones": "",
            "status": "error",
            "proxy": "",
            "error": str(exc),
        }


def run_login_only_selenium(
    rotator: ProxyRotator,
    *,
    browser: str,
    cookie: str,
    cookie_base_file: str,
    account_login: str,
    account_password: str,
    timeout: float,
    auth_timeout: float,
    headless: bool,
    manual_login: bool,
    chrome_binary: str,
    chrome_user_data_dir: str,
    chrome_profile_directory: str,
) -> None:
    chosen = next(rotator.proxy_cycle(), None)
    if chosen is None:
        raise RuntimeError("No available proxies for login")
    _, proxy = chosen

    current_cookie_file = proxy_cookie_path(cookie_base_file, proxy)
    current_cookie_json_file = cookie_json_path(current_cookie_file)
    current_cookie = load_cookie_header(current_cookie_file) or cookie
    current_browser_cookies = load_browser_cookies(current_cookie_json_file)

    driver = build_driver(
        browser,
        proxy,
        timeout=timeout,
        headless=headless,
        chrome_binary=chrome_binary,
        chrome_user_data_dir=chrome_user_data_dir,
        chrome_profile_directory=chrome_profile_directory,
    )
    try:
        inject_cookies(driver, current_cookie, current_browser_cookies)
        ensure_authenticated_session(
            driver,
            account_login=account_login,
            account_password=account_password,
            auth_timeout=auth_timeout,
            headless=headless,
            force_manual_login=manual_login or not (account_login and account_password),
        )
        save_cookie_header(dump_cookies_to_header(driver), current_cookie_file)
        save_browser_cookies(driver.get_cookies(), current_cookie_json_file)
        print(f"Saved cookies: {Path(current_cookie_file).resolve()}")
        print(f"Saved browser cookies: {Path(current_cookie_json_file).resolve()}")
    finally:
        cleanup_driver(driver)


def save_csv(rows: list[dict[str, str]], out_path: Path) -> None:
    fieldnames = [
        "ad_url",
        "ad_id",
        "title",
        "price",
        "description",
        "city",
        "street",
        "seller_name",
        "phones",
        "status",
        "proxy",
        "error",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def save_json(rows: list[dict[str, str]], out_path: Path) -> None:
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Krisha phone collector with proxy failover")
    parser.add_argument("--ads-file", default="", help="Path to file with one ad URL per line")
    parser.add_argument("--ad-url", default="", help="Single ad URL or ajaxPhones URL")
    parser.add_argument(
        "--listing-url",
        default=DEFAULT_LISTING_URL,
        help="Listing page URL to collect ad links from when ad URLs are not provided",
    )
    parser.add_argument(
        "--listing-limit",
        type=int,
        default=0,
        help="How many ads to collect from listing page",
    )
    parser.add_argument(
        "--proxies-file",
        default="proxyscrape_premium_http_proxies.txt",
        help="Path to proxy list file (host:port per line)",
    )
    parser.add_argument("--output", default="results.csv", help="Output CSV file")
    parser.add_argument("--checkpoint-file", default="", help="Path to resume checkpoint JSON file")
    parser.add_argument("--database-url", default="", help="PostgreSQL DSN for live per-record insert")
    parser.add_argument("--json-output", default="", help="Optional JSON output path")
    parser.add_argument("--cookie", default="", help="Cookie header string")
    parser.add_argument("--cookie-file", default="", help="Path to file with cookie string")
    parser.add_argument(
        "--login-only",
        action="store_true",
        help="Only authenticate in browser and save cookies, do not parse ads",
    )
    parser.add_argument("--account-login", default="", help="Krisha account phone/email for Selenium login")
    parser.add_argument("--account-password", default="", help="Krisha account password for Selenium login")
    parser.add_argument(
        "--cookie-output-file",
        default="",
        help="Optional path to save fresh cookies after Selenium login",
    )
    parser.add_argument("--timeout", type=float, default=12.0, help="HTTP timeout per request")
    parser.add_argument(
        "--proxy-failover-timeout",
        type=float,
        default=3.0,
        help="Seconds to wait on Selenium page load before switching to next proxy",
    )
    parser.add_argument(
        "--auth-timeout",
        type=float,
        default=300.0,
        help="Timeout for Selenium login or manual authorization in seconds",
    )
    parser.add_argument(
        "--manual-login",
        action="store_true",
        help="Open browser and wait only for manual login (skip auto-login)",
    )
    parser.add_argument(
        "--cookies-only",
        action="store_true",
        help="Use saved cookies only and never trigger login flow",
    )
    parser.add_argument("--delay", type=float, default=0.7, help="Delay between ads (seconds)")
    parser.add_argument(
        "--random-delay-min",
        type=float,
        default=0.0,
        help="Minimum random delay between requests in seconds (0 = auto from --delay)",
    )
    parser.add_argument(
        "--random-delay-max",
        type=float,
        default=0.0,
        help="Maximum random delay between requests in seconds (0 = auto from --delay)",
    )
    parser.add_argument(
        "--chat-message",
        default="Здравствуйте! Подскажите, пожалуйста, можно ли позвонить?",
        help="Message text sent in chat before clicking call button",
    )
    parser.add_argument(
        "--send-chat-message",
        action="store_true",
        help="Send message in chat before trying to reveal phone (disabled by default)",
    )
    parser.add_argument(
        "--chat-app-id",
        default=DEFAULT_CHAT_APP_ID,
        help="chat.krisha.kz appId for getThread.json",
    )
    parser.add_argument(
        "--chat-app-key",
        default=DEFAULT_CHAT_APP_KEY,
        help="chat.krisha.kz appKey for getThread.json",
    )
    parser.add_argument(
        "--chat-current-user",
        default=DEFAULT_CHAT_CURRENT_USER,
        help="currentUser parameter for app.krisha.kz/a/getPhones",
    )
    parser.add_argument("--shuffle", action="store_true", help="Shuffle ad URLs before processing")
    parser.add_argument(
        "--proxy-blacklist-file",
        default="proxy_blacklist.txt",
        help="Path to file with bad proxies to skip",
    )
    parser.add_argument(
        "--no-proxy",
        action="store_true",
        help="Run directly without using proxy list",
    )
    parser.add_argument(
        "--driver",
        choices=["http", "selenium"],
        default="selenium",
        help="Phone extraction mode",
    )
    parser.add_argument(
        "--browser",
        choices=["chrome", "safari"],
        default="chrome",
        help="Browser to use for Selenium mode",
    )
    parser.add_argument(
        "--chrome-binary",
        default="",
        help="Optional path to Chrome/Chromium binary for Selenium",
    )
    parser.add_argument(
        "--chrome-user-data-dir",
        default="",
        help="Path to Chrome user data dir for reusing your normal browser session",
    )
    parser.add_argument(
        "--chrome-profile-directory",
        default="",
        help="Chrome profile directory name, for example Default or Profile 1",
    )
    parser.add_argument(
        "--headless",
        dest="headless",
        action="store_true",
        help="Run Selenium browser in headless mode",
    )
    parser.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        help="Run Selenium browser with visible window for manual login/session capture",
    )
    parser.set_defaults(headless=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
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
        live_db_writer = LiveDbWriter(db_url, source="krisha", run_id=db_run_id)
        print(f"[db] live mode enabled run_id={live_db_writer.run_id}")

    proxies_file = Path(args.proxies_file)
    output_path = Path(args.output)
    checkpoint_path = checkpoint_path_for_output(output_path, args.checkpoint_file)

    proxies = [DIRECT_PROXY] if args.no_proxy else load_lines(proxies_file)
    blocked_proxies = set() if args.no_proxy else set(load_optional_lines(Path(args.proxy_blacklist_file)))

    cookie = args.cookie.strip()
    if args.cookie_file and Path(args.cookie_file).exists():
        cookie = Path(args.cookie_file).read_text(encoding="utf-8").strip()
    cookie_base_file = args.cookie_output_file.strip() or args.cookie_file or "cookie.txt"

    base_headers = build_base_headers(cookie if cookie else None)
    rotator = ProxyRotator(proxies=proxies, timeout=args.timeout, blocked_proxies=blocked_proxies)
    chrome_binary = resolve_chrome_binary(args.chrome_binary)
    chrome_user_data_dir = args.chrome_user_data_dir.strip()
    chrome_profile_directory = args.chrome_profile_directory.strip()
    if chrome_user_data_dir and not chrome_profile_directory:
        chrome_profile_directory = DEFAULT_CHROME_PROFILE_DIRECTORY

    if args.driver == "selenium" and args.login_only:
        run_login_only_selenium(
            rotator,
            browser=args.browser,
            cookie=cookie,
            cookie_base_file=cookie_base_file,
            account_login=args.account_login.strip(),
            account_password=args.account_password,
            timeout=args.timeout,
            auth_timeout=args.auth_timeout,
            headless=args.headless,
            manual_login=args.manual_login,
            chrome_binary=chrome_binary,
            chrome_user_data_dir=chrome_user_data_dir,
            chrome_profile_directory=chrome_profile_directory,
        )
        return 0

    ads: list[str] = []
    if args.ads_file:
        ads.extend(load_lines(Path(args.ads_file)))
    if args.ad_url:
        ads.append(args.ad_url.strip())
    if not ads:
        listing_limit = args.listing_limit if args.listing_limit > 0 else prompt_listing_limit()
        try:
            ads = fetch_ads_from_listing(args.listing_url, listing_limit, rotator, base_headers)
        except RuntimeError as exc:
            if args.driver != "selenium":
                raise
            print(f"HTTP listing fetch failed, trying Selenium listing fallback: {exc}")
            ads = fetch_ads_from_listing_selenium(
                args.listing_url,
                listing_limit,
                browser=args.browser,
                timeout=args.timeout,
                headless=args.headless,
                chrome_binary=chrome_binary,
                chrome_user_data_dir=chrome_user_data_dir,
                chrome_profile_directory=chrome_profile_directory,
                cookie=cookie,
                cookie_base_file=cookie_base_file,
            )
        if not ads:
            raise ValueError(f"No ads found on listing page: {args.listing_url}")
        print(f"Collected {len(ads)} ads from listing page.")
    if args.shuffle and len(ads) > 1:
        random.shuffle(ads)

    resume_state = load_checkpoint(checkpoint_path)

    if args.driver == "selenium":
        rows = fetch_phones_for_ads_selenium(
            ads,
            rotator,
            browser=args.browser,
            cookie=cookie,
            cookie_base_file=cookie_base_file,
            proxy_blacklist_file=args.proxy_blacklist_file,
            account_login=args.account_login.strip(),
            account_password=args.account_password,
            timeout=args.timeout,
            proxy_failover_timeout=args.proxy_failover_timeout,
            auth_timeout=args.auth_timeout,
            delay_sec=args.delay,
            random_delay_min=args.random_delay_min,
            random_delay_max=args.random_delay_max,
            headless=args.headless,
            manual_login=args.manual_login,
            cookies_only=args.cookies_only,
            chat_message=args.chat_message,
            send_chat_message_enabled=args.send_chat_message,
            chat_app_id=args.chat_app_id.strip(),
            chat_app_key=args.chat_app_key.strip(),
            chat_current_user=args.chat_current_user.strip(),
            chrome_binary=chrome_binary,
            chrome_user_data_dir=chrome_user_data_dir,
            chrome_profile_directory=chrome_profile_directory,
            checkpoint_path=checkpoint_path,
            resume_state=resume_state,
            listing_url=args.listing_url,
            on_row=live_db_writer.insert_row if live_db_writer else None,
        )
    else:
        rows = []
        total = len(ads)
        ad_index = 0
        if resume_state:
            saved_listing = str(resume_state.get("listing_url", "")).strip()
            saved_ads = resume_state.get("ads", [])
            if saved_listing == args.listing_url and isinstance(saved_ads, list) and saved_ads == ads:
                saved_rows = resume_state.get("rows", [])
                if isinstance(saved_rows, list):
                    rows = [row for row in saved_rows if isinstance(row, dict)]
                ad_index = max(0, min(int(resume_state.get("ad_index", 0)), total))
                if rows:
                    print(f"  -> resume checkpoint loaded: rows={len(rows)}, next={ad_index + 1}")

        def persist_checkpoint() -> None:
            save_checkpoint(
                checkpoint_path,
                {
                    "version": 1,
                    "source": "krisha",
                    "listing_url": args.listing_url,
                    "ads": ads,
                    "ad_index": ad_index,
                    "rows": rows,
                    "updated_at": time.time(),
                },
            )

        for idx, ad_url in enumerate(ads[ad_index:], start=ad_index + 1):
            print(f"[{idx}/{total}] {ad_url}")
            row = fetch_phone_for_ad(
                ad_url,
                rotator,
                base_headers,
                delay_sec=args.delay,
                random_delay_min=args.random_delay_min,
                random_delay_max=args.random_delay_max,
            )
            rows.append(row)
            if live_db_writer:
                live_db_writer.insert_row(row)
            status = row["status"]
            proxy = row["proxy"] or "-"
            phones = row["phones"] or "-"
            print(f"  -> status={status}, proxy={proxy}, phones={phones}")
            if row["error"]:
                print(f"  -> error={row['error']}")
            ad_index = idx
            persist_checkpoint()
        if live_db_writer and rows:
            live_db_writer._processed = len(rows)

    if live_db_writer and rows:
        live_db_writer._processed = len(rows)

    save_csv(rows, output_path)
    print(f"Saved CSV: {output_path.resolve()}")

    if args.json_output:
        json_path = Path(args.json_output)
        save_json(rows, json_path)
        print(f"Saved JSON: {json_path.resolve()}")

    if live_db_writer:
        skipped = sum(1 for row in rows if row.get("status") == "skipped")
        errors = sum(1 for row in rows if row.get("status") in {"error", "captcha_required", "auth_required"})
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
