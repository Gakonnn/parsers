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
from app.models.billing import Invoice, InvoiceStatus, Payment, PaymentStatus, SubscriptionPlan, SubscriptionStatus, UserSubscription
from app.models.user import User


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
            "success_url": get_settings().payment_success_url,
            "cancel_url": get_settings().payment_cancel_url,
        },
    )
    db.add(invoice)
    db.flush()
    # Provider integration can replace this URL with a real checkout link.
    # Without a configured provider we keep it empty instead of exposing a non-production payment URL.
    invoice.provider_invoice_id = str(invoice.id)
    invoice.payment_url = _build_checkout_url(invoice, plan)
    db.flush()
    return invoice


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


def webhook_payload_from_raw(raw_body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload")
    return payload
