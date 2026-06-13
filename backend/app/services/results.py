from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.responses import Response, StreamingResponse

from app.models.user import User, UserRole
from app.schemas.result import ParserResultPublic


PHONE_KEYS = ("seller_phone", "phones", "phone_1", "phone")
BASE_EXPORT_FIELDS = ("job_id", "run_id", "source", "external_id", "created_at")
ADSERVLET_BUSINESS_SHEET = "юр лица 2G Kr Ko "
ADSERVLET_OLX_SHEET = "физ лица OLX"
ADSERVLET_BUSINESS_SOURCES = {"2gis", "krisha"}
ADSERVLET_OLX_SOURCES = {"olx"}
ADSERVLET_BUSINESS_HEADERS = (
    "Phone",
    "phone_2",
    "phone_3",
    "whatsapp_1",
    "telegram_1",
    "Title / Name",
    "description",
    "rubrics (интересы)",
    "country",
    "Location",
    "district",
    "address",
    "email_1",
    "email_2",
    "email_3",
    "facebook_1",
    "instagram_1",
    "instagram_2",
    "instagram_3",
    "type",
)
ADSERVLET_OLX_HEADERS = (
    "Phone",
    "phone_2",
    "phone_3",
    "whatsapp_1",
    "telegram_1",
    "seller_name",
    "country",
    "Location",
    "Location",
    "category (интересы)",
    "title",
    "description",
    "пол",
    "возраст",
    "email_1",
    "email_2",
    "email_3",
    "facebook_1",
    "instagram_1",
    "instagram_2",
    "instagram_3",
)
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")


