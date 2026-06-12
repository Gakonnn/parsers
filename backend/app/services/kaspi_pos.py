from __future__ import annotations

import hmac
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.models.billing import Invoice


KASPI_QR_PROVIDER = "kaspi_qr"
KASPI_QR_SUCCESS_STATUSES = {"Processed"}
KASPI_QR_PENDING_STATUSES = {"QrTokenCreated", "QrTokenScanned", "Wait"}
KASPI_QR_EXPIRED_STATUSES = {"QrTokenDiscarded", "Expired"}


class KaspiPosError(RuntimeError):
    pass


def kaspi_pos_configured() -> bool:
    settings = get_settings()
    return bool(
        settings.kaspi_pos_base_url
        and settings.kaspi_pos_token_sn
        and settings.kaspi_pos_vtoken_secret
    )


def _kaspi_headers() -> dict[str, str]:
    settings = get_settings()
    if not kaspi_pos_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kaspi POS is not configured. Set KASPI_POS_TOKEN_SN and KASPI_POS_VTOKEN_SECRET.",
        )
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Token-SN": settings.kaspi_pos_token_sn,
        "X-Vtoken-Secret": settings.kaspi_pos_vtoken_secret,
    }
    if settings.kaspi_pos_profile_id:
        headers["X-Profile-Id"] = settings.kaspi_pos_profile_id
    return headers


def _request_json(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = get_settings()
    url = f"{settings.kaspi_pos_base_url}{path}"
    body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=body, headers=_kaspi_headers(), method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=settings.kaspi_pos_timeout_sec) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raw_error = exc.read().decode("utf-8", "replace")
        raise KaspiPosError(f"Kaspi POS returned HTTP {exc.code}: {raw_error}") from exc
    except urllib.error.URLError as exc:
        raise KaspiPosError(f"Kaspi POS is unavailable: {exc.reason}") from exc
    except TimeoutError as exc:
        raise KaspiPosError("Kaspi POS request timed out") from exc

    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise KaspiPosError("Kaspi POS returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise KaspiPosError("Kaspi POS returned invalid payload")
    return data


def create_qr_for_invoice(invoice: Invoice) -> dict[str, Any]:
    settings = get_settings()
    if invoice.amount_kzt <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kaspi QR amount must be greater than zero")

    payload = {
        "amount": invoice.amount_kzt,
        "latitude": settings.kaspi_pos_latitude,
        "longitude": settings.kaspi_pos_longitude,
    }
    try:
        response = _request_json("POST", "/api/qr/create", payload)
    except KaspiPosError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    if int(response.get("StatusCode") or 0) != 0:
        message = response.get("Message") or response.get("message") or "Kaspi POS rejected QR creation"
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(message))

    data = response.get("Data")
    if not isinstance(data, dict) or not data.get("QrOperationId") or not data.get("QrToken"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Kaspi POS returned QR without operation id/token")
    return response


def fetch_qr_status(qr_operation_id: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({"qrOperationId": qr_operation_id})
    try:
        return _request_json("GET", f"/api/qr/status?{query}")
    except KaspiPosError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


def extract_qr_status(payload: dict[str, Any]) -> str:
    data = payload.get("Data")
    if isinstance(data, dict):
        return str(data.get("Status") or "").strip()
    return str(payload.get("status") or "").strip()


def classify_qr_status(status_value: str) -> str:
    if status_value in KASPI_QR_SUCCESS_STATUSES:
        return "success"
    if status_value in KASPI_QR_PENDING_STATUSES:
        return "pending"
    if status_value in KASPI_QR_EXPIRED_STATUSES:
        return "expired"
    if status_value:
        return "failed"
    return "pending"


def verify_kaspi_webhook_signature(raw_body: bytes, signature: str) -> bool:
    secret = get_settings().kaspi_pos_webhook_secret
    if not secret:
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, "sha256").hexdigest()
    return hmac.compare_digest(expected, signature or "")

