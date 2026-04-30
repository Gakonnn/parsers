#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
import zipfile
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape as xml_escape

from unified_parsers.phone_utils import normalize_phone_number

try:
    import psycopg2
    from psycopg2.extras import Json
except ModuleNotFoundError:  # pragma: no cover
    psycopg2 = None
    Json = None


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/135.0.0.0 Safari/537.36"
)

DEFAULT_OUTPUT = "olx_results.xlsx"
DEFAULT_CATEGORY_URL = "https://www.olx.kz/elektronika/"
DEFAULT_PHONE_PROXY_PROVIDER = "crawlbase"
MAX_LISTING_URLS_PER_PAGE = 20
SCRAPERAPI_KEY = "1ad559ff083d0fe48e3247faea63c745"
# SCRAPERAPI_KEY = "eb1e349299028a16e6354608cb234487"
SCRAPERAPI_ENDPOINT = "https://api.scraperapi.com/"
# CRAWLBASE_TOKEN = "rTYT3c-PoUO-7QtvacwEsQ"
# CRAWLBASE_JS_TOKEN = "bhrb7WcyuedvnQHwa5MCYA"
# CRAWLBASE_TOKEN = "lCWTH7nVVzq9iRl2DkfMQA"
# CRAWLBASE_JS_TOKEN = "pJthiiFncvYV7xx37KvxSA"
CRAWLBASE_TOKEN = "QTJJCKbfuH48b55m3Twt_w"
CRAWLBASE_JS_TOKEN = "5_JX-_tCFVkw8HK--wYKyg"
CRAWLBASE_ENDPOINT = "https://api.crawlbase.com/"
PHONE_API_TEMPLATES = (
    "https://www.olx.kz/api/v1/offers/{ad_id}/phones",
    "https://www.olx.kz/api/v1/offers/{ad_id}/limited-phones/",
)


@dataclass
class ListingData:
    ad_id: str
    title: str
    price: str
    description: str
    category: str
    location: str
    seller_name: str
    seller_phone: str
    source_url: str

    def row(self) -> list[str]:
        return [
            self.ad_id,
            self.title,
            self.price,
            self.description,
            self.category,
            self.location,
            self.seller_name,
            self.seller_phone,
            self.source_url,
        ]

    def payload(self) -> dict[str, str]:
        return {
            "id": self.ad_id,
            "title": self.title,
            "price": self.price,
            "description": self.description,
            "category": self.category,
            "location": self.location,
            "seller_name": self.seller_name,
            "seller_phone": self.seller_phone,
            "source_url": self.source_url,
        }


