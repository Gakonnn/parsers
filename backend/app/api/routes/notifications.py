from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.system import Notification
from app.models.user import User
from app.schemas.system import BulkUpdateResponse, NotificationListResponse, NotificationPublic


router = APIRouter()


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    unread_only: bool = Query(default=False),
    type: str = Query(default="", max_length=128),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> NotificationListResponse:
    statement = (
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    count_statement = select(func.count()).select_from(Notification).where(Notification.user_id == current_user.id)
    unread_statement = select(func.count()).select_from(Notification).where(
        Notification.user_id == current_user.id,
        Notification.is_read.is_(False),
    )
    if unread_only:
        statement = statement.where(Notification.is_read.is_(False))
        count_statement = count_statement.where(Notification.is_read.is_(False))
    if type.strip():
        statement = statement.where(Notification.type == type.strip())
        count_statement = count_statement.where(Notification.type == type.strip())

    return NotificationListResponse(
        items=list(db.scalars(statement).all()),
        total=db.scalar(count_statement) or 0,
        unread_total=db.scalar(unread_statement) or 0,
    )


@router.post("/read-all", response_model=BulkUpdateResponse)
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BulkUpdateResponse:
    result = db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.is_read.is_(False))
        .values(is_read=True, read_at=datetime.now(UTC))
    )
    db.commit()
    return BulkUpdateResponse(updated=result.rowcount or 0)


@router.post("/{notification_id}/read", response_model=NotificationPublic)
def mark_notification_read(
    notification_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Notification:
    notification = db.scalar(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == current_user.id)
    )
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.now(UTC)
        db.commit()
        db.refresh(notification)
    return notification
