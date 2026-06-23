"""normalize default plan visibility

Revision ID: 20260623_0012
Revises: 20260623_0011
Create Date: 2026-06-23 00:30:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260623_0012"
down_revision = "20260623_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE subscription_plans
        SET is_active = true,
            is_public = true,
            updated_at = now()
        WHERE is_default = true
        """
    )
    op.execute(
        """
        UPDATE subscription_plans
        SET is_default = true,
            is_active = true,
            is_public = true,
            updated_at = now()
        WHERE code = 'free'
          AND NOT EXISTS (
              SELECT 1
              FROM subscription_plans
              WHERE is_default = true
          )
        """
    )
    op.execute(
        """
        UPDATE subscription_plans
        SET is_default = true,
            is_active = true,
            is_public = true,
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


def downgrade() -> None:
    pass
