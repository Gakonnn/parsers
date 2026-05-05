from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from starlette.responses import Response

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.result import ExportFormat, ParserResultListResponse, ResultFieldsResponse
from app.services.results import export_results_response, list_result_fields, list_results


router = APIRouter()


@router.get("", response_model=ParserResultListResponse)
def read_results(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    source: str = Query(default="", max_length=32),
    job_id: UUID | None = Query(default=None),
    q: str = Query(default="", max_length=255),
    has_phone: str = Query(default="", pattern="^(|yes|no)$"),
    created_from: str = Query(default=""),
    created_to: str = Query(default=""),
    all_users: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ParserResultListResponse:
    items, total = list_results(
        db,
        current_user=current_user,
        source=source,
        job_id=job_id,
        q=q,
        has_phone=has_phone,
        created_from=created_from,
        created_to=created_to,
        all_users=all_users,
        limit=limit,
        offset=offset,
    )
    return ParserResultListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/fields", response_model=ResultFieldsResponse)
def read_result_fields(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    source: str = Query(default="", max_length=32),
    job_id: UUID | None = Query(default=None),
    all_users: bool = Query(default=False),
) -> ResultFieldsResponse:
    return ResultFieldsResponse(fields=list_result_fields(db, current_user=current_user, source=source, job_id=job_id, all_users=all_users))


@router.get("/export")
def export_results(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    format: ExportFormat = Query(default="csv"),  # noqa: A002 - API query parameter name.
    fields: str = Query(default=""),
    source: str = Query(default="", max_length=32),
    job_id: UUID | None = Query(default=None),
    q: str = Query(default="", max_length=255),
    has_phone: str = Query(default="", pattern="^(|yes|no)$"),
    created_from: str = Query(default=""),
    created_to: str = Query(default=""),
    all_users: bool = Query(default=False),
) -> Response:
    return export_results_response(
        db,
        current_user=current_user,
        export_format=format,
        fields=fields,
        source=source,
        job_id=job_id,
        q=q,
        has_phone=has_phone,
        created_from=created_from,
        created_to=created_to,
        all_users=all_users,
    )
