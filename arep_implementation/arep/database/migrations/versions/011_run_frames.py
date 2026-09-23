"""Stored tick frames for scrubbable playback (Phase 2.5)

Adds ``run_frames``: gzipped JSON tick frames keyed by run.

Deliberately not written for every run. At 50 Hz a 30-second run is 1,500
frames, so a 500-run batch would be three quarters of a million of them. Frames
are kept only for runs worth scrubbing instantly -- the ones that collided, plus
anything a customer pins -- which at a 2% collision rate is ten runs a batch.

Everything else replays from its seed and stores nothing, because determinism
means the run can always be rebuilt. Stored frames buy exactly one thing: not
paying the CPU again while someone drags a scrub bar.

Revision ID: 011
Revises: 010
Create Date: 2026-09-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "run_frames",
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("frame_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("frames_gzip", sa.LargeBinary(), nullable=False),
        sa.Column(
            "reason", sa.String(length=32), nullable=False, server_default="collision"
        ),
        sa.Column(
            "stored_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        # CASCADE: frames are meaningless without the run they belong to, and
        # orphaned blobs are the expensive kind of leak.
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id"),
    )


def downgrade() -> None:
    op.drop_table("run_frames")
