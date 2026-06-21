"""add payment qr settings

Revision ID: 20260621_0010
Revises: 20260615_0009
Create Date: 2026-06-21 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260621_0010"
down_revision = "20260615_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_qr_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False, server_default="Kaspi QR"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("image_data", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payment_qr_settings_created_by_user_id"), "payment_qr_settings", ["created_by_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_payment_qr_settings_created_by_user_id"), table_name="payment_qr_settings")
    op.drop_table("payment_qr_settings")