class LiveDbWriter:
    def __init__(self, database_url: str, source: str = "olx") -> None:
        if psycopg2 is None or Json is None:
            raise RuntimeError(
                "psycopg2 is not installed. Install dependencies with: ./scripts/bootstrap_unified_env.sh"
            )
        self.source = source
        self.run_id = str(uuid.uuid4())
        self._conn = psycopg2.connect(database_url)
        self._conn.autocommit = True
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
                """,
                (self.run_id, self.source, "running", json.dumps({})),
            )

    def insert_listing(self, listing: ListingData) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO parser_records (run_id, source, external_id, payload)
                VALUES (%s::uuid, %s, %s, %s)
                """,
                (self.run_id, self.source, listing.ad_id, Json(listing.payload())),
            )

    def finish(self, *, status: str, processed: int, skipped: int, errors: int, output_path: str = "") -> None:
        metrics = {
            "processed": processed,
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


def fetch_text(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru,en;q=0.9",
        },
    )
    with urlopen(request, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def extract_first(patterns: list[str], html: str, flags: int = re.S) -> str:
    for pattern in patterns:
        match = re.search(pattern, html, flags)
        if match:
            return clean_text(match.group(1))
    return ""


def extract_product_ld_json(html: str) -> dict[str, Any]:
    pattern = re.compile(
        r'<script[^>]+type="application/ld\+json"[^>]*>\s*(\{.*?\})\s*</script>',
        re.S,
    )
    for match in pattern.finditer(html):
        raw_json = match.group(1)
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("@type") in {"Product", "Offer"}:
            return payload
    return {}


def extract_title(html: str, ld_json: dict[str, Any]) -> str:
    return clean_text(ld_json.get("name")) or extract_first(
        [
            r"<title[^>]*>(.*?)</title>",
            r'<meta[^>]+property="og:title"[^>]+content="(.*?)"',
        ],
        html,
        flags=re.S | re.I,
    )


def extract_description(html: str, ld_json: dict[str, Any]) -> str:
    return clean_text(ld_json.get("description")) or extract_first(
        [
            r'<meta[^>]+name="description"[^>]+content="(.*?)"',
            r'"description":"(.*?)"',
        ],
        html,
        flags=re.S | re.I,
    )


def extract_price(ld_json: dict[str, Any], html: str) -> str:
    offers = ld_json.get("offers")
    if isinstance(offers, dict):
        price = offers.get("price")
        currency = offers.get("priceCurrency", "")
        if price:
            return f"{price} {currency}".strip()

    return extract_first(
        [
            r'"price":\{"value":"(.*?)"',
            r'<meta[^>]+property="product:price:amount"[^>]+content="(.*?)"',
        ],
        html,
        flags=re.S | re.I,
    )


def slug_to_label(slug: str) -> str:
    label = slug.strip("/").split("/")[-1]
    label = label.replace("-", " / ")
    return clean_text(label)


def extract_category(html: str, ld_json: dict[str, Any], title: str, location: str) -> str:
    if title:
        title_pattern = re.escape(title)
        location_pattern = re.escape(location) if location else r".+?"
        match = re.search(
            rf"{title_pattern}\s*-\s*(.*?)\s+{location_pattern}\s+на\s+Olx",
            html,
            re.I | re.S,
        )
        if match:
            return clean_text(match.group(1))

    category_value = ld_json.get("category")
    if isinstance(category_value, str) and category_value:
        return slug_to_label(urlparse(category_value).path)

    return ""


def extract_location(html: str, ld_json: dict[str, Any]) -> str:
    offers = ld_json.get("offers")
    if isinstance(offers, dict):
        area_served = offers.get("areaServed")
        if isinstance(area_served, dict):
            location = clean_text(area_served.get("name"))
            if location:
                return location

    return extract_first(
        [
            r'"location":{"cityName":"(.*?)"',
            r'"cityName":"(.*?)"',
        ],
        html,
        flags=re.S | re.I,
    )


def extract_seller_name(html: str) -> str:
    return extract_first(
        [
            r"Пользователь.*?<h[1-6][^>]*>(.*?)</h[1-6]>",
            r'data-testid="user-profile-link"[^>]*>(.*?)<',
            r'data-cy="user-profile-link"[^>]*>(.*?)<',
            r'"name":"([^"]+)"\s*,\s*"accountType"',
            r'"sellerName":"([^"]+)"',
        ],
        html,
        flags=re.S | re.I,
    )


def extract_ad_id(html: str, url: str, ld_json: dict[str, Any]) -> str:
    sku = clean_text(str(ld_json.get("sku", "")))
    if sku.isdigit():
        return sku

    match = re.search(r"/offers/(\d+)/(?:limited-phones|phones)/", html)
    if match:
        return match.group(1)

    match = re.search(r'"ad_id"\s*:\s*(\d+)', html)
    if match:
        return match.group(1)

    match = re.search(r'"id"\s*:\s*(\d+)', html)
    if match:
        return match.group(1)

    match = re.search(r"ID([A-Za-z0-9]+)\.html", url)
    if match:
        return match.group(1)

    return ""


def build_phone_request_attempts(target_url: str, provider: str) -> list[dict[str, Any]]:
    provider_name = provider.strip().lower()
    crawlbase_normal = f"{CRAWLBASE_ENDPOINT}?{urlencode({'token': CRAWLBASE_TOKEN, 'url': target_url})}"
    crawlbase_js = f"{CRAWLBASE_ENDPOINT}?{urlencode({'token': CRAWLBASE_JS_TOKEN, 'url': target_url})}"
    scraperapi_url = f"{SCRAPERAPI_ENDPOINT}?{urlencode({'api_key': SCRAPERAPI_KEY, 'url': target_url})}"
    direct_url = target_url

    direct = {"kind": "direct", "url": direct_url}
    crawlbase = {"kind": "direct", "url": crawlbase_normal}
    crawlbase_js_attempt = {"kind": "direct", "url": crawlbase_js}
    scraperapi = {"kind": "direct", "url": scraperapi_url}

    if provider_name == "crawlbase":
        return [crawlbase, crawlbase_js_attempt, scraperapi, direct]
    if provider_name == "scraperapi":
        return [scraperapi, crawlbase, crawlbase_js_attempt, direct]
    if provider_name == "direct":
        return [direct]
    if provider_name == "auto":
        return [crawlbase, crawlbase_js_attempt, scraperapi, direct]
    return [crawlbase, crawlbase_js_attempt, scraperapi, direct]


def fetch_phone(ad_id: str, provider: str = DEFAULT_PHONE_PROXY_PROVIDER) -> str:
    if not ad_id.isdigit():
        return ""

    for phone_api_template in PHONE_API_TEMPLATES:
        target_url = phone_api_template.format(ad_id=ad_id)
        attempts = build_phone_request_attempts(target_url, provider)
        for attempt in attempts:
            try:
                response_text = fetch_text(str(attempt["url"]))
                payload = json.loads(response_text)
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
                continue

            phones = payload.get("data", {}).get("phones")
            if not phones:
                phones = payload.get("phones", [])
            if not isinstance(phones, list):
                continue

            normalized: list[str] = []
            for phone in phones:
                if isinstance(phone, str):
                    cleaned = clean_text(phone)
                elif isinstance(phone, dict):
                    cleaned = clean_text(str(phone.get("number", "")))
                else:
                    cleaned = ""
                compact_phone = normalize_phone_number(cleaned)
                if compact_phone:
                    normalized.append(compact_phone)
            if normalized:
                return ";".join(dict.fromkeys(normalized))

    return ""


def parse_listing(url: str, phone_provider: str = DEFAULT_PHONE_PROXY_PROVIDER) -> ListingData:
    html = fetch_text(url)
    ld_json = extract_product_ld_json(html)

    ad_id = extract_ad_id(html, url, ld_json)
    title = extract_title(html, ld_json)
    description = extract_description(html, ld_json)
    price = extract_price(ld_json, html)
    location = extract_location(html, ld_json)
    category = extract_category(html, ld_json, title, location)
    seller_name = extract_seller_name(html)
    seller_phone = fetch_phone(ad_id, provider=phone_provider)

    return ListingData(
        ad_id=ad_id,
        title=title,
        price=price,
        description=description,
        category=category,
        location=location,
        seller_name=seller_name,
        seller_phone=seller_phone,
        source_url=url,
    )


def extract_ld_json_objects(html: str) -> list[dict[str, Any]]:
    pattern = re.compile(
        r'<script[^>]+type="application/ld\+json"[^>]*>\s*(\{.*?\})\s*</script>',
        re.S,
    )
    payloads: list[dict[str, Any]] = []
    for match in pattern.finditer(html):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def normalize_listing_url(url: str) -> str:
    clean_url = url.split("?")[0]
    return urljoin("https://www.olx.kz", clean_url)


def extract_listing_urls_from_category(html: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    for payload in extract_ld_json_objects(html):
        if payload.get("@type") != "ItemList":
            continue

        elements = payload.get("itemListElement", [])
        if not isinstance(elements, list):
            continue

        for element in elements:
            if not isinstance(element, dict):
                continue
            url = element.get("url")
            if not isinstance(url, str) or "/d/obyavlenie/" not in url:
                continue
            normalized = normalize_listing_url(url)
            if normalized in seen:
                continue
            seen.add(normalized)
            urls.append(normalized)

    if urls:
        return urls[:MAX_LISTING_URLS_PER_PAGE]

    fallback_urls: list[str] = []
    fallback_urls.extend(re.findall(r'href=["\'](https://www\.olx\.kz/d/obyavlenie/[^"\']+)["\']', html))
    fallback_urls.extend(re.findall(r'href=["\'](//www\.olx\.kz/d/obyavlenie/[^"\']+)["\']', html))
    fallback_urls.extend(re.findall(r'href=["\'](/d/obyavlenie/[^"\']+)["\']', html))

    for raw_url in fallback_urls:
        url = raw_url
        if raw_url.startswith("//"):
            url = f"https:{raw_url}"
        elif raw_url.startswith("/"):
            url = urljoin("https://www.olx.kz", raw_url)
        normalized = normalize_listing_url(url)
        if normalized in seen:
            continue
        seen.add(normalized)
        urls.append(normalized)
    return urls[:MAX_LISTING_URLS_PER_PAGE]


def build_page_url(category_url: str, page: int) -> str:
    parsed = urlparse(category_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if page > 1:
        query["page"] = str(page)
    else:
        query.pop("page", None)
    return urlunparse(parsed._replace(query=urlencode(query)))


def iter_listing_urls(category_url: str, limit: int):
    seen: set[str] = set()
    page = 1
    consecutive_empty_pages = 0
    max_consecutive_empty_pages = 3

    while len(seen) < limit:
        page_url = build_page_url(category_url, page)
        html = fetch_text(page_url)
        page_urls = extract_listing_urls_from_category(html)
        print(f"[category] page={page} url={page_url} links={len(page_urls)}")
        if not page_urls:
            consecutive_empty_pages += 1
            if consecutive_empty_pages >= max_consecutive_empty_pages:
                break
            page += 1
            continue

        page_added = 0
        for url in page_urls:
            if url in seen:
                continue
            seen.add(url)
            page_added += 1
            yield url
            if len(seen) >= limit:
                break

        if page_added == 0:
            consecutive_empty_pages += 1
            if consecutive_empty_pages >= max_consecutive_empty_pages:
                break
        else:
            consecutive_empty_pages = 0
        page += 1


def collect_listing_urls(category_url: str, limit: int) -> list[str]:
    return list(iter_listing_urls(category_url, limit))


def col_name(index: int) -> str:
    result = []
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result.append(chr(65 + remainder))
    return "".join(reversed(result))


def inline_cell(value: str) -> str:
    return (
        "<c t=\"inlineStr\">"
        f"<is><t xml:space=\"preserve\">{xml_escape(value or '')}</t></is>"
        "</c>"
    )


def build_sheet_xml(rows: list[list[str]]) -> str:
    xml_rows: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for col_index, value in enumerate(row, start=1):
            ref = f"{col_name(col_index)}{row_index}"
            cell_xml = inline_cell(value).replace("<c ", f"<c r=\"{ref}\" ", 1)
            cells.append(cell_xml)
        xml_rows.append(f"<row r=\"{row_index}\">{''.join(cells)}</row>")

    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">"
        "<sheetData>"
        f"{''.join(xml_rows)}"
        "</sheetData>"
        "</worksheet>"
    )


def write_xlsx(path: Path, headers: list[str], listings: list[ListingData]) -> None:
    rows = [headers] + [listing.row() for listing in listings]
    sheet_xml = build_sheet_xml(rows)

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""
    workbook = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="OLX" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>
"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>
"""
    core = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:dcterms="http://purl.org/dc/terms/"
    xmlns:dcmitype="http://purl.org/dc/dcmitype/"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:creator>Codex</dc:creator>
  <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">2026-04-16T00:00:00Z</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">2026-04-16T00:00:00Z</dcterms:modified>
</cp:coreProperties>
"""
    app = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
    xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Microsoft Excel</Application>
</Properties>
"""

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as workbook_file:
        workbook_file.writestr("[Content_Types].xml", content_types)
        workbook_file.writestr("_rels/.rels", rels)
        workbook_file.writestr("docProps/core.xml", core)
        workbook_file.writestr("docProps/app.xml", app)
        workbook_file.writestr("xl/workbook.xml", workbook)
        workbook_file.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        workbook_file.writestr("xl/worksheets/sheet1.xml", sheet_xml)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Парсинг категории OLX.kz с сохранением объявлений в Excel."
    )
    parser.add_argument(
        "-c",
        "--category-url",
        help=f"Ссылка на категорию OLX.kz. По умолчанию при вводе предлагается: {DEFAULT_CATEGORY_URL}",
    )
    parser.add_argument(
        "-l",
        "--limit",
        type=int,
        help="Сколько объявлений обработать",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Имя выходного Excel-файла. По умолчанию: {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--database-url",
        default="",
        help="PostgreSQL DSN for live per-record persistence",
    )
    parser.add_argument(
        "--phone-proxy-provider",
        choices=["crawlbase", "scraperapi", "auto", "direct"],
        default=DEFAULT_PHONE_PROXY_PROVIDER,
        help=(
            "Provider for phone API requests. "
            "Supported: crawlbase, scraperapi, auto, direct."
        ),
    )
    return parser.parse_args()


def prompt_non_empty(prompt_text: str, default: str | None = None) -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        value = input(f"{prompt_text}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        print("Поле не должно быть пустым.")


def prompt_limit(default: int = 10) -> int:
    while True:
        raw_value = input(f"Введите лимит объявлений [{default}]: ").strip()
        if not raw_value:
            return default
        if raw_value.isdigit() and int(raw_value) > 0:
            return int(raw_value)
        print("Введите положительное число.")


def main() -> int:
    args = parse_args()
    category_url = args.category_url or prompt_non_empty(
        "Введите ссылку на категорию OLX",
        DEFAULT_CATEGORY_URL,
    )
    limit = args.limit if args.limit and args.limit > 0 else prompt_limit()
    headers = [
        "id",
        "название объявления",
        "цена",
        "описание",
        "категория",
        "местоположение",
        "имя продавца",
        "номер продавца",
        "ссылка",
    ]
    database_url = (args.database_url or os.environ.get("DATABASE_URL", "")).strip()
    phone_provider = (
        os.environ.get("OLX_PHONE_PROXY_PROVIDER", "").strip().lower()
        or args.phone_proxy_provider
    )
    db_writer: LiveDbWriter | None = None
    if database_url:
        try:
            db_writer = LiveDbWriter(database_url=database_url, source="olx")
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] Не удалось подключиться к PostgreSQL: {exc}", file=sys.stderr)
            return 1
        print(f"[db] live mode enabled run_id={db_writer.run_id}")

    listings: list[ListingData] = []
    skipped = 0
    found_any = False

    try:
        listing_iter = iter_listing_urls(category_url, limit)
        print("Начинаю парсинг объявлений по мере загрузки страниц...")
        for index, url in enumerate(listing_iter, start=1):
            found_any = True
            try:
                listing = parse_listing(url, phone_provider=phone_provider)
            except HTTPError as exc:
                skipped += 1
                print(
                    f"[WARN] Пропуск [{index}]: HTTP {exc.code} при загрузке {url}",
                    file=sys.stderr,
                )
                continue
            except URLError as exc:
                skipped += 1
                print(
                    f"[WARN] Пропуск [{index}]: ошибка сети при загрузке {url}: {exc}",
                    file=sys.stderr,
                )
                continue
            except Exception as exc:  # noqa: BLE001
                skipped += 1
                print(f"[WARN] Пропуск [{index}]: не удалось обработать {url}: {exc}", file=sys.stderr)
                continue
            listings.append(listing)
            if db_writer:
                try:
                    db_writer.insert_listing(listing)
                except Exception as exc:  # noqa: BLE001
                    print(f"[ERROR] Не удалось сохранить запись в PostgreSQL: {exc}", file=sys.stderr)
                    db_writer.finish(status="failed", processed=len(listings), skipped=skipped, errors=1)
                    db_writer.close()
                    return 1
            print(f"[{index}/{limit}] Обработано: {listing.title or url}")
    except HTTPError as exc:
        print(f"[ERROR] HTTP {exc.code} при загрузке категории {category_url}", file=sys.stderr)
        if db_writer:
            db_writer.finish(status="failed", processed=len(listings), skipped=skipped, errors=1)
            db_writer.close()
        return 1
    except URLError as exc:
        print(f"[ERROR] Ошибка сети при загрузке категории {category_url}: {exc}", file=sys.stderr)
        if db_writer:
            db_writer.finish(status="failed", processed=len(listings), skipped=skipped, errors=1)
            db_writer.close()
        return 1

    if not found_any:
        print("[ERROR] Не удалось найти объявления в указанной категории.", file=sys.stderr)
        if db_writer:
            db_writer.finish(status="failed", processed=0, skipped=0, errors=1)
            db_writer.close()
        return 1

    if not listings:
        print(
            f"[ERROR] Не удалось обработать ни одного объявления. Пропущено: {skipped}",
            file=sys.stderr,
        )
        if db_writer:
            db_writer.finish(status="failed", processed=0, skipped=skipped, errors=1)
            db_writer.close()
        return 1

    output_path = Path(args.output).resolve()
    write_xlsx(output_path, headers, listings)
    if skipped:
        print(f"Пропущено объявлений: {skipped}")
    print(f"Сохранено {len(listings)} объявление(й) в {output_path}")
    if db_writer:
        db_writer.finish(
            status="completed",
            processed=len(listings),
            skipped=skipped,
            errors=0,
            output_path=str(output_path),
        )
        db_writer.close()
        print(f"[db] live save completed run_id={db_writer.run_id}, records={len(listings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
