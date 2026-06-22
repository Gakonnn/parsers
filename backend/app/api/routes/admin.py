from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.parser_job import ParserJob
from app.models.system import AuditLog, SupportMessage
from app.models.user import User, UserRole
from app.schemas.billing import UsageSummary, UserSubscriptionPublic
from app.schemas.job import ParserJobListResponse
from app.schemas.system import AuditLogListResponse, SupportMessageListResponse, SupportMessagePublic, SupportMessageUpdate
from app.schemas.user import UserAdminUpdate, UserListResponse, UserPublic
from app.services.audit import log_event, notify_user
from app.services.quota import current_month_start, get_monthly_usage, get_or_create_active_subscription


router = APIRouter()

SUPPORT_STATUSES = {"new", "in_progress", "closed"}


@router.get("/users", response_model=UserListResponse)
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
    q: str = Query(default="", max_length=255),
    role: str = Query(default="", max_length=32),
    is_active: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> UserListResponse:
    statement = select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
    count_statement = select(func.count()).select_from(User)

    conditions = []
    search = q.strip()
    if search:
        pattern = f"%{search}%"
        conditions.append(or_(User.email.ilike(pattern), User.full_name.ilike(pattern)))
    if role.strip():
        conditions.append(User.role == role.strip())
    if is_active is not None:
        conditions.append(User.is_active.is_(is_active))
    for condition in conditions:
        statement = statement.where(condition)
        count_statement = count_statement.where(condition)

    return UserListResponse(
        items=list(db.scalars(statement).all()),
        total=db.scalar(count_statement) or 0,
    )


