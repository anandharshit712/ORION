"""Per-run failure ledger (Phase 2, closing the D-08 residual)

Adds ``run_failures``, keyed on (batch_id, master_seed).

A run that succeeds writes a RunRecord, and the worker checks for that row
before executing — so a Celery redelivery cannot double-count a success. A run
that fails writes nothing, so there was nothing to check, and a redelivery of a
failing task bumped ``runs_failed`` a second time **and refunded a second
credit**. The second one matters more than the failure count: it is a wrong
charge, in the customer's favour, on every redelivered failure.

Redelivery is not exotic. acks_late means it happens whenever a worker dies
mid-task.

Revision ID: 010
Revises: 009
Create Date: 2026-09-21
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "run_failures",
        # Composite key: a batch fans out one task per seed, so the pair is
        # what identifies a run. The database enforces the "once" — not an
        # application check that races with itself across workers.
        sa.Column("batch_id", sa.Integer, primary_key=True),
        sa.Column("master_seed", sa.Integer, primary_key=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "recorded_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("run_failures")
