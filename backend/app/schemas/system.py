from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_user_id: UUID | None = None
    target_user_id: UUID | None = None
    event_type: str
    entity_type: str | None = None
    entity_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    message: str | None = None
    payload: dict
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogPublic]
    total: int


class NotificationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    channel: str
    type: str
    title: str
    body: str | None = None
    payload: dict
    is_read: bool
    created_at: datetime
    read_at: datetime | None = None


class NotificationListResponse(BaseModel):
    items: list[NotificationPublic]
    total: int
    unread_total: int


class BulkUpdateResponse(BaseModel):
    updated: int