def _parse_datetime(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid datetime: {value}") from exc


def _normalize_fields(fields: str | list[str] | None) -> list[str]:
    if fields is None:
        return []
    if isinstance(fields, str):
        raw_items = fields.split(",")
    else:
        raw_items = []
        for item in fields:
            raw_items.extend(str(item).split(","))
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(key)
    return normalized


def _build_filters(
    *,
    current_user: User,
    source: str = "",
    job_id: UUID | None = None,
    q: str = "",
    has_phone: str = "",
    created_from: str = "",
    created_to: str = "",
    all_users: bool = False,
) -> tuple[list[str], dict[str, Any]]:
    where_parts: list[str] = []
    params: dict[str, Any] = {}

    if current_user.role != UserRole.ADMIN.value or not all_users:
        where_parts.append("j.user_id = CAST(:current_user_id AS uuid)")
        params["current_user_id"] = str(current_user.id)

    if source.strip():
        where_parts.append("r.source = :source")
        params["source"] = source.strip()
    if job_id is not None:
        where_parts.append("j.id = CAST(:job_id AS uuid)")
        params["job_id"] = str(job_id)
    if q.strip():
        where_parts.append("(r.external_id ILIKE :q OR r.payload::text ILIKE :q OR r.run_id::text ILIKE :q)")
        params["q"] = f"%{q.strip()}%"

    phone_expr = "NULLIF(TRIM(COALESCE(r.payload->>'seller_phone', r.payload->>'phones', r.payload->>'phone_1', r.payload->>'phone', '')), '')"
    if has_phone == "yes":
        where_parts.append(f"{phone_expr} IS NOT NULL")
    elif has_phone == "no":
        where_parts.append(f"{phone_expr} IS NULL")

    parsed_from = _parse_datetime(created_from)
    if parsed_from:
        where_parts.append("r.created_at >= :created_from")
        params["created_from"] = parsed_from
    parsed_to = _parse_datetime(created_to)
    if parsed_to:
        where_parts.append("r.created_at <= :created_to")
        params["created_to"] = parsed_to

    return where_parts, params


def _where_sql(where_parts: list[str]) -> str:
    return "WHERE " + " AND ".join(where_parts) if where_parts else ""


def _repair_missing_job_run_links(db: Session, *, current_user: User, all_users: bool = False) -> None:
    user_filter = ""
    params: dict[str, Any] = {}
    if current_user.role != UserRole.ADMIN.value or not all_users:
        user_filter = "AND j.user_id = CAST(:current_user_id AS uuid)"
        params["current_user_id"] = str(current_user.id)

    sql = text(
        f"""
        WITH missing_jobs AS (
            SELECT
                j.id,
                j.source,
                j.created_at,
                COALESCE(j.finished_at, j.created_at + INTERVAL '1 hour') AS finished_at,
                j.progress_current
            FROM parser_jobs j
            WHERE j.status = 'completed'
              AND j.db_run_id IS NULL
              {user_filter}
        ),
        run_counts AS (
            SELECT
                pr.run_id,
                pr.source,
                pr.created_at,
                COUNT(r.id)::int AS record_count
            FROM parser_runs pr
            JOIN parser_records r ON r.run_id = pr.run_id
            GROUP BY pr.run_id, pr.source, pr.created_at
        ),
        candidates AS (
            SELECT DISTINCT ON (m.id)
                m.id AS job_id,
                rc.run_id
            FROM missing_jobs m
            JOIN run_counts rc ON rc.source = m.source
            WHERE rc.record_count > 0
              AND (m.progress_current <= 0 OR rc.record_count = m.progress_current)
              AND rc.created_at >= m.created_at - INTERVAL '2 minutes'
              AND rc.created_at <= m.finished_at + INTERVAL '10 minutes'
              AND NOT EXISTS (
                  SELECT 1 FROM parser_jobs linked WHERE linked.db_run_id = rc.run_id
              )
            ORDER BY
                m.id,
                ABS(EXTRACT(EPOCH FROM (rc.created_at - m.created_at)))
        )
        UPDATE parser_jobs j
        SET db_run_id = candidates.run_id
        FROM candidates
        WHERE j.id = candidates.job_id
        """
    )
    try:
        result = db.execute(sql, params)
        if result.rowcount and result.rowcount > 0:
            db.commit()
    except SQLAlchemyError:
        db.rollback()


def list_results(
    db: Session,
    *,
    current_user: User,
    source: str = "",
    job_id: UUID | None = None,
    q: str = "",
    has_phone: str = "",
    created_from: str = "",
    created_to: str = "",
    all_users: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ParserResultPublic], int]:
    _repair_missing_job_run_links(db, current_user=current_user, all_users=all_users)
    where_parts, params = _build_filters(
        current_user=current_user,
        source=source,
        job_id=job_id,
        q=q,
        has_phone=has_phone,
        created_from=created_from,
        created_to=created_to,
        all_users=all_users,
    )
    where_sql = _where_sql(where_parts)
    base_from = """
        FROM parser_records r
        JOIN parser_jobs j ON j.db_run_id = r.run_id
        LEFT JOIN parser_runs runs ON runs.run_id = r.run_id
    """
    count_sql = text(f"SELECT COUNT(*) {base_from} {where_sql}")
    data_sql = text(
        f"""
        SELECT
            r.id,
            j.id::text AS job_id,
            r.run_id::text AS run_id,
            r.source,
            r.external_id,
            r.payload,
            r.created_at,
            runs.status AS run_status
        {base_from}
        {where_sql}
        ORDER BY r.created_at DESC, r.id DESC
        LIMIT :limit OFFSET :offset
        """
    )
    params_with_page = {**params, "limit": limit, "offset": offset}
    try:
        total = int(db.execute(count_sql, params).scalar_one() or 0)
        rows = db.execute(data_sql, params_with_page).mappings().all()
    except SQLAlchemyError:
        return [], 0

    items = [
        ParserResultPublic(
            id=int(row["id"]),
            job_id=UUID(str(row["job_id"])),
            run_id=UUID(str(row["run_id"])),
            source=str(row["source"] or ""),
            external_id=str(row["external_id"] or ""),
            payload=row["payload"] if isinstance(row["payload"], dict) else {},
            created_at=row["created_at"],
            run_status=str(row["run_status"] or "") or None,
        )
        for row in rows
    ]
    return items, total


