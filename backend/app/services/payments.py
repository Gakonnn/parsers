from __future__ import annotations

import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.billing import (
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentQrSetting,
    PaymentStatus,
    SubscriptionPlan,
    SubscriptionStatus,
    UserSubscription,
)
from app.models.user import User
from app.services.kaspi_pos import (
    KASPI_QR_PROVIDER,
    classify_qr_status,
    create_qr_for_invoice,
    extract_qr_status,
    fetch_qr_status,
)


MANUAL_QR_PROVIDER = "manual_qr"


def _now() -> datetime:
    return datetime.now(UTC)


def find_plan(db: Session, *, plan_id: UUID | None = None, plan_code: str | None = None) -> SubscriptionPlan:
    if plan_id is None and not plan_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="plan_id or plan_code is required")
    statement = select(SubscriptionPlan).where(SubscriptionPlan.is_active.is_(True))
    if plan_id is not None:
        statement = statement.where(SubscriptionPlan.id == plan_id)
    else:
        statement = statement.where(SubscriptionPlan.code == str(plan_code).strip().lower())
    plan = db.scalar(statement)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return plan


def create_invoice_for_plan(db: Session, *, user: User, plan: SubscriptionPlan, provider: str = "manual") -> Invoice:
    provider = (provider or "manual").strip().lower()
    settings = get_settings()
    invoice = Invoice(
        user_id=user.id,
        plan_id=plan.id,
        status=InvoiceStatus.PENDING.value,
        amount_kzt=plan.price_kzt,
        currency=plan.currency,
        provider=provider,
        expires_at=_now() + timedelta(hours=24),
        metadata_json={
            "plan_code": plan.code,
            "success_url": settings.payment_success_url,
            "cancel_url": settings.payment_cancel_url,
        },
    )
    db.add(invoice)
    db.flush()

    if provider == KASPI_QR_PROVIDER:
        qr_response = create_qr_for_invoice(invoice)
        qr_data = qr_response.get("Data") if isinstance(qr_response.get("Data"), dict) else {}
        qr_operation_id = str(qr_data.get("QrOperationId") or "").strip()
        qr_token = str(qr_data.get("QrToken") or "").strip()
        invoice.provider_invoice_id = qr_operation_id
        invoice.payment_url = qr_token
        invoice.metadata_json = {
            **(invoice.metadata_json or {}),
            "kaspi_qr": {
                "qr_operation_id": qr_operation_id,
                "qr_token": qr_token,
                "expire_date": qr_data.get("ExpireDate"),
                "receipt_url": qr_data.get("ReceiptUrl"),
                "amount": qr_data.get("Amount") or invoice.amount_kzt,
                "status": qr_data.get("Status") or "QrTokenCreated",
                "status_kind": "pending",
                "created_response": qr_response,
            },
        }
    else:
        # Provider integration can replace this URL with a real checkout link.
        # Without a configured provider we keep it empty instead of exposing a non-production payment URL.
        invoice.provider_invoice_id = str(invoice.id)
        invoice.payment_url = _build_checkout_url(invoice, plan)
    db.flush()
    return invoice


def get_active_payment_qr_setting(db: Session) -> PaymentQrSetting | None:
    return db.scalar(
        select(PaymentQrSetting)
        .where(PaymentQrSetting.is_active.is_(True), PaymentQrSetting.image_data.is_not(None))
        .order_by(PaymentQrSetting.updated_at.desc(), PaymentQrSetting.created_at.desc())
    )


def get_latest_payment_qr_setting(db: Session) -> PaymentQrSetting | None:
    return db.scalar(select(PaymentQrSetting).order_by(PaymentQrSetting.updated_at.desc(), PaymentQrSetting.created_at.desc()))


def upsert_payment_qr_setting(
    db: Session,
    *,
    title: str,
    note: str | None,
    image_data: str | None,
    is_active: bool,
    admin: User,
) -> PaymentQrSetting:
    setting = get_latest_payment_qr_setting(db)
    if setting is None:
        setting = PaymentQrSetting(created_by_user_id=admin.id)
        db.add(setting)
    setting.title = title.strip() or "Kaspi QR"
    setting.note = note.strip() if isinstance(note, str) and note.strip() else None
    setting.image_data = image_data.strip() if isinstance(image_data, str) and image_data.strip() else None
    setting.is_active = is_active
    setting.created_by_user_id = setting.created_by_user_id or admin.id
    db.flush()
    return setting


