from __future__ import annotations

import re
from typing import Any


def normalize_phone_number(raw: Any) -> str:
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


def normalize_2gis_contact_phones(payload: Any) -> Any:
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
