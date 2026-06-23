from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.billing import SubscriptionPlan, SubscriptionStatus, UsageEvent, UserSubscription
from app.models.parser_job import ParserJob
from app.models.user import User, UserRole


FREE_PLAN_CODE = "free"
JOB_EVENT_TYPE = "job_created"
RECORDS_EVENT_TYPE = "records_reserved"


@dataclass(frozen=True)
class QuotaDecision:
    plan: SubscriptionPlan
    subscription: UserSubscription
    requested_records: int
    jobs_used: int
    records_used: int
    jobs_remaining: int
    records_remaining: int


def current_month_start() -> datetime:
    now = datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def estimate_requested_records(source: str, parameters: dict[str, Any], explicit_total: int = 0) -> int:
    if explicit_total > 0:
        return explicit_total
    for key in ("limit", "listing_limit", "max_records", "parser.max-records"):
        value = parameters.get(key)
        if value in (None, ""):
            continue
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            continue
    # One record is reserved so very small jobs still count against a monthly quota.
    return 1


def get_or_create_free_plan(db: Session) -> SubscriptionPlan:
    settings = get_settings()
    plan = db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == FREE_PLAN_CODE))
    if plan is not None:
        changed = False
        if plan.name != "Бесплатный":
            plan.name = "Бесплатный"
            changed = True
        if plan.description != "Бесплатный тариф для первых 50 записей":
            plan.description = "Бесплатный тариф для первых 50 записей"
            changed = True
        if plan.max_jobs_per_month != settings.free_plan_jobs_per_month:
            plan.max_jobs_per_month = settings.free_plan_jobs_per_month
            changed = True
        if plan.max_records_per_month != settings.free_plan_records_per_month:
            plan.max_records_per_month = settings.free_plan_records_per_month
            changed = True
        if not plan.allowed_sources:
            plan.allowed_sources = settings.free_plan_sources
            changed = True
        default_count = db.scalar(select(func.count()).select_from(SubscriptionPlan).where(SubscriptionPlan.is_default.is_(True))) or 0
        if default_count == 0 and not plan.is_default:
            plan.is_default = True
            changed = True
        if changed:
            db.flush()
        return plan

    default_count = db.scalar(select(func.count()).select_from(SubscriptionPlan).where(SubscriptionPlan.is_default.is_(True))) or 0
    plan = SubscriptionPlan(
        code=FREE_PLAN_CODE,
        name="Бесплатный",
        description="Бесплатный тариф для первых 50 записей",
        price_kzt=0,
        max_jobs_per_month=settings.free_plan_jobs_per_month,
        max_records_per_month=settings.free_plan_records_per_month,
        allowed_sources=settings.free_plan_sources,
        is_active=True,
        is_public=True,
        is_default=default_count == 0,
    )
    db.add(plan)
    db.flush()
    return plan


def get_default_subscription_plan(db: Session) -> SubscriptionPlan:
    plan = db.scalar(
        select(SubscriptionPlan)
        .where(
            SubscriptionPlan.is_default.is_(True),
            SubscriptionPlan.is_active.is_(True),
            SubscriptionPlan.is_public.is_(True),
        )
        .order_by(SubscriptionPlan.updated_at.desc())
    )
    if plan is not None:
        return plan
    return get_or_create_free_plan(db)


def get_or_create_active_subscription(db: Session, user: User) -> UserSubscription:
    now = datetime.now(UTC)
    subscription = db.scalar(
        select(UserSubscription)
        .where(
            UserSubscription.user_id == user.id,
            UserSubscription.status.in_([SubscriptionStatus.ACTIVE.value, SubscriptionStatus.TRIALING.value]),
            UserSubscription.starts_at <= now,
            (UserSubscription.ends_at.is_(None) | (UserSubscription.ends_at > now)),
        )
        .order_by(UserSubscription.created_at.desc())
    )
    if subscription is not None:
        return subscription

    plan = get_default_subscription_plan(db)
    subscription = UserSubscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE.value,
    )
    db.add(subscription)
    db.flush()
    subscription.plan = plan
    return subscription


def get_monthly_usage(db: Session, user: User) -> tuple[int, int]:
    month_start = current_month_start()
    jobs_used = db.scalar(
        select(func.count())
        .select_from(UsageEvent)
        .where(
            UsageEvent.user_id == user.id,
            UsageEvent.event_type == JOB_EVENT_TYPE,
            UsageEvent.created_at >= month_start,
        )
    ) or 0
    records_used = db.scalar(
        select(func.coalesce(func.sum(UsageEvent.amount), 0))
        .where(
            UsageEvent.user_id == user.id,
            UsageEvent.event_type == RECORDS_EVENT_TYPE,
            UsageEvent.created_at >= month_start,
        )
    ) or 0
    return int(jobs_used), int(records_used)


def ensure_job_quota(db: Session, user: User, source: str, parameters: dict[str, Any], explicit_total: int = 0) -> QuotaDecision:
    subscription = get_or_create_active_subscription(db, user)
    plan = subscription.plan
    if not plan.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscription plan is inactive")

    allowed_sources = plan.allowed_sources or []
    if allowed_sources and source not in allowed_sources and user.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Source '{source}' is not available on current plan",
        )

    requested_records = estimate_requested_records(source, parameters, explicit_total)
    jobs_used, records_used = get_monthly_usage(db, user)

    if user.role != UserRole.ADMIN.value:
        if plan.max_records_per_month >= 0 and records_used + requested_records > plan.max_records_per_month:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Monthly record limit exceeded",
            )

    return QuotaDecision(
        plan=plan,
        subscription=subscription,
        requested_records=requested_records,
        jobs_used=jobs_used,
        records_used=records_used,
        jobs_remaining=-1,
        records_remaining=max(-1, plan.max_records_per_month - records_used),
    )


def record_job_usage(db: Session, user: User, job: ParserJob, requested_records: int) -> None:
    db.add(
        UsageEvent(
            user_id=user.id,
            job_id=job.id,
            event_type=JOB_EVENT_TYPE,
            source=job.source,
            amount=1,
            extra={"job_id": str(job.id)},
        )
    )
    db.add(
        UsageEvent(
            user_id=user.id,
            job_id=job.id,
            event_type=RECORDS_EVENT_TYPE,
            source=job.source,
            amount=requested_records,
            extra={"job_id": str(job.id), "reserved": True},
        )
    )
