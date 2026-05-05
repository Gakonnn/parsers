from __future__ import annotations

from celery import Celery

from app.core.config import get_settings


settings = get_settings()

celery_app = Celery(
    "parsers_platform",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_default_queue="parsers",
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    timezone="Asia/Almaty",
)
