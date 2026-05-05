from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.parser_job import ParserJob, ParserJobStatus
from app.models.user import User, UserRole
from app.schemas.job import ParserJobActionResponse, ParserJobCreate, ParserJobListResponse, ParserJobLiveResponse, ParserJobPublic
from app.services.audit import log_event, notify_user
from app.services.parsers_hub import ParsersHubError, get_parser_job, run_parser_job_action
from app.services.quota import ensure_job_quota, record_job_usage
from app.worker.tasks import run_parser_job


router = APIRouter()


def _get_owned_job(db: Session, job_id: UUID, current_user: User) -> ParserJob:
    job = db.scalar(select(ParserJob).where(ParserJob.id == job_id))
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if current_user.role != UserRole.ADMIN.value and job.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.post("", response_model=ParserJobPublic, status_code=status.HTTP_201_CREATED)
def create_job(
    payload: ParserJobCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ParserJob:
    quota = ensure_job_quota(db, current_user, payload.source, payload.parameters, payload.progress_total)
    job = ParserJob(
        user_id=current_user.id,
        source=payload.source,
        status=ParserJobStatus.PENDING.value,
        parameters=payload.parameters,
        progress_total=payload.progress_total or quota.requested_records,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        task = run_parser_job.delay(str(job.id))
    except Exception as exc:  # noqa: BLE001
        job.status = ParserJobStatus.FAILED.value
        job.error_message = f"Failed to enqueue parser job: {exc}"
        log_event(
            db,
            event_type="job.enqueue_failed",
            actor_user=current_user,
            target_user=current_user,
            entity_type="parser_job",
            entity_id=job.id,
            message=job.error_message,
            payload={"source": job.source},
            request=request,
        )
        notify_user(
            db,
            user=current_user,
            type="job.failed",
            title="Задача не запустилась",
            body=job.error_message,
            payload={"job_id": str(job.id), "source": job.source},
        )
        db.commit()
        db.refresh(job)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=job.error_message) from exc
    job.celery_task_id = task.id
    record_job_usage(db, current_user, job, quota.requested_records)
    log_event(
        db,
        event_type="job.created",
        actor_user=current_user,
        target_user=current_user,
        entity_type="parser_job",
        entity_id=job.id,
        message="Parser job queued",
        payload={"source": job.source, "requested_records": quota.requested_records},
        request=request,
    )
    notify_user(
        db,
        user=current_user,
        type="job.created",
        title="Задача поставлена в очередь",
        body=f"Парсер {job.source} скоро начнет работу.",
        payload={"job_id": str(job.id), "source": job.source},
    )
    db.commit()
    db.refresh(job)
    return job


@router.get("", response_model=ParserJobListResponse)
def list_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    all_users: bool = Query(default=False),
) -> ParserJobListResponse:
    statement = select(ParserJob).order_by(ParserJob.created_at.desc()).limit(limit).offset(offset)
    count_statement = select(func.count()).select_from(ParserJob)
    if current_user.role != UserRole.ADMIN.value or not all_users:
        statement = statement.where(ParserJob.user_id == current_user.id)
        count_statement = count_statement.where(ParserJob.user_id == current_user.id)

    items = list(db.scalars(statement).all())
    total = db.scalar(count_statement) or 0
    return ParserJobListResponse(items=items, total=total)


@router.get("/{job_id}/live", response_model=ParserJobLiveResponse)
def get_job_live(job_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> ParserJobLiveResponse:
    job = _get_owned_job(db, job_id, current_user)
    runner = None
    if job.runner_job_id:
        try:
            runner = get_parser_job(job.runner_job_id)
        except ParsersHubError as exc:
            runner = {"error": str(exc)}
    return ParserJobLiveResponse(job=ParserJobPublic.model_validate(job), runner=runner)


@router.post("/{job_id}/stop", response_model=ParserJobActionResponse)
def stop_job(
    job_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ParserJobActionResponse:
    job = _get_owned_job(db, job_id, current_user)
    if not job.runner_job_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Parser runner job is not started yet")

    try:
        runner = run_parser_job_action(job.runner_job_id, "stop")
    except ParsersHubError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    job.status = ParserJobStatus.CANCELLED.value
    log_event(
        db,
        event_type="job.stop_requested",
        actor_user=current_user,
        target_user=job.user,
        entity_type="parser_job",
        entity_id=job.id,
        message="Parser job stop requested",
        payload={"source": job.source, "runner_job_id": job.runner_job_id},
        request=request,
    )
    notify_user(
        db,
        user=job.user,
        type="job.stop_requested",
        title="Остановка задачи запрошена",
        body=f"Парсер {job.source} получил команду остановки.",
        payload={"job_id": str(job.id), "source": job.source},
    )
    db.commit()
    db.refresh(job)
    return ParserJobActionResponse(job=ParserJobPublic.model_validate(job), runner=runner)


@router.post("/{job_id}/retry", response_model=ParserJobPublic, status_code=status.HTTP_201_CREATED)
def retry_job(
    job_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ParserJob:
    original = _get_owned_job(db, job_id, current_user)
    quota = ensure_job_quota(db, current_user, original.source, original.parameters, original.progress_total)
    retry = ParserJob(
        user_id=current_user.id,
        source=original.source,
        status=ParserJobStatus.PENDING.value,
        parameters=original.parameters,
        progress_total=original.progress_total or quota.requested_records,
    )
    db.add(retry)
    db.commit()
    db.refresh(retry)
    try:
        task = run_parser_job.delay(str(retry.id))
    except Exception as exc:  # noqa: BLE001
        retry.status = ParserJobStatus.FAILED.value
        retry.error_message = f"Failed to enqueue parser job retry: {exc}"
        db.commit()
        db.refresh(retry)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=retry.error_message) from exc

    retry.celery_task_id = task.id
    record_job_usage(db, current_user, retry, quota.requested_records)
    log_event(
        db,
        event_type="job.retry_created",
        actor_user=current_user,
        target_user=current_user,
        entity_type="parser_job",
        entity_id=retry.id,
        message="Parser job retry queued",
        payload={"source": retry.source, "original_job_id": str(original.id), "requested_records": quota.requested_records},
        request=request,
    )
    notify_user(
        db,
        user=current_user,
        type="job.retry_created",
        title="Повторный запуск создан",
        body=f"Парсер {retry.source} поставлен в очередь повторно.",
        payload={"job_id": str(retry.id), "original_job_id": str(original.id), "source": retry.source},
    )
    db.commit()
    db.refresh(retry)
    return retry


@router.get("/{job_id}", response_model=ParserJobPublic)
def get_job(job_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> ParserJob:
    return _get_owned_job(db, job_id, current_user)
