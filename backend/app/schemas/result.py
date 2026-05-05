from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


ExportFormat = Literal["csv", "json", "xlsx"]


class ParserResultPublic(BaseModel):
    id: int
    job_id: UUID
    run_id: UUID
    source: str
    external_id: str
    payload: dict[str, Any]
    created_at: datetime
    run_status: str | None = None


class ParserResultListResponse(BaseModel):
    items: list[ParserResultPublic]
    total: int
    limit: int
    offset: int


class ResultFieldsResponse(BaseModel):
    fields: list[str]
