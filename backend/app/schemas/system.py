from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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


class SupportMessageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    message: str = Field(min_length=1, max_length=5000)
    source: str = Field(default="footer", max_length=64)


class SupportMessageUpdate(BaseModel):
    status: str = Field(min_length=1, max_length=32)


class SupportMessagePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str
    phone: str | None = None
    message: str
    status: str
    source: str
    created_at: datetime
    updated_at: datetime


class SupportMessageListResponse(BaseModel):
    items: list[SupportMessagePublic]
    total: int
