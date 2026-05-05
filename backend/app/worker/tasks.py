from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.parser_job import ParserJob, ParserJobStatus
from app.services.audit import log_event, notify_user
from app.services.parsers_hub import ParsersHubError, get_parser_job, start_parser_job
from app.worker.celery_app import celery_app


TERMINAL_HUB_STATUSES = {"completed", "failed", "stopped"}
DB_RUN_ID_RE = re.compile(r"\bdb_run_id=([0-9a-fA-F-]{36})\b")
DB_LIVE_RUN_ID_RE = re.compile(r"\[db\].*\brun_id=([0-9a-fA-F-]{36})\b")


def _now() -> datetime:
    return datetime.now(UTC)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _status_from_hub(status: str) -> str:
    if status == "completed":
        return ParserJobStatus.COMPLETED.value
    if status == "stopped":
        return ParserJobStatus.CANCELLED.value
    if status == "failed":
        return ParserJobStatus.FAILED.value
    return ParserJobStatus.RUNNING.value


def _log_tail(snapshot: dict[str, Any], limit: int = 1200) -> str:
    text = str(snapshot.get("log", "") or "")
    return text[-limit:]


def _extract_db_run_id(log_text: str) -> UUID | None:
    for pattern in (DB_RUN_ID_RE, DB_LIVE_RUN_ID_RE):
        match = pattern.search(log_text)
        if not match:
            continue
        try:
            return UUID(match.group(1))
        except ValueError:
            continue
    return None


def _sync_progress(job: ParserJob, hub_snapshot: dict[str, Any]) -> None:
    progress = hub_snapshot.get("progress")
    if not isinstance(progress, dict):
        progress = {}
    current = _as_int(progress.get("current"), job.progress_current)
    total = _as_int(progress.get("total"), job.progress_total)
    job.progress_current = max(job.progress_current, current)
    if total > 0:
        job.progress_total = total
    output_path = str(hub_snapshot.get("output_path") or "").strip()
    if output_path:
        job.result_path = output_path
    log_text = str(hub_snapshot.get("log", "") or "")
    db_run_id = _extract_db_run_id(log_text)
    if db_run_id:
        job.db_run_id = db_run_id


@celery_app.task(name="parser_jobs.run", bind=True)
def run_parser_job(self, job_id: str) -> dict[str, Any]:
    settings = get_settings()
    with SessionLocal() as db:
        try:
            parsed_job_id = UUID(job_id)
        except ValueError as exc:
            raise ValueError(f"Invalid job id: {job_id}") from exc

        job = db.scalar(select(ParserJob).where(ParserJob.id == parsed_job_id))
        if job is None:
            raise ValueError(f"Parser job not found: {job_id}")
        if job.status not in {ParserJobStatus.PENDING.value, ParserJobStatus.RUNNING.value}:
            return {"job_id": job_id, "status": job.status, "skipped": True}

        job.status = ParserJobStatus.RUNNING.value
        job.started_at = job.started_at or _now()
        job.error_message = None
        db.commit()

        try:
            hub_job = start_parser_job(job.source, job.parameters)
            runner_job_id = str(hub_job.get("job_id") or "").strip()
            if not runner_job_id:
                raise ParsersHubError("Parsers hub started job without job_id")

            job.runner_job_id = runner_job_id
            job.result_path = str(hub_job.get("output_path") or "") or job.result_path
            _sync_progress(job, hub_job)
            db.commit()

            while True:
                hub_snapshot = get_parser_job(runner_job_id)
                hub_status = str(hub_snapshot.get("status") or "").lower()
                _sync_progress(job, hub_snapshot)
                job.status = _status_from_hub(hub_status)

                if hub_status in TERMINAL_HUB_STATUSES:
                    job.finished_at = _now()
                    if hub_status in {"failed", "stopped"}:
                        job.error_message = _log_tail(hub_snapshot) or f"Parsers hub job {hub_status}"
                    user = job.user
                    if user is not None:
                        event_type = f"job.{job.status}"
                        log_event(
                            db,
                            event_type=event_type,
                            target_user=user,
                            entity_type="parser_job",
                            entity_id=job.id,
                            message=f"Parser job finished with status {job.status}",
                            payload={
                                "source": job.source,
                                "runner_job_id": runner_job_id,
                                "progress_current": job.progress_current,
                                "progress_total": job.progress_total,
                            },
                        )
                        if job.status == ParserJobStatus.COMPLETED.value:
                            notify_user(
                                db,
                                user=user,
                                type="job.completed",
                                title="Парсинг завершен",
                                body=f"Парсер {job.source} собрал {job.progress_current} записей.",
                                payload={"job_id": str(job.id), "source": job.source},
                            )
                        elif job.status == ParserJobStatus.CANCELLED.value:
                            notify_user(
                                db,
                                user=user,
                                type="job.cancelled",
                                title="Парсинг остановлен",
                                body=f"Задача {job.source} была остановлена.",
                                payload={"job_id": str(job.id), "source": job.source},
                            )
                        else:
                            notify_user(
                                db,
                                user=user,
                                type="job.failed",
                                title="Парсинг завершился с ошибкой",
                                body=job.error_message or f"Парсер {job.source} завершился с ошибкой.",
                                payload={"job_id": str(job.id), "source": job.source},
                            )
                    db.commit()
                    return {
                        "job_id": job_id,
                        "runner_job_id": runner_job_id,
                        "status": job.status,
                        "progress_current": job.progress_current,
                        "progress_total": job.progress_total,
                    }

                db.commit()
                time.sleep(max(0.5, settings.job_poll_interval_sec))
        except Exception as exc:  # noqa: BLE001
            job.status = ParserJobStatus.FAILED.value
            job.finished_at = _now()
            job.error_message = str(exc)
            user = job.user
            if user is not None:
                log_event(
                    db,
                    event_type="job.worker_failed",
                    target_user=user,
                    entity_type="parser_job",
                    entity_id=job.id,
                    message="Parser worker failed",
                    payload={"source": job.source, "error": str(exc)},
                )
                notify_user(
                    db,
                    user=user,
                    type="job.failed",
                    title="Парсинг завершился с ошибкой",
                    body=str(exc),
                    payload={"job_id": str(job.id), "source": job.source},
                )
            db.commit()
            raise
