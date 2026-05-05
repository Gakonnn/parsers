from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.config import get_settings
from app.db.session import get_db
from app.models.billing import Invoice, Payment, SubscriptionPlan, SubscriptionStatus, UserSubscription
from app.models.user import User
from app.schemas.billing import (
    AssignSubscriptionRequest,
    InvoiceCreateRequest,
    InvoiceListResponse,
    InvoicePublic,
    PaymentPublic,
    PaymentProviderPublic,
    SubscriptionPlanCreate,
    SubscriptionPlanPublic,
    SubscriptionPlanUpdate,
    UsageSummary,
    UserSubscriptionPublic,
)
from app.services.payments import (
    create_invoice_for_plan,
    find_plan,
    mark_invoice_paid,
    process_payment_webhook,
    verify_webhook_signature,
    webhook_payload_from_raw,
)
from app.services.audit import log_event, notify_user
from app.services.quota import current_month_start, get_monthly_usage, get_or_create_active_subscription


router = APIRouter()


@router.get("/provider", response_model=PaymentProviderPublic)
def read_payment_provider(_: User = Depends(get_current_user)) -> PaymentProviderPublic:
    settings = get_settings()
    return PaymentProviderPublic(
        provider_name=settings.payment_provider_name,
        checkout_mode=settings.payment_checkout_mode,
        checkout_url_template=settings.payment_checkout_url_template or None,
        success_url=settings.payment_success_url or None,
        cancel_url=settings.payment_cancel_url or None,
        webhook_secret_configured=bool(settings.payment_webhook_secret.strip()),
    )


@router.get("/plans", response_model=list[SubscriptionPlanPublic])
def list_public_plans(db: Session = Depends(get_db)) -> list[SubscriptionPlan]:
    return list(
        db.scalars(
            select(SubscriptionPlan)
            .where(SubscriptionPlan.is_active.is_(True), SubscriptionPlan.is_public.is_(True))
            .order_by(SubscriptionPlan.price_kzt.asc(), SubscriptionPlan.name.asc())
        ).all()
    )


