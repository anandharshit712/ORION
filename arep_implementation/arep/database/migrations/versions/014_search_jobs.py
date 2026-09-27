"""Queued adversarial searches (Phase 2.3)

`POST /api/search` exists so adversarial search stops being CLI-only. A search
is `max_evals` simulations of one scenario, steered rather than sampled, which
is minutes of work — so it is queued like a comparison and polled.

`credits_charged` equals the evaluation budget. That is an honest price because
the search always spends its whole budget: it keeps going past the first
collision so it can report every distinct failure, which is what somebody
fixing a model needs. Recorded rather than recomputed, so a refund returns what
was actually paid even if the formula changes.

Revision ID: 014
Revises: 013
Create Date: 2026-09-27
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "search_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("scenario_id", sa.String(length=512), nullable=False),
        sa.Column("model_id", sa.String(length=256), nullable=False),
        sa.Column(
            "optimizer", sa.String(length=16), nullable=False, server_default="cma_es"
        ),
        sa.Column(
            "physics_mode",
            sa.String(length=16),
            nullable=False,
            server_default="kinematic",
        ),
        sa.Column("max_evals", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("seed", sa.Integer(), nullable=False, server_default="42"),
        sa.Column("n_dims", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("credits_charged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="queued"
        ),
        sa.Column("evals_done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("best_fitness", sa.Float(), nullable=True),
        # Nullable, not defaulted false: before the search finishes, "no
        # falsification found" and "not looked yet" are different answers, and
        # reporting the first while the second is true says a model is safe.
        sa.Column("falsification_found", sa.Boolean(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
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
    op.create_index("ix_search_jobs_org_id", "search_jobs", ["org_id"])
    op.create_index("ix_search_jobs_status", "search_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_search_jobs_status", table_name="search_jobs")
    op.drop_index("ix_search_jobs_org_id", table_name="search_jobs")
    op.drop_table("search_jobs")
