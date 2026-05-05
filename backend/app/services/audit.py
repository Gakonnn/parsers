from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.system import AuditLog, Notification
from app.models.user import User


def _string_id(value: UUID | str | None) -> str | None:
    if value is None:
        return None
    return str(value)


def request_meta(request: Request | None) -> dict[str, str | None]:
    if request is None:
        return {"ip_address": None, "user_agent": None}
    forwarded_for = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return {
        "ip_address": forwarded_for or (request.client.host if request.client else None),
        "user_agent": request.headers.get("user-agent"),
    }


def log_event(
    db: Session,
    *,
    event_type: str,
    actor_user: User | None = None,
    target_user: User | None = None,
    entity_type: str | None = None,
    entity_id: UUID | str | None = None,
    message: str | None = None,
    payload: dict[str, Any] | None = None,
    request: Request | None = None,
) -> AuditLog:
    meta = request_meta(request)
    item = AuditLog(
        actor_user_id=actor_user.id if actor_user else None,
        target_user_id=target_user.id if target_user else None,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=_string_id(entity_id),
        ip_address=meta["ip_address"],
        user_agent=meta["user_agent"],
        message=message,
        payload=payload or {},
    )
    db.add(item)
    return item


def notify_user(
    db: Session,
    *,
    user: User,
    type: str,
    title: str,
    body: str | None = None,
    payload: dict[str, Any] | None = None,
    channel: str = "in_app",
) -> Notification:
    item = Notification(
        user_id=user.id,
        channel=channel,
        type=type,
        title=title,
        body=body,
        payload=payload or {},
    )
    db.add(item)
    return item