@router.get("/users/{user_id}", response_model=UserPublic)
def get_user(user_id: UUID, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> User:
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/users/{user_id}", response_model=UserPublic)
def update_user(
    user_id: UUID,
    payload: UserAdminUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> User:
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    updates = payload.model_dump(exclude_unset=True)
    if "role" in updates and updates["role"] is not None:
        allowed_roles = {role.value for role in UserRole}
        if updates["role"] not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")
    if user.id == current_admin.id and updates.get("is_active") is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admin cannot disable own account")
    if user.id == current_admin.id and updates.get("role") and updates["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admin cannot remove own admin role")

    for key, value in updates.items():
        setattr(user, key, value)
    if updates:
        log_event(
            db,
            event_type="user.updated",
            actor_user=current_admin,
            target_user=user,
            entity_type="user",
            entity_id=user.id,
            message="User account updated by admin",
            payload={"updated_fields": sorted(updates.keys())},
        )
        if "is_active" in updates:
            title = "Аккаунт включен" if user.is_active else "Аккаунт отключен"
            notify_user(
                db,
                user=user,
                type="user.status_changed",
                title=title,
                body="Администратор изменил статус вашего аккаунта.",
                payload={"is_active": user.is_active},
            )
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}")
def delete_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> None:
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admin cannot delete own account")
    log_event(
        db,
        event_type="user.deleted",
        actor_user=current_admin,
        target_user=user,
        entity_type="user",
        entity_id=user.id,
        message="User account deleted by admin",
        payload={"email": user.email},
    )
    db.delete(user)
    db.commit()


@router.get("/users/{user_id}/jobs", response_model=ParserJobListResponse)
def list_user_jobs(
    user_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ParserJobListResponse:
    user_exists = db.scalar(select(User.id).where(User.id == user_id))
    if user_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    statement = (
        select(ParserJob)
        .where(ParserJob.user_id == user_id)
        .order_by(ParserJob.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    count_statement = select(func.count()).select_from(ParserJob).where(ParserJob.user_id == user_id)
    return ParserJobListResponse(
        items=list(db.scalars(statement).all()),
        total=db.scalar(count_statement) or 0,
    )


@router.get("/users/{user_id}/usage", response_model=UsageSummary)
def get_user_usage(user_id: UUID, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> UsageSummary:
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    subscription = get_or_create_active_subscription(db, user)
    jobs_used, records_used = get_monthly_usage(db, user)
    plan = subscription.plan
    db.commit()
    return UsageSummary(
        subscription=UserSubscriptionPublic.model_validate(subscription),
        jobs_used=jobs_used,
        records_used=records_used,
        jobs_remaining=-1,
        records_remaining=max(-1, plan.max_records_per_month - records_used),
        month_started_at=current_month_start(),
    )


@router.get("/audit-logs", response_model=AuditLogListResponse)
def list_audit_logs(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
    q: str = Query(default="", max_length=255),
    event_type: str = Query(default="", max_length=128),
    entity_type: str = Query(default="", max_length=64),
    actor_user_id: UUID | None = Query(default=None),
    target_user_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AuditLogListResponse:
    statement = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    count_statement = select(func.count()).select_from(AuditLog)

    conditions = []
    search = q.strip()
    if search:
        pattern = f"%{search}%"
        conditions.append(
            or_(
                AuditLog.event_type.ilike(pattern),
                AuditLog.entity_type.ilike(pattern),
                AuditLog.entity_id.ilike(pattern),
                AuditLog.message.ilike(pattern),
            )
        )
    if event_type.strip():
        conditions.append(AuditLog.event_type == event_type.strip())
    if entity_type.strip():
        conditions.append(AuditLog.entity_type == entity_type.strip())
    if actor_user_id is not None:
        conditions.append(AuditLog.actor_user_id == actor_user_id)
    if target_user_id is not None:
        conditions.append(AuditLog.target_user_id == target_user_id)

    for condition in conditions:
        statement = statement.where(condition)
        count_statement = count_statement.where(condition)

    return AuditLogListResponse(
        items=list(db.scalars(statement).all()),
        total=db.scalar(count_statement) or 0,
    )


@router.get("/support-messages", response_model=SupportMessageListResponse)
def list_support_messages(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
    q: str = Query(default="", max_length=255),
    status_filter: str = Query(default="", alias="status", max_length=32),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> SupportMessageListResponse:
    statement = select(SupportMessage).order_by(SupportMessage.created_at.desc()).limit(limit).offset(offset)
    count_statement = select(func.count()).select_from(SupportMessage)

    conditions = []
    search = q.strip()
    if search:
        pattern = f"%{search}%"
        conditions.append(
            or_(
                SupportMessage.name.ilike(pattern),
                SupportMessage.email.ilike(pattern),
                SupportMessage.phone.ilike(pattern),
                SupportMessage.message.ilike(pattern),
            )
        )
    if status_filter.strip():
        conditions.append(SupportMessage.status == status_filter.strip())

    for condition in conditions:
        statement = statement.where(condition)
        count_statement = count_statement.where(condition)

    return SupportMessageListResponse(
        items=list(db.scalars(statement).all()),
        total=db.scalar(count_statement) or 0,
    )


@router.patch("/support-messages/{message_id}", response_model=SupportMessagePublic)
def update_support_message(
    message_id: UUID,
    payload: SupportMessageUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> SupportMessage:
    item = db.scalar(select(SupportMessage).where(SupportMessage.id == message_id))
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Support message not found")
    next_status = payload.status.strip()
    if next_status not in SUPPORT_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid support message status")

    previous_status = item.status
    item.status = next_status
    log_event(
        db,
        event_type="support.message_updated",
        actor_user=current_admin,
        entity_type="support_message",
        entity_id=item.id,
        message="Support message status updated by admin",
        payload={"from": previous_status, "to": next_status},
    )
    db.commit()
    db.refresh(item)
    return item


@router.delete("/support-messages/{message_id}")
def delete_support_message(
    message_id: UUID,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> None:
    item = db.scalar(select(SupportMessage).where(SupportMessage.id == message_id))
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Support message not found")
    log_event(
        db,
        event_type="support.message_deleted",
        actor_user=current_admin,
        entity_type="support_message",
        entity_id=item.id,
        message="Support message deleted by admin",
        payload={"email": item.email, "source": item.source},
    )
    db.delete(item)
    db.commit()
