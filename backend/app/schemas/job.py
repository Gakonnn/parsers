from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


ParserSource = Literal["olx", "krisha", "2gis", "kolesa"]


class ParserJobCreate(BaseModel):
    source: ParserSource
    parameters: dict[str, Any] = Field(default_factory=dict)
    progress_total: int = Field(default=0, ge=0)


class ParserJobPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    source: str
    status: str
    parameters: dict[str, Any]
    progress_current: int
    progress_total: int
    celery_task_id: str | None = None
    runner_job_id: str | None = None
    db_run_id: UUID | None = None
    result_path: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ParserJobListResponse(BaseModel):
    items: list[ParserJobPublic]
    total: int


class ParserJobLiveResponse(BaseModel):
    job: ParserJobPublic
    runner: dict[str, Any] | None = None


class ParserJobActionResponse(BaseModel):
    job: ParserJobPublic
    runner: dict[str, Any] | None = None
