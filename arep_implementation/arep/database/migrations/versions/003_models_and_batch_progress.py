"""Add models table, org scoping on runs/batch_jobs, async batch progress cols

Revision ID: 003
Revises: 002
Create Date: 2026-04-28
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # P1.2 — customer-submitted models
    op.create_table(
        "models",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("version", sa.String(32), nullable=False, server_default="v1.0"),
        sa.Column("submission_type", sa.String(16), nullable=False),
        sa.Column("artefact_uri", sa.String(512), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("size_bytes", sa.Integer, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="ready"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_models_org_name_version", "models", ["org_id", "name", "version"])

    # P1.1 — org scoping on existing tables
    op.add_column("runs", sa.Column("org_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=True, index=True))
    op.add_column("batch_jobs", sa.Column("org_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=True, index=True))

    # P1.3 — async batch progress
    op.add_column("batch_jobs", sa.Column("runs_completed", sa.Integer, nullable=False, server_default="0"))
    op.add_column("batch_jobs", sa.Column("runs_failed", sa.Integer, nullable=False, server_default="0"))
    op.add_column("batch_jobs", sa.Column("error_message", sa.Text, nullable=True))
    op.add_column("batch_jobs", sa.Column("scenario_path", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("batch_jobs", "scenario_path")
    op.drop_column("batch_jobs", "error_message")
    op.drop_column("batch_jobs", "runs_failed")
    op.drop_column("batch_jobs", "runs_completed")
    op.drop_column("batch_jobs", "org_id")
    op.drop_column("runs", "org_id")
    op.drop_index("ix_models_org_name_version", table_name="models")
    op.drop_table("models")
