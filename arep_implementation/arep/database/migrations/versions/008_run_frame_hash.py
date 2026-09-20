"""Per-run frame hash (Phase 0.5, defect D-06)

Adds ``runs.frame_hash``: a rolling SHA256 over the run's canonical tick frames.

Two runs of the same (model, scenario, seed) must produce the same digest. That
turns the determinism claim from a promise into something a test asserts and a
customer can verify against their own re-run — which matters because the score
is the product.

Nullable: runs recorded before this migration have no digest, and a batch run
executed without frame emission does not produce one.

Revision ID: 008
Revises: 007
Create Date: 2026-09-20
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("frame_hash", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "frame_hash")
