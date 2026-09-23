"""Queued model comparisons (Phase 2.4)

Adds ``comparison_jobs``.

RegressionDetector has worked since Phase 2 but was reachable only from the CLI,
so the dashboard's Compare section had nothing to call. A comparison runs
2 x runs_per_scenario x len(scenario_ids) simulations - minutes of work - so it
is queued like a batch rather than run inside the request.

``credits_charged`` is stored rather than recomputed at refund time: the pricing
formula can change, and a customer must be refunded what they were charged.

Revision ID: 012
Revises: 011
Create Date: 2026-09-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "comparison_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("model_a_id", sa.String(length=256), nullable=False),
        sa.Column("model_b_id", sa.String(length=256), nullable=False),
        sa.Column("scenario_ids", sa.Text(), nullable=False),
        sa.Column(
            "runs_per_scenario", sa.Integer(), nullable=False, server_default="10"
        ),
        sa.Column("seed", sa.Integer(), nullable=False, server_default="42"),
        sa.Column("credits_charged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="queued"
        ),
        sa.Column("overall_winner", sa.String(length=8), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("has_regression", sa.Boolean(), nullable=True),
        sa.Column("report_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_comparison_jobs_org_id", "comparison_jobs", ["org_id"])
    op.create_index("ix_comparison_jobs_status", "comparison_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_comparison_jobs_status", table_name="comparison_jobs")
    op.drop_index("ix_comparison_jobs_org_id", table_name="comparison_jobs")
    op.drop_table("comparison_jobs")
