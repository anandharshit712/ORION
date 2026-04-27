"""Initial schema — existing tables

Revision ID: 001
Revises: None
Create Date: 2026-04-26
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the initial schema (scenarios, batch_jobs, runs, users)."""
    op.create_table(
        "scenarios",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(256), nullable=False, index=True),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("yaml_content", sa.Text, nullable=False),
        sa.Column("duration", sa.Float, nullable=False),
        sa.Column("road_type", sa.String(32), nullable=True),
        sa.Column("num_traffic_objects", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(256), nullable=False, unique=True, index=True),
        sa.Column("username", sa.String(128), nullable=False, unique=True, index=True),
        sa.Column("hashed_password", sa.String(512), nullable=False),
        sa.Column("full_name", sa.String(256), nullable=True),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("last_login", sa.DateTime, nullable=True),
    )
    op.create_table(
        "batch_jobs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("scenario_name", sa.String(256), nullable=False),
        sa.Column("model_name", sa.String(256), nullable=False),
        sa.Column("num_runs", sa.Integer, nullable=False),
        sa.Column("master_seed", sa.Integer, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, default="pending"),
        sa.Column("composite_mean", sa.Float, nullable=True),
        sa.Column("composite_std", sa.Float, nullable=True),
        sa.Column("safety_mean", sa.Float, nullable=True),
        sa.Column("compliance_mean", sa.Float, nullable=True),
        sa.Column("stability_mean", sa.Float, nullable=True),
        sa.Column("reactivity_mean", sa.Float, nullable=True),
        sa.Column("collision_rate", sa.Float, nullable=True),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("scenario_id", sa.Integer, sa.ForeignKey("scenarios.id"), nullable=False),
        sa.Column("batch_job_id", sa.Integer, sa.ForeignKey("batch_jobs.id"), nullable=True),
        sa.Column("model_name", sa.String(256), nullable=False, index=True),
        sa.Column("master_seed", sa.Integer, nullable=False),
        sa.Column("duration", sa.Float, nullable=False),
        sa.Column("termination_reason", sa.String(32), nullable=True),
        sa.Column("num_timesteps", sa.Integer, default=0),
        sa.Column("composite_score", sa.Float, nullable=False),
        sa.Column("safety_score", sa.Float, nullable=False),
        sa.Column("collision_occurred", sa.Boolean, default=False),
        sa.Column("min_ttc", sa.Float, default=30.0),
        sa.Column("compliance_score", sa.Float, nullable=False),
        sa.Column("speed_compliance", sa.Float, default=1.0),
        sa.Column("stability_score", sa.Float, nullable=False),
        sa.Column("mean_jerk", sa.Float, default=0.0),
        sa.Column("reactivity_score", sa.Float, nullable=False),
        sa.Column("brake_response_time", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_runs_model_scenario", "runs", ["model_name", "scenario_id"])
    op.create_index("ix_runs_composite", "runs", ["composite_score"])


def downgrade() -> None:
    op.drop_table("runs")
    op.drop_table("batch_jobs")
    op.drop_table("users")
    op.drop_table("scenarios")
