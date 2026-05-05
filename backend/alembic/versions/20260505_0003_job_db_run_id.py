"""link parser jobs to DB run ids

Revision ID: 20260505_0003
Revises: 20260505_0002
Create Date: 2026-05-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260505_0003"
down_revision = "20260505_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("parser_jobs", sa.Column("db_run_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_parser_jobs_db_run_id", "parser_jobs", ["db_run_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_parser_jobs_db_run_id", table_name="parser_jobs")
    op.drop_column("parser_jobs", "db_run_id")
