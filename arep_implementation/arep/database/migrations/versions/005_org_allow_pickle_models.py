"""Gate the cloudpickle model path per organisation (Phase 0.2, defect D-01)

Adds ``organisations.allow_pickle_models``, default FALSE.

A cloudpickle artefact executes arbitrary Python on upload-and-run, so the SDK
path is opt-in per org and enabled by hand for trusted design partners. The
Docker path stays available to everyone. Existing orgs are deliberately NOT
grandfathered in — after this migration nobody can use the pickle path until a
superadmin turns it on.

Revision ID: 005
Revises: 004
Create Date: 2026-09-18
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organisations",
        sa.Column(
            "allow_pickle_models",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("organisations", "allow_pickle_models")