def attach_manual_qr_receipt(invoice: Invoice, *, receipt_id: str, qr_setting: PaymentQrSetting | None) -> None:
    metadata = dict(invoice.metadata_json or {})
    metadata["manual_qr"] = {
        "receipt_id": receipt_id.strip(),
        "submitted_at": _now().isoformat(),
        "status": "waiting_moderation",
        "qr_setting_id": str(qr_setting.id) if qr_setting is not None else None,
        "qr_title": qr_setting.title if qr_setting is not None else None,
    }
    invoice.metadata_json = metadata
    invoice.provider_invoice_id = receipt_id.strip()


def _build_checkout_url(invoice: Invoice, plan: SubscriptionPlan) -> str:
    settings = get_settings()
    template = settings.payment_checkout_url_template.strip()
    if template:
        try:
            return template.format(
                invoice_id=invoice.id,
                plan_id=plan.id,
                plan_code=plan.code,
                amount_kzt=plan.price_kzt,
                currency=plan.currency,
            )
        except Exception:
            pass
    return ""


def activate_subscription_from_invoice(db: Session, invoice: Invoice) -> UserSubscription:
    now = _now()
    active_subscriptions = db.scalars(
        select(UserSubscription).where(
            UserSubscription.user_id == invoice.user_id,
            UserSubscription.status.in_([SubscriptionStatus.ACTIVE.value, SubscriptionStatus.TRIALING.value]),
        )
    ).all()
    for subscription in active_subscriptions:
        subscription.status = SubscriptionStatus.EXPIRED.value
        subscription.ends_at = subscription.ends_at or now

    subscription = UserSubscription(
        user_id=invoice.user_id,
        plan_id=invoice.plan_id,
        status=SubscriptionStatus.ACTIVE.value,
    )
    db.add(subscription)
    db.flush()
    return subscription


def mark_invoice_paid(
    db: Session,
    invoice: Invoice,
    *,
    provider_payment_id: str = "",
    raw_payload: dict[str, Any] | None = None,
) -> Payment:
    if invoice.status == InvoiceStatus.PAID.value:
        existing_payment = db.scalar(select(Payment).where(Payment.invoice_id == invoice.id, Payment.status == PaymentStatus.SUCCEEDED.value))
        if existing_payment is not None:
            return existing_payment

    invoice.status = InvoiceStatus.PAID.value
    invoice.paid_at = invoice.paid_at or _now()
    payment = Payment(
        invoice_id=invoice.id,
        user_id=invoice.user_id,
        status=PaymentStatus.SUCCEEDED.value,
        amount_kzt=invoice.amount_kzt,
        currency=invoice.currency,
        provider=invoice.provider,
        provider_payment_id=provider_payment_id or str(invoice.id),
        raw_payload=raw_payload or {},
    )
    db.add(payment)
    activate_subscription_from_invoice(db, invoice)
    db.flush()
    return payment


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    secret = get_settings().payment_webhook_secret.encode("utf-8")
    expected = hmac.new(secret, raw_body, "sha256").hexdigest()
    return hmac.compare_digest(expected, signature or "")


