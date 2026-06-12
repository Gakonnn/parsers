"""billing plans and usage limits

Revision ID: 20260505_0002
Revises: 20260505_0001
Create Date: 2026-05-05
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260505_0002"
down_revision = "20260505_0001"
branch_labels = None
depends_on = None

FREE_PLAN_ID = str(uuid.uuid5(uuid.NAMESPACE_DNS, "parsers-platform-free-plan"))


def upgrade() -> None:
    op.create_table(
        "subscription_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price_kzt", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("billing_period", sa.String(length=32), nullable=False),
        sa.Column("max_jobs_per_month", sa.Integer(), nullable=False),
        sa.Column("max_records_per_month", sa.Integer(), nullable=False),
        sa.Column("allowed_sources", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_subscription_plans_code", "subscription_plans", ["code"], unique=True)

    op.create_table(
        "user_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["subscription_plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_subscriptions_status", "user_subscriptions", ["status"], unique=False)
    op.create_index("ix_user_subscriptions_user_id", "user_subscriptions", ["user_id"], unique=False)

    op.create_table(
        "usage_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["parser_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usage_events_created_at", "usage_events", ["created_at"], unique=False)
    op.create_index("ix_usage_events_event_type", "usage_events", ["event_type"], unique=False)
    op.create_index("ix_usage_events_job_id", "usage_events", ["job_id"], unique=False)
    op.create_index("ix_usage_events_source", "usage_events", ["source"], unique=False)
    op.create_index("ix_usage_events_user_id", "usage_events", ["user_id"], unique=False)

    plans_table = sa.table(
        "subscription_plans",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("price_kzt", sa.Integer),
        sa.column("currency", sa.String),
        sa.column("billing_period", sa.String),
        sa.column("max_jobs_per_month", sa.Integer),
        sa.column("max_records_per_month", sa.Integer),
        sa.column("allowed_sources", postgresql.JSONB),
        sa.column("is_active", sa.Boolean),
        sa.column("is_public", sa.Boolean),
    )
    op.bulk_insert(
        plans_table,
        [
            {
                "id": uuid.UUID(FREE_PLAN_ID),
                "code": "free",
                "name": "Базовый",
                "description": "Базовый тариф для новых пользователей",
                "price_kzt": 0,
                "currency": "KZT",
                "billing_period": "monthly",
                "max_jobs_per_month": 10,
                "max_records_per_month": 500,
                "allowed_sources": ["olx", "krisha", "2gis", "kolesa"],
                "is_active": True,
                "is_public": True,
            }
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_usage_events_user_id", table_name="usage_events")
    op.drop_index("ix_usage_events_source", table_name="usage_events")
    op.drop_index("ix_usage_events_job_id", table_name="usage_events")
    op.drop_index("ix_usage_events_event_type", table_name="usage_events")
    op.drop_index("ix_usage_events_created_at", table_name="usage_events")
    op.drop_table("usage_events")
    op.drop_index("ix_user_subscriptions_user_id", table_name="user_subscriptions")
    op.drop_index("ix_user_subscriptions_status", table_name="user_subscriptions")
    op.drop_table("user_subscriptions")
    op.drop_index("ix_subscription_plans_code", table_name="subscription_plans")
    op.drop_table("subscription_plans")
