"""add default subscription plan flag

Revision ID: 20260623_0011
Revises: 20260621_0010
Create Date: 2026-06-23 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260623_0011"
down_revision = "20260621_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscription_plans",
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.execute(
        """
        UPDATE subscription_plans
        SET is_default = true,
            updated_at = now()
        WHERE code = 'free'
        """
    )
    op.execute(
        """
        UPDATE subscription_plans
        SET is_default = true,
            updated_at = now()
        WHERE id = (
            SELECT id
            FROM subscription_plans
            WHERE is_active = true
              AND is_public = true
            ORDER BY price_kzt ASC, name ASC
            LIMIT 1
        )
        AND NOT EXISTS (
            SELECT 1
            FROM subscription_plans
            WHERE is_default = true
        )
        """
    )
    op.create_index(
        "uq_subscription_plans_single_default",
        "subscription_plans",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default IS TRUE"),
    )
    op.alter_column("subscription_plans", "is_default", server_default=None)


def downgrade() -> None:
    op.drop_index("uq_subscription_plans_single_default", table_name="subscription_plans")
    op.drop_column("subscription_plans", "is_default")
