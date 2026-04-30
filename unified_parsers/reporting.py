from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import csv
import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile


@dataclass
class RunReport:
    source: str
    status: str
    exit_code: int
    started_at: str
    finished_at: str
    duration_sec: float
    output_path: str
    processed: int
    skipped: int
    errors: int
    db_run_id: str = ""
    db_records: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


class MetricsCollector:
    _processed_line = re.compile(r"\[\d+\s*/\s*\d+\]\s+(?:Обработано:|https?://)", re.I)
    _progress_line = re.compile(r"\[progress\]\s+(\d+)\s*/\s*(\d+)", re.I)
    _saved_olx = re.compile(r"Сохранено\s+(\d+)\s+объявлен", re.I)
    _skipped_olx = re.compile(r"Пропущено\s+объявлений:\s*(\d+)", re.I)

    def __init__(self) -> None:
        self.processed = 0
        self.skipped = 0
        self.errors = 0
        self._saved_total: int | None = None
        self._skipped_total: int | None = None

    def consume(self, line: str) -> None:
        text = line.strip()
        lower = text.lower()
        progress_match = self._progress_line.search(text)
        if progress_match:
            self.processed = max(self.processed, int(progress_match.group(1)))
        elif self._processed_line.search(text):
            self.processed += 1
        if "[warn]" in lower and "пропуск" in lower:
            self.skipped += 1
        if "[error]" in lower:
            self.errors += 1

        saved_match = self._saved_olx.search(text)
        if saved_match:
            self._saved_total = int(saved_match.group(1))
        skipped_match = self._skipped_olx.search(text)
        if skipped_match:
            self._skipped_total = int(skipped_match.group(1))

    def finalize(self) -> tuple[int, int, int]:
        processed = self._saved_total if self._saved_total is not None else self.processed
        skipped = self._skipped_total if self._skipped_total is not None else self.skipped
        return processed, skipped, self.errors


def refine_metrics_from_output(
    source: str,
    output_path: Path | None,
    processed: int,
    skipped: int,
    errors: int,
    exit_code: int,
) -> tuple[int, int, int]:
    if output_path is None or not output_path.exists() or not output_path.is_file():
        if exit_code != 0 and errors == 0:
            errors = 1
        return processed, skipped, errors

    source_key = source.lower().strip()
    if source_key == "krisha":
        return _refine_krisha_from_csv(output_path, processed, skipped, errors, exit_code)

    row_count = _count_rows_generic(output_path)
    if row_count is not None:
        processed = row_count
    if exit_code != 0 and errors == 0:
        errors = 1
    return processed, skipped, errors


def _refine_krisha_from_csv(
    output_path: Path,
    processed: int,
    skipped: int,
    errors: int,
    exit_code: int,
) -> tuple[int, int, int]:
    try:
        with output_path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
    except Exception:
        if exit_code != 0 and errors == 0:
            errors = 1
        return processed, skipped, errors

    if not rows:
        if exit_code != 0 and errors == 0:
            errors = 1
        return 0, skipped, errors

    processed = len(rows)
    skipped_count = 0
    error_count = 0
    for row in rows:
        status = str(row.get("status", "")).strip().lower()
        error_text = str(row.get("error", "")).strip()
        if "skip" in status:
            skipped_count += 1
        if error_text or any(token in status for token in ("error", "failed", "captcha", "timeout")):
            error_count += 1

    skipped = skipped_count if skipped_count else skipped
    errors = max(errors, error_count)
    if exit_code != 0 and errors == 0:
        errors = 1
    return processed, skipped, errors


def _count_rows_generic(path: Path) -> int | None:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _count_csv_rows(path)
    if suffix == ".json":
        return _count_json_rows(path)
    if suffix == ".xlsx":
        return _count_xlsx_rows(path)
    return None


def _count_csv_rows(path: Path) -> int | None:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh)
            rows = list(reader)
    except Exception:
        return None
    if not rows:
        return 0
    return max(0, len(rows) - 1)


def _count_json_rows(path: Path) -> int | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("rows", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
    return None


def _count_xlsx_rows(path: Path) -> int | None:
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    try:
        with zipfile.ZipFile(path) as zf:
            xml_bytes = zf.read("xl/worksheets/sheet1.xml")
        root = ET.fromstring(xml_bytes)
    except Exception:
        return None

    row_nodes = root.findall(".//x:sheetData/x:row", ns)
    if not row_nodes:
        return 0
    return max(0, len(row_nodes) - 1)


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def write_report(path: Path, report: RunReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.to_json(), encoding="utf-8")
