from __future__ import annotations

import re
from typing import Any


PHONE_CANDIDATE_RE = re.compile(r"(?:\+|00)?\d[\d\s().-]{7,}\d")


def normalize_phone_number(raw: Any) -> str:
    """Return phone in international compact format, e.g. +77051234567."""
    value = str(raw or "").strip()
    if not value:
        return ""

    digits = re.sub(r"\D", "", value)
    if not digits:
        return ""

    if digits.startswith("00") and len(digits) > 10:
        digits = digits[2:]

    if len(digits) == 12 and digits.startswith("77"):
        digits = digits[-11:]

    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits

    if len(digits) < 8 or len(digits) > 15:
        return ""

    return f"+{digits}"


def normalize_phone_numbers(raw: Any) -> list[str]:
    """Extract and normalize all phone-like values, preserving first-seen order."""
    value = str(raw or "").strip()
    if not value:
        return []

    candidates = PHONE_CANDIDATE_RE.findall(value) or [value]
    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        phone = normalize_phone_number(candidate)
        if phone and phone not in seen:
            normalized.append(phone)
            seen.add(phone)
    return normalized


def normalize_phone_value(raw: Any, *, joiner: str = ";") -> str:
    return joiner.join(normalize_phone_numbers(raw))


def normalize_payload_phone_fields(payload: Any) -> Any:
    """Normalize dict/list values whose keys clearly represent phone fields."""
    if isinstance(payload, list):
        return [normalize_payload_phone_fields(item) for item in payload]
    if not isinstance(payload, dict):
        return payload

    normalized: dict[str, Any] = {}
    for key, value in payload.items():
        key_text = str(key).lower()
        if isinstance(value, str) and ("phone" in key_text or "телефон" in key_text):
            normalized[key] = normalize_phone_value(value) or value
        elif isinstance(value, list) and ("phone" in key_text or "телефон" in key_text):
            normalized[key] = normalize_phone_numbers("; ".join(str(item) for item in value)) or value
        else:
            normalized[key] = normalize_payload_phone_fields(value)
    return normalized


def normalize_2gis_contact_phones(payload: Any) -> Any:
    """Normalize 2GIS contact objects with type=phone."""
    if isinstance(payload, list):
        return [normalize_2gis_contact_phones(item) for item in payload]
    if not isinstance(payload, dict):
        return payload

    normalized: dict[str, Any] = {}
    is_phone_contact = str(payload.get("type", "")).lower() == "phone"
    for key, value in payload.items():
        if is_phone_contact and key in {"text", "value"} and isinstance(value, str):
            normalized[key] = normalize_phone_number(value) or value
        else:
            normalized[key] = normalize_2gis_contact_phones(value)
    return normalized
