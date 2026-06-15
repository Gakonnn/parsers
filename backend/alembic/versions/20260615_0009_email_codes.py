"""email codes

Revision ID: 20260615_0009
Revises: 20260615_0008
Create Date: 2026-06-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260615_0009"
down_revision = "20260615_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE users SET is_verified = true WHERE is_verified = false")
    op.create_table(
        "email_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("code_hash", sa.String(length=255), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_codes_user_id", "email_codes", ["user_id"], unique=False)
    op.create_index("ix_email_codes_email", "email_codes", ["email"], unique=False)
    op.create_index("ix_email_codes_purpose", "email_codes", ["purpose"], unique=False)
    op.create_index(
        "ix_email_codes_lookup",
        "email_codes",
        ["email", "purpose", "consumed_at", "expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_email_codes_lookup", table_name="email_codes")
    op.drop_index("ix_email_codes_purpose", table_name="email_codes")
    op.drop_index("ix_email_codes_email", table_name="email_codes")
    op.drop_index("ix_email_codes_user_id", table_name="email_codes")
    op.drop_table("email_codes")
