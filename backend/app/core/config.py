from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _getenv(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value not in (None, ""):
            return value
    return default


def _as_bool(value: str, *, default: bool = False) -> bool:
    if value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


@dataclass(frozen=True)
class Settings:
    app_name: str
    environment: str
    api_v1_prefix: str
    database_url: str
    secret_key: str
    access_token_expire_minutes: int
    cors_origins: list[str]
    auto_create_tables: bool
    celery_broker_url: str
    celery_result_backend: str
    parsers_hub_url: str
    parsers_hub_timeout_sec: float
    job_poll_interval_sec: float
    free_plan_jobs_per_month: int
    free_plan_records_per_month: int
    free_plan_sources: list[str]
    payment_webhook_secret: str
    payment_success_url: str
    payment_cancel_url: str
    payment_provider_name: str
    payment_checkout_mode: str
    payment_checkout_url_template: str


@lru_cache
def get_settings() -> Settings:
    database_url = _getenv(
        "BACKEND_DATABASE_URL",
        "DATABASE_URL",
        default="postgresql+psycopg2://parsers:parsers@localhost:5432/parsers",
    )
    cors_raw = _getenv("BACKEND_CORS_ORIGINS", default="http://localhost:3000,http://127.0.0.1:3000")
    return Settings(
        app_name=_getenv("BACKEND_APP_NAME", default="Parsers Platform API"),
        environment=_getenv("BACKEND_ENVIRONMENT", default="local"),
        api_v1_prefix=_getenv("BACKEND_API_V1_PREFIX", default="/api/v1"),
        database_url=_normalize_database_url(database_url),
        secret_key=_getenv("BACKEND_SECRET_KEY", "SECRET_KEY", default="change-me-in-production"),
        access_token_expire_minutes=int(_getenv("BACKEND_ACCESS_TOKEN_EXPIRE_MINUTES", default="1440")),
        cors_origins=_parse_csv(cors_raw),
        auto_create_tables=_as_bool(_getenv("BACKEND_AUTO_CREATE_TABLES", default="false")),
        celery_broker_url=_getenv(
            "BACKEND_CELERY_BROKER_URL",
            "CELERY_BROKER_URL",
            default="redis://localhost:6379/0",
        ),
        celery_result_backend=_getenv(
            "BACKEND_CELERY_RESULT_BACKEND",
            "CELERY_RESULT_BACKEND",
            default="redis://localhost:6379/1",
        ),
        parsers_hub_url=_getenv("PARSERS_HUB_INTERNAL_URL", default="http://localhost:8090").rstrip("/"),
        parsers_hub_timeout_sec=float(_getenv("PARSERS_HUB_TIMEOUT_SEC", default="30")),
        job_poll_interval_sec=float(_getenv("BACKEND_JOB_POLL_INTERVAL_SEC", default="2")),
        free_plan_jobs_per_month=int(_getenv("BACKEND_FREE_PLAN_JOBS_PER_MONTH", default="10")),
        free_plan_records_per_month=int(_getenv("BACKEND_FREE_PLAN_RECORDS_PER_MONTH", default="500")),
        free_plan_sources=_parse_csv(_getenv("BACKEND_FREE_PLAN_SOURCES", default="olx,krisha,2gis,kolesa")),
        payment_webhook_secret=_getenv("PAYMENT_WEBHOOK_SECRET", default="change-payment-webhook-secret"),
        payment_success_url=_getenv("PAYMENT_SUCCESS_URL", default=""),
        payment_cancel_url=_getenv("PAYMENT_CANCEL_URL", default=""),
        payment_provider_name=_getenv("PAYMENT_PROVIDER_NAME", default="manual"),
        payment_checkout_mode=_getenv("PAYMENT_CHECKOUT_MODE", default="mock"),
        payment_checkout_url_template=_getenv("PAYMENT_CHECKOUT_URL_TEMPLATE", default=""),
    )