def list_result_fields(
    db: Session,
    *,
    current_user: User,
    source: str = "",
    job_id: UUID | None = None,
    all_users: bool = False,
) -> list[str]:
    _repair_missing_job_run_links(db, current_user=current_user, all_users=all_users)
    where_parts, params = _build_filters(
        current_user=current_user,
        source=source,
        job_id=job_id,
        all_users=all_users,
    )
    where_sql = _where_sql(where_parts)
    sql = text(
        f"""
        SELECT DISTINCT jsonb_object_keys(r.payload) AS field
        FROM parser_records r
        JOIN parser_jobs j ON j.db_run_id = r.run_id
        {where_sql}
        ORDER BY field
        """
    )
    try:
        return [str(row[0]) for row in db.execute(sql, params).all()]
    except SQLAlchemyError:
        return []


def _result_to_export_row(result: ParserResultPublic, payload_fields: list[str]) -> dict[str, Any]:
    row: dict[str, Any] = {
        "job_id": str(result.job_id),
        "run_id": str(result.run_id),
        "source": result.source,
        "external_id": result.external_id,
        "created_at": result.created_at.isoformat(),
    }
    for field in payload_fields:
        value = result.payload.get(field, "")
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        row[field] = value
    return row


def _value_parts(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        parts: list[str] = []
        for item in value:
            parts.extend(_value_parts(item))
        return parts
    if isinstance(value, dict):
        for key in ("url", "href", "link", "text", "value", "name", "title", "label"):
            if key in value:
                parts = _value_parts(value.get(key))
                if parts:
                    return parts
        return [json.dumps(value, ensure_ascii=False)]
    text_value = str(value).strip()
    return [text_value] if text_value else []


def _payload_values(payload: dict[str, Any], *keys: str) -> list[str]:
    lowered: dict[str, Any] = {}
    for key, value in payload.items():
        lowered.setdefault(str(key).lower(), value)

    values: list[str] = []
    seen: set[str] = set()
    for key in keys:
        raw_value = payload.get(key)
        if raw_value is None:
            raw_value = lowered.get(key.lower())
        for part in _value_parts(raw_value):
            if part and part not in seen:
                seen.add(part)
                values.append(part)
    return values


def _payload_value(payload: dict[str, Any], *keys: str, default: str = "") -> str:
    values = _payload_values(payload, *keys)
    return values[0] if values else default


def _normalize_phone(raw_value: Any) -> str:
    digits = re.sub(r"\D+", "", str(raw_value or ""))
    if not digits:
        return ""
    if len(digits) == 11 and digits.startswith("8"):
        digits = f"7{digits[1:]}"
    elif len(digits) == 10:
        digits = f"7{digits}"
    if len(digits) < 8:
        return ""
    return digits


def _phones_from_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        phones: list[str] = []
        for item in value:
            phones.extend(_phones_from_value(item))
        return phones
    if isinstance(value, dict):
        phones = []
        priority_keys = ("phone", "phones", "phone_1", "phone_2", "phone_3", "number", "text", "value", "href", "url")
        for key in priority_keys:
            if key in value:
                phones.extend(_phones_from_value(value.get(key)))
        if phones:
            return phones
        for item in value.values():
            phones.extend(_phones_from_value(item))
        return phones

    text_value = str(value)
    raw_values = PHONE_RE.findall(text_value) or re.split(r"[;,\n|/]+", text_value)
    phones = []
    for raw_phone in raw_values:
        phone = _normalize_phone(raw_phone)
        if phone:
            phones.append(phone)
    return phones


def _extract_phones(payload: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    phone_keys = (
        "seller_phone",
        "phones",
        "phone",
        "phone_1",
        "phone_2",
        "phone_3",
        "phone_numbers",
        "mobile",
        "contact_phone",
        "contacts",
        "whatsapp",
        "whatsapp_1",
    )
    lowered = {str(key).lower(): value for key, value in payload.items()}
    for key in phone_keys:
        if key in payload:
            values.append(payload[key])
        elif key.lower() in lowered:
            values.append(lowered[key.lower()])

    phones: list[str] = []
    seen: set[str] = set()
    for value in values:
        for phone in _phones_from_value(value):
            if phone not in seen:
                seen.add(phone)
                phones.append(phone)
    return phones


def _whatsapp_value(payload: dict[str, Any], primary_phone: str) -> str:
    raw_value = _payload_value(payload, "whatsapp_1", "whatsapp", "WhatsApp")
    if raw_value:
        if raw_value.startswith(("http://", "https://")):
            return raw_value
        phone = _normalize_phone(raw_value)
        if phone:
            return f"https://wa.me/{phone}"
        return raw_value
    return f"https://wa.me/{primary_phone}" if primary_phone else ""


def _limited_values(payload: dict[str, Any], keys: tuple[str, ...], limit: int) -> list[str]:
    values = _payload_values(payload, *keys)
    return [*values[:limit], *([""] * max(0, limit - len(values)))]


def _adservlet_business_row(result: ParserResultPublic) -> list[str]:
    payload = result.payload
    phones = [*_extract_phones(payload), "", "", ""]
    emails = _limited_values(payload, ("email_1", "email_2", "email_3", "email", "emails"), 3)
    facebook = _payload_value(payload, "facebook_1", "facebook", "Facebook")
    instagram = _limited_values(payload, ("instagram_1", "instagram_2", "instagram_3", "instagram", "Instagram"), 3)
    source = result.source.strip().lower()

    return [
        phones[0],
        phones[1],
        phones[2],
        _whatsapp_value(payload, phones[0]),
        _payload_value(payload, "telegram_1", "telegram", "Telegram"),
        _payload_value(payload, "name", "title", "seller_name", "company_name", "Title / Name"),
        _payload_value(payload, "description", "Описание"),
        _payload_value(payload, "rubrics", "rubric", "category", "categories", "rubrics (интересы)"),
        _payload_value(payload, "country", "Страна", default="Казахстан"),
        _payload_value(payload, "city", "location", "region", "Location"),
        _payload_value(payload, "district", "living_area", "microdistrict", "district_area", "район"),
        _payload_value(payload, "address", "address_name", "full_address", "street", "адрес"),
        emails[0],
        emails[1],
        emails[2],
        facebook,
        instagram[0],
        instagram[1],
        instagram[2],
        _payload_value(payload, "type", default="branch" if source == "2gis" else ""),
    ]


def _adservlet_olx_row(result: ParserResultPublic) -> list[str]:
    payload = result.payload
    phones = [*_extract_phones(payload), "", "", ""]
    emails = _limited_values(payload, ("email_1", "email_2", "email_3", "email", "emails"), 3)
    facebook = _payload_value(payload, "facebook_1", "facebook", "Facebook")
    instagram = _limited_values(payload, ("instagram_1", "instagram_2", "instagram_3", "instagram", "Instagram"), 3)

    return [
        phones[0],
        phones[1],
        phones[2],
        _whatsapp_value(payload, phones[0]),
        _payload_value(payload, "telegram_1", "telegram", "Telegram"),
        _payload_value(payload, "seller_name", "name"),
        _payload_value(payload, "country", "Страна", default="Казахстан"),
        _payload_value(payload, "city", "region", "location", "Location"),
        _payload_value(payload, "district", "living_area", "microdistrict", "address", "address_name"),
        _payload_value(payload, "category", "categories", "rubric", "category (интересы)"),
        _payload_value(payload, "title", "name"),
        _payload_value(payload, "description", "Описание"),
        _payload_value(payload, "пол", "gender", "sex"),
        _payload_value(payload, "возраст", "age"),
        emails[0],
        emails[1],
        emails[2],
        facebook,
        instagram[0],
        instagram[1],
        instagram[2],
    ]


def _write_adservlet_sheet(workbook: Any, sheet_name: str, headers: tuple[str, ...], rows: list[list[str]]) -> None:
    worksheet = workbook.add_worksheet(sheet_name)
    header_format = workbook.add_format({"bold": True, "bg_color": "#F2F4F7"})
    for col, header in enumerate(headers):
        worksheet.write(0, col, header, header_format)
        worksheet.set_column(col, col, min(max(len(header) + 2, 14), 30))
    for row_index, row in enumerate(rows, start=1):
        for col, value in enumerate(row):
            worksheet.write(row_index, col, value)
    worksheet.freeze_panes(1, 0)
    worksheet.autofilter(0, 0, max(len(rows), 1), max(len(headers) - 1, 0))


def _adservlet_xlsx_response(items: list[ParserResultPublic]) -> StreamingResponse:
    try:
        import xlsxwriter
    except ModuleNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="xlsxwriter is not installed") from exc

    business_rows = [
        _adservlet_business_row(item)
        for item in items
        if item.source.strip().lower() in ADSERVLET_BUSINESS_SOURCES
    ]
    olx_rows = [
        _adservlet_olx_row(item)
        for item in items
        if item.source.strip().lower() in ADSERVLET_OLX_SOURCES
    ]

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    _write_adservlet_sheet(workbook, ADSERVLET_BUSINESS_SHEET, ADSERVLET_BUSINESS_HEADERS, business_rows)
    _write_adservlet_sheet(workbook, ADSERVLET_OLX_SHEET, ADSERVLET_OLX_HEADERS, olx_rows)
    workbook.close()
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="parser_results_adservlet.xlsx"'},
    )


