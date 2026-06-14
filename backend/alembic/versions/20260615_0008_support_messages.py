"""support messages

Revision ID: 20260615_0008
Revises: 20260614_0007
Create Date: 2026-06-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260615_0008"
down_revision = "20260614_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_support_messages_created_at", "support_messages", ["created_at"], unique=False)
    op.create_index("ix_support_messages_email", "support_messages", ["email"], unique=False)
    op.create_index("ix_support_messages_status", "support_messages", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_support_messages_status", table_name="support_messages")
    op.drop_index("ix_support_messages_email", table_name="support_messages")
    op.drop_index("ix_support_messages_created_at", table_name="support_messages")
    op.drop_table("support_messages")
