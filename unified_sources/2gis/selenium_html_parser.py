#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
from pathlib import Path
from typing import Any

try:
    from selenium import webdriver
    from selenium.common.exceptions import TimeoutException, WebDriverException
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
except ModuleNotFoundError as exc:  # pragma: no cover
    raise RuntimeError("Selenium is not installed. Run bootstrap first.") from exc

try:
    import xlsxwriter
except ModuleNotFoundError:  # pragma: no cover
    xlsxwriter = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Experimental 2GIS parser via Selenium HTML.")
    parser.add_argument("--search-url", required=True, help="2GIS search URL")
    parser.add_argument("--max-records", type=int, default=100, help="Maximum records to collect")
    parser.add_argument("--format", choices=["xlsx", "csv", "json"], default="xlsx", help="Output format")
    parser.add_argument("--output", required=True, help="Output path")
    parser.add_argument("--headless", choices=["yes", "no"], default="yes", help="Run browser headless")
    parser.add_argument(
        "--remote-url",
        default=os.environ.get("SELENIUM_REMOTE_URL", "").strip(),
        help="Optional Selenium remote URL",
    )
    parser.add_argument("--timeout", type=float, default=40.0, help="Wait timeout in seconds")
    parser.add_argument("--scroll-steps", type=int, default=18, help="Number of page scroll steps")
    parser.add_argument("--scroll-delay", type=float, default=0.7, help="Delay between scrolls")
    return parser.parse_args()


def make_driver(headless: bool, remote_url: str) -> webdriver.Chrome:
    options = Options()
    options.page_load_strategy = "eager"
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1400")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    if remote_url.strip():
        return webdriver.Remote(command_executor=remote_url.strip(), options=options)  # type: ignore[return-value]
    return webdriver.Chrome(options=options)


def normalize_url(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"https://2gis.ru{url}"


def extract_id_from_url(url: str) -> str:
    match = re.search(r"/firm/(\d+)", url)
    return match.group(1) if match else ""


def collect_records(driver: webdriver.Chrome, max_records: int, timeout: float, scroll_steps: int, scroll_delay: float) -> list[dict[str, Any]]:
    wait = WebDriverWait(driver, timeout)
    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    records_by_url: dict[str, dict[str, Any]] = {}

    def absorb_links() -> None:
        elements = driver.find_elements(By.CSS_SELECTOR, "a[href*='/firm/']")
        for el in elements:
            href = (el.get_attribute("href") or "").strip()
            if not href:
                continue
            href = normalize_url(href)
            if "/firm/" not in href:
                continue
            title = (el.text or "").strip()
            if not title:
                title = (el.get_attribute("title") or "").strip()
            try:
                card = el.find_element(By.XPATH, "./ancestor::*[self::article or self::li or self::div][1]")
                raw_text = (card.text or "").strip()
            except Exception:
                raw_text = title
            if href in records_by_url:
                if not records_by_url[href]["raw_text"] and raw_text:
                    records_by_url[href]["raw_text"] = raw_text
                if not records_by_url[href]["title"] and title:
                    records_by_url[href]["title"] = title
                continue
            records_by_url[href] = {
                "external_id": extract_id_from_url(href),
                "title": title,
                "url": href,
                "raw_text": raw_text,
            }

    absorb_links()
    for _ in range(max(1, scroll_steps)):
        if len(records_by_url) >= max_records:
            break
        driver.execute_script("window.scrollBy(0, 900);")
        time.sleep(max(0.15, scroll_delay))
        absorb_links()

    rows = list(records_by_url.values())[:max_records]
    for row in rows:
        row["source_url"] = row.pop("url")
    return rows


def save_rows(rows: list[dict[str, Any]], output_path: Path, fmt: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["external_id", "title", "source_url", "raw_text"]
    if fmt == "json":
        output_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        return
    if fmt == "csv":
        with output_path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in fields})
        return
    if fmt == "xlsx":
        if xlsxwriter is None:
            raise RuntimeError("xlsxwriter is not installed. Use --format csv or json.")
        wb = xlsxwriter.Workbook(str(output_path))
        ws = wb.add_worksheet("2gis")
        for col, field in enumerate(fields):
            ws.write(0, col, field)
        for ridx, row in enumerate(rows, start=1):
            for cidx, field in enumerate(fields):
                ws.write(ridx, cidx, row.get(field, ""))
        wb.close()
        return
    raise ValueError(f"Unsupported format: {fmt}")


def main() -> int:
    args = parse_args()
    output_path = Path(args.output).resolve()
    max_records = max(1, int(args.max_records))
    headless = str(args.headless).lower() == "yes"

    print(f"[2gis-html] Loading: {args.search_url}")
    driver: webdriver.Chrome | None = None
    try:
        driver = make_driver(headless=headless, remote_url=args.remote_url)
        driver.set_page_load_timeout(max(15, int(args.timeout)))
        try:
            driver.get(args.search_url)
        except TimeoutException:
            # 2GIS may keep long-running map/network streams; continue with partially loaded DOM.
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass
            print("[2gis-html] Page load timeout reached, continuing with partial DOM.")
        rows = collect_records(
            driver=driver,
            max_records=max_records,
            timeout=float(args.timeout),
            scroll_steps=max(1, int(args.scroll_steps)),
            scroll_delay=float(args.scroll_delay),
        )
        save_rows(rows=rows, output_path=output_path, fmt=str(args.format))
        print(f"[2gis-html] Saved {len(rows)} records to {output_path}")
        return 0
    except (TimeoutException, WebDriverException) as exc:
        print(f"[ERROR] Selenium failed: {exc}")
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}")
        return 1
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