@router.get("/me", response_model=UsageSummary)
def read_my_usage(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> UsageSummary:
    subscription = get_or_create_active_subscription(db, current_user)
    jobs_used, records_used = get_monthly_usage(db, current_user)
    plan = subscription.plan
    db.commit()
    return UsageSummary(
        subscription=UserSubscriptionPublic.model_validate(subscription),
        jobs_used=jobs_used,
        records_used=records_used,
        jobs_remaining=max(-1, plan.max_jobs_per_month - jobs_used),
        records_remaining=max(-1, plan.max_records_per_month - records_used),
        month_started_at=current_month_start(),
    )


@router.post("/invoices", response_model=InvoicePublic, status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: InvoiceCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Invoice:
    plan = find_plan(db, plan_id=payload.plan_id, plan_code=payload.plan_code)
    invoice = create_invoice_for_plan(db, user=current_user, plan=plan, provider=payload.provider)
    log_event(
        db,
        event_type="invoice.created",
        actor_user=current_user,
        target_user=current_user,
        entity_type="invoice",
        entity_id=invoice.id,
        message="Payment invoice created",
        payload={"plan_code": plan.code, "amount_kzt": invoice.amount_kzt, "provider": invoice.provider},
        request=request,
    )
    notify_user(
        db,
        user=current_user,
        type="invoice.created",
        title="Счет создан",
        body=f"Создан счет на тариф {plan.name}.",
        payload={"invoice_id": str(invoice.id), "plan_code": plan.code, "amount_kzt": invoice.amount_kzt},
    )
    db.commit()
    db.refresh(invoice)
    return invoice


@router.get("/invoices", response_model=InvoiceListResponse)
def list_my_invoices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = 50,
    offset: int = 0,
) -> InvoiceListResponse:
    limit = max(1, min(200, int(limit)))
    offset = max(0, int(offset))
    statement = (
        select(Invoice)
        .where(Invoice.user_id == current_user.id)
        .order_by(Invoice.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    count_statement = select(func.count()).select_from(Invoice).where(Invoice.user_id == current_user.id)
    return InvoiceListResponse(
        items=list(db.scalars(statement).all()),
        total=db.scalar(count_statement) or 0,
    )


@router.get("/invoices/{invoice_id}", response_model=InvoicePublic)
def get_my_invoice(invoice_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Invoice:
    invoice = db.scalar(select(Invoice).where(Invoice.id == invoice_id, Invoice.user_id == current_user.id))
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return invoice


@router.post("/invoices/{invoice_id}/mock-pay", response_model=PaymentPublic)
def mock_pay_invoice(
    invoice_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Payment:
    invoice = db.scalar(select(Invoice).where(Invoice.id == invoice_id, Invoice.user_id == current_user.id))
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    payment = mark_invoice_paid(db, invoice, provider_payment_id=f"mock_{invoice.id}", raw_payload={"mock": True})
    log_event(
        db,
        event_type="invoice.paid",
        actor_user=current_user,
        target_user=current_user,
        entity_type="invoice",
        entity_id=invoice.id,
        message="Invoice paid with mock provider",
        payload={"payment_id": str(payment.id), "provider": payment.provider},
        request=request,
    )
    notify_user(
        db,
        user=current_user,
        type="payment.succeeded",
        title="Оплата прошла успешно",
        body="Тариф активирован.",
        payload={"invoice_id": str(invoice.id), "payment_id": str(payment.id)},
    )
    db.commit()
    db.refresh(payment)
    return payment


@router.post("/webhook", response_model=PaymentPublic)
async def payment_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_payment_signature: str = Header(default=""),
) -> Payment:
    raw_body = await request.body()
    if not verify_webhook_signature(raw_body, x_payment_signature):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid payment webhook signature")
    payload = webhook_payload_from_raw(raw_body)
    payment = process_payment_webhook(db, payload=payload)
    user = db.scalar(select(User).where(User.id == payment.user_id))
    log_event(
        db,
        event_type="payment.webhook_received",
        target_user=user,
        entity_type="payment",
        entity_id=payment.id,
        message="Payment webhook processed",
        payload={"status": payment.status, "invoice_id": str(payment.invoice_id), "provider": payment.provider},
        request=request,
    )
    if user is not None:
        notify_user(
            db,
            user=user,
            type=f"payment.{payment.status}",
            title="Статус оплаты обновлен",
            body=f"Платеж получил статус: {payment.status}.",
            payload={"invoice_id": str(payment.invoice_id), "payment_id": str(payment.id)},
        )
    db.commit()
    db.refresh(payment)
    return payment


@router.post("/admin/plans", response_model=SubscriptionPlanPublic, status_code=status.HTTP_201_CREATED)
def create_plan(
    payload: SubscriptionPlanCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> SubscriptionPlan:
    code = payload.code.strip().lower()
    existing = db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == code))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Plan code already exists")
    plan = SubscriptionPlan(
        code=code,
        name=payload.name,
        description=payload.description,
        price_kzt=payload.price_kzt,
        currency=payload.currency,
        billing_period=payload.billing_period,
        max_jobs_per_month=payload.max_jobs_per_month,
        max_records_per_month=payload.max_records_per_month,
        allowed_sources=payload.allowed_sources,
        is_active=payload.is_active,
        is_public=payload.is_public,
    )
    db.add(plan)
    db.flush()
    log_event(
        db,
        event_type="plan.created",
        actor_user=current_admin,
        entity_type="subscription_plan",
        entity_id=plan.id,
        message="Subscription plan created",
        payload={"code": plan.code, "price_kzt": plan.price_kzt},
        request=request,
    )
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/admin/plans", response_model=list[SubscriptionPlanPublic])
def list_admin_plans(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> list[SubscriptionPlan]:
    return list(db.scalars(select(SubscriptionPlan).order_by(SubscriptionPlan.price_kzt.asc(), SubscriptionPlan.name.asc())).all())


@router.patch("/admin/plans/{plan_id}", response_model=SubscriptionPlanPublic)
def update_plan(
    plan_id: UUID,
    payload: SubscriptionPlanUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> SubscriptionPlan:
    plan = db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id))
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(plan, key, value)
    if updates:
        log_event(
            db,
            event_type="plan.updated",
            actor_user=current_admin,
            entity_type="subscription_plan",
            entity_id=plan.id,
            message="Subscription plan updated",
            payload={"updated_fields": sorted(updates.keys()), "code": plan.code},
            request=request,
        )
    db.commit()
    db.refresh(plan)
    return plan


@router.post("/admin/users/{user_id}/subscription", response_model=UserSubscriptionPublic)
def assign_user_subscription(
    user_id: UUID,
    payload: AssignSubscriptionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> UserSubscription:
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if payload.plan_id is None and not payload.plan_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="plan_id or plan_code is required")

    plan_statement = select(SubscriptionPlan)
    if payload.plan_id is not None:
        plan_statement = plan_statement.where(SubscriptionPlan.id == payload.plan_id)
    else:
        plan_statement = plan_statement.where(SubscriptionPlan.code == str(payload.plan_code).strip().lower())
    plan = db.scalar(plan_statement)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    now = datetime.now(UTC)
    active_subscriptions = db.scalars(
        select(UserSubscription).where(
            UserSubscription.user_id == user.id,
            UserSubscription.status.in_([SubscriptionStatus.ACTIVE.value, SubscriptionStatus.TRIALING.value]),
        )
    ).all()
    for subscription in active_subscriptions:
        subscription.status = SubscriptionStatus.EXPIRED.value
        subscription.ends_at = subscription.ends_at or now

    subscription = UserSubscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE.value,
        ends_at=payload.ends_at,
    )
    db.add(subscription)
    db.flush()
    log_event(
        db,
        event_type="subscription.assigned",
        actor_user=current_admin,
        target_user=user,
        entity_type="user_subscription",
        entity_id=subscription.id,
        message="Subscription assigned by admin",
        payload={"plan_code": plan.code, "ends_at": payload.ends_at.isoformat() if payload.ends_at else None},
        request=request,
    )
    notify_user(
        db,
        user=user,
        type="subscription.assigned",
        title="Тариф обновлен",
        body=f"Администратор назначил тариф {plan.name}.",
        payload={"subscription_id": str(subscription.id), "plan_code": plan.code},
    )
    db.commit()
    db.refresh(subscription)
    return subscription


@router.get("/admin/invoices", response_model=InvoiceListResponse)
def list_all_invoices(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
    user_id: UUID | None = None,
    status_filter: str = "",
    limit: int = 50,
    offset: int = 0,
) -> InvoiceListResponse:
    limit = max(1, min(200, int(limit)))
    offset = max(0, int(offset))
    statement = select(Invoice).order_by(Invoice.created_at.desc()).limit(limit).offset(offset)
    count_statement = select(func.count()).select_from(Invoice)
    if user_id is not None:
        statement = statement.where(Invoice.user_id == user_id)
        count_statement = count_statement.where(Invoice.user_id == user_id)
    if status_filter.strip():
        statement = statement.where(Invoice.status == status_filter.strip())
        count_statement = count_statement.where(Invoice.status == status_filter.strip())
    return InvoiceListResponse(
        items=list(db.scalars(statement).all()),
        total=db.scalar(count_statement) or 0,
    )


@router.post("/admin/invoices/{invoice_id}/mark-paid", response_model=PaymentPublic)
def admin_mark_invoice_paid(
    invoice_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> Payment:
    invoice = db.scalar(select(Invoice).where(Invoice.id == invoice_id))
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    payment = mark_invoice_paid(db, invoice, provider_payment_id=f"admin_{invoice.id}", raw_payload={"admin": True})
    user = db.scalar(select(User).where(User.id == invoice.user_id))
    log_event(
        db,
        event_type="invoice.paid_by_admin",
        actor_user=current_admin,
        target_user=user,
        entity_type="invoice",
        entity_id=invoice.id,
        message="Invoice marked as paid by admin",
        payload={"payment_id": str(payment.id)},
        request=request,
    )
    if user is not None:
        notify_user(
            db,
            user=user,
            type="payment.succeeded",
            title="Оплата подтверждена",
            body="Администратор подтвердил оплату, тариф активирован.",
            payload={"invoice_id": str(invoice.id), "payment_id": str(payment.id)},
        )
    db.commit()
    db.refresh(payment)
    return payment