def process_payment_webhook(db: Session, *, payload: dict[str, Any]) -> Payment:
    invoice_id = payload.get("invoice_id")
    provider_invoice_id = str(payload.get("provider_invoice_id") or "").strip()
    statement = select(Invoice)
    if invoice_id:
        statement = statement.where(Invoice.id == invoice_id)
    elif provider_invoice_id:
        statement = statement.where(Invoice.provider_invoice_id == provider_invoice_id)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invoice_id or provider_invoice_id is required")
    invoice = db.scalar(statement)
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    incoming_status = str(payload.get("status") or "").strip().lower()
    provider_payment_id = str(payload.get("provider_payment_id") or "").strip()
    raw_payload = payload.get("raw_payload") if isinstance(payload.get("raw_payload"), dict) else payload
    if incoming_status in {"paid", "success", "succeeded", "completed"}:
        return mark_invoice_paid(db, invoice, provider_payment_id=provider_payment_id, raw_payload=raw_payload)

    payment_status = PaymentStatus.FAILED.value if incoming_status in {"failed", "error"} else PaymentStatus.CANCELLED.value
    invoice.status = InvoiceStatus.FAILED.value if payment_status == PaymentStatus.FAILED.value else InvoiceStatus.CANCELLED.value
    payment = Payment(
        invoice_id=invoice.id,
        user_id=invoice.user_id,
        status=payment_status,
        amount_kzt=invoice.amount_kzt,
        currency=invoice.currency,
        provider=invoice.provider,
        provider_payment_id=provider_payment_id or str(invoice.id),
        raw_payload=raw_payload,
    )
    db.add(payment)
    db.flush()
    return payment


def _merge_invoice_metadata(invoice: Invoice, key: str, payload: dict[str, Any]) -> None:
    metadata = dict(invoice.metadata_json or {})
    existing = metadata.get(key) if isinstance(metadata.get(key), dict) else {}
    metadata[key] = {**existing, **payload}
    invoice.metadata_json = metadata


def sync_kaspi_invoice_status(db: Session, invoice: Invoice) -> Invoice:
    if invoice.provider != KASPI_QR_PROVIDER:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice is not a Kaspi QR invoice")
    if invoice.status == InvoiceStatus.PAID.value:
        return invoice
    qr_operation_id = str(invoice.provider_invoice_id or "").strip()
    if not qr_operation_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kaspi QR operation id is missing")

    status_payload = fetch_qr_status(qr_operation_id)
    status_value = extract_qr_status(status_payload)
    status_kind = classify_qr_status(status_value)
    _merge_invoice_metadata(
        invoice,
        "kaspi_qr",
        {
            "qr_operation_id": qr_operation_id,
            "status": status_value,
            "status_kind": status_kind,
            "last_status_response": status_payload,
            "last_checked_at": _now().isoformat(),
        },
    )
    if status_kind == "success":
        mark_invoice_paid(db, invoice, provider_payment_id=qr_operation_id, raw_payload=status_payload)
    elif status_kind == "expired":
        invoice.status = InvoiceStatus.EXPIRED.value
    elif status_kind == "failed":
        invoice.status = InvoiceStatus.FAILED.value
    db.flush()
    return invoice


def process_kaspi_webhook(db: Session, *, payload: dict[str, Any]) -> Invoice:
    qr_operation_id = str(payload.get("paymentId") or payload.get("provider_invoice_id") or "").strip()
    if not qr_operation_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="paymentId is required")
    invoice = db.scalar(
        select(Invoice).where(
            Invoice.provider == KASPI_QR_PROVIDER,
            Invoice.provider_invoice_id == qr_operation_id,
        )
    )
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kaspi invoice not found")

    event = str(payload.get("event") or "").strip()
    status_value = str(payload.get("status") or "").strip()
    status_kind = classify_qr_status(status_value)
    if event == "payment.success":
        status_kind = "success"
    elif event == "payment.expired":
        status_kind = "expired"
    elif event == "payment.failed":
        status_kind = "failed"

    _merge_invoice_metadata(
        invoice,
        "kaspi_qr",
        {
            "qr_operation_id": qr_operation_id,
            "status": status_value,
            "status_kind": status_kind,
            "last_webhook": payload,
            "last_webhook_at": _now().isoformat(),
        },
    )
    if status_kind == "success":
        mark_invoice_paid(db, invoice, provider_payment_id=qr_operation_id, raw_payload=payload)
    elif status_kind == "expired":
        invoice.status = InvoiceStatus.EXPIRED.value
    elif status_kind == "failed":
        invoice.status = InvoiceStatus.FAILED.value
    db.flush()
    return invoice


def webhook_payload_from_raw(raw_body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload")
    return payload