def export_results_response(
    db: Session,
    *,
    current_user: User,
    export_format: str,
    fields: str | list[str] | None = None,
    source: str = "",
    job_id: UUID | None = None,
    q: str = "",
    has_phone: str = "",
    created_from: str = "",
    created_to: str = "",
    all_users: bool = False,
    adservlet: bool = False,
) -> Response:
    items, _ = list_results(
        db,
        current_user=current_user,
        source=source,
        job_id=job_id,
        q=q,
        has_phone=has_phone,
        created_from=created_from,
        created_to=created_to,
        all_users=all_users,
        limit=10_000,
        offset=0,
    )

    if adservlet:
        if export_format != "xlsx":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Adservlet export supports xlsx only")
        return _adservlet_xlsx_response(items)

    payload_fields = _normalize_fields(fields)
    if not payload_fields:
        seen: set[str] = set()
        for item in items:
            for key in item.payload.keys():
                if key not in seen:
                    seen.add(key)
                    payload_fields.append(key)

    rows = [_result_to_export_row(item, payload_fields) for item in items]
    headers = [*BASE_EXPORT_FIELDS, *payload_fields]
    filename = f"parser_results.{export_format}"

    if export_format == "json":
        body = json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8")
        return Response(
            content=body,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    if export_format == "csv":
        buffer = io.StringIO()
        buffer.write("\ufeff")
        writer = csv.DictWriter(buffer, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        return Response(
            content=buffer.getvalue().encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    if export_format == "xlsx":
        try:
            import xlsxwriter
        except ModuleNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="xlsxwriter is not installed") from exc
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        worksheet = workbook.add_worksheet("results")
        header_format = workbook.add_format({"bold": True, "bg_color": "#F2F4F7"})
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)
        for row_index, row in enumerate(rows, start=1):
            for col, header in enumerate(headers):
                worksheet.write(row_index, col, row.get(header, ""))
        worksheet.freeze_panes(1, 0)
        worksheet.autofilter(0, 0, max(len(rows), 1), max(len(headers) - 1, 0))
        workbook.close()
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported export format")
