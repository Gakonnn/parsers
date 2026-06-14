"""record based tariffs

Revision ID: 20260614_0007
Revises: 20260612_0006
Create Date: 2026-06-14
"""

from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op


revision = "20260614_0007"
down_revision = "20260612_0006"
branch_labels = None
depends_on = None


SOURCES = ["olx", "krisha", "2gis", "kolesa"]

PLANS = [
    ("free", "Бесплатный", "Бесплатный тариф для первых 50 записей", 0, 50),
    ("start", "Старт", "Стартовый тариф для первых регулярных выгрузок", 4_000, 500),
    ("standard", "Стандарт", "Оптимальный тариф для стабильного потока лидов", 10_000, 2_000),
    ("business", "Бизнес", "Расширенный тариф для активного парсинга и выгрузок", 25_000, 10_000),
    ("pro", "Профи", "Профессиональный тариф для больших объемов данных", 50_000, 35_000),
    ("corporate", "Корпоративный", "Корпоративный тариф для отделов продаж и аналитики", 100_000, 100_000),
    ("enterprise", "Enterprise", "Enterprise-тариф для масштабной автоматизации", 300_000, 500_000),
    ("enterprise_plus", "Enterprise Plus", "Максимальный тариф для крупных команд и потоков данных", 500_000, 1_200_000),
]


def upgrade() -> None:
    allowed_sources = json.dumps(SOURCES)
    for code, name, description, price_kzt, max_records in PLANS:
        op.execute(
            sa.text(
                """
                INSERT INTO subscription_plans (
                    id,
                    code,
                    name,
                    description,
                    price_kzt,
                    currency,
                    billing_period,
                    max_jobs_per_month,
                    max_records_per_month,
                    allowed_sources,
                    is_active,
                    is_public
                )
                VALUES (
                    :id,
                    :code,
                    :name,
                    :description,
                    :price_kzt,
                    'KZT',
                    'monthly',
                    -1,
                    :max_records_per_month,
                    CAST(:allowed_sources AS jsonb),
                    true,
                    true
                )
                ON CONFLICT (code) DO UPDATE
                SET name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    price_kzt = EXCLUDED.price_kzt,
                    currency = EXCLUDED.currency,
                    billing_period = EXCLUDED.billing_period,
                    max_jobs_per_month = EXCLUDED.max_jobs_per_month,
                    max_records_per_month = EXCLUDED.max_records_per_month,
                    allowed_sources = EXCLUDED.allowed_sources,
                    is_active = true,
                    is_public = true,
                    updated_at = now()
                """
            ).bindparams(
                id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"dataleadhub-plan-{code}")),
                code=code,
                name=name,
                description=description,
                price_kzt=price_kzt,
                max_records_per_month=max_records,
                allowed_sources=allowed_sources,
            )
        )

    valid_codes = ", ".join(f"'{code}'" for code, *_ in PLANS)
    op.execute(
        sa.text(
            f"""
            UPDATE subscription_plans
            SET is_public = false,
                updated_at = now()
            WHERE code NOT IN ({valid_codes})
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE subscription_plans
            SET is_public = true,
                updated_at = now()
            """
        )
    )
