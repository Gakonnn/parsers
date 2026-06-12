"""production plan names

Revision ID: 20260612_0006
Revises: 20260505_0005
Create Date: 2026-06-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260612_0006"
down_revision = "20260505_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE subscription_plans
            SET name = :name,
                description = :description
            WHERE code = :code
            """
        ).bindparams(
            code="free",
            name="Базовый",
            description="Базовый тариф для новых пользователей",
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE subscription_plans
            SET name = :name,
                description = :description
            WHERE code = :code
            """
        ).bindparams(
            code="free",
            name="Базовый",
            description="Базовый тариф для новых пользователей",
        )
    )
