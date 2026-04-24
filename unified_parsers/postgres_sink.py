from __future__ import annotations

import csv
import json
import uuid
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

try:
    import psycopg2
    from psycopg2.extras import Json
except ModuleNotFoundError:  # pragma: no cover
    psycopg2 = None
    Json = None


class PostgresSinkError(RuntimeError):
    """Errors raised while persisting parser data to PostgreSQL."""


def persist_output_to_postgres(
    *,
    source: str,
    output_path: Path,
    database_url: str,
    status: str,
    metrics: dict[str, Any],
) -> tuple[str, int]:
    if psycopg2 is None or Json is None:
        raise PostgresSinkError(
            "psycopg2 is not installed. Install it with: ./scripts/bootstrap_unified_env.sh"
        )

    records = load_records(source=source, output_path=output_path)
    run_id = str(uuid.uuid4())

    conn = psycopg2.connect(database_url)
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            _ensure_schema(cur)
            cur.execute(
                """
                INSERT INTO parser_runs (run_id, source, status, metrics)
                VALUES (%s, %s, %s, %s::jsonb)
                """,
                (run_id, source, status, json.dumps(metrics, ensure_ascii=False)),
            )
            for record in records:
                external_id = _extract_external_id(source, record)
                cur.execute(
                    """
                    INSERT INTO parser_records (run_id, source, external_id, payload)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (run_id, source, external_id, Json(record)),
                )
        conn.commit()
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        raise PostgresSinkError(str(exc)) from exc
    finally:
        conn.close()

    return run_id, len(records)


def load_records(*, source: str, output_path: Path) -> list[dict[str, Any]]:
    if not output_path.exists():
        raise PostgresSinkError(f"Output file not found: {output_path}")

    source_key = source.lower().strip()
    if source_key == "olx":
        return _read_xlsx_rows(output_path)
    if source_key == "krisha":
        return _read_csv_rows(output_path)
    if source_key == "2gis":
        if output_path.suffix.lower() == ".json":
            return _read_json_rows(output_path)
        if output_path.suffix.lower() == ".xlsx":
            return _read_xlsx_rows(output_path)
        return _read_csv_rows(output_path)
    return _read_generic_rows(output_path)


def _ensure_schema(cur: Any) -> None:
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


def _extract_external_id(source: str, row: dict[str, Any]) -> str:
    source_key = source.lower().strip()
    if source_key == "olx":
        return str(row.get("id", "")).strip()
    if source_key == "krisha":
        return str(row.get("ad_id", "")).strip()
    if source_key == "2gis":
        return str(row.get("2GIS URL", "") or row.get("Наименование", "")).strip()
    return ""


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return [dict(row) for row in reader]


def _read_json_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _read_xlsx_rows(path: Path) -> list[dict[str, Any]]:
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as zf:
        xml_bytes = zf.read("xl/worksheets/sheet1.xml")
    root = ET.fromstring(xml_bytes)
    rows: list[list[str]] = []
    for row_node in root.findall(".//x:sheetData/x:row", ns):
        values: list[str] = []
        for cell in row_node.findall("x:c", ns):
            text_node = cell.find("x:is/x:t", ns)
            values.append((text_node.text or "") if text_node is not None else "")
        rows.append(values)

    if not rows:
        return []
    headers = rows[0]
    records: list[dict[str, Any]] = []
    for row in rows[1:]:
        padded = row + [""] * max(0, len(headers) - len(row))
        records.append({headers[i]: padded[i] for i in range(len(headers))})
    return records


def _read_generic_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _read_csv_rows(path)
    if suffix == ".json":
        return _read_json_rows(path)
    if suffix == ".xlsx":
        return _read_xlsx_rows(path)
    raise PostgresSinkError(f"Unsupported output format for DB import: {path}")

