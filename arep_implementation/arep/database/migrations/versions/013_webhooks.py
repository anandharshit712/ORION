"""Outbound webhooks (Phase 3.1)

Adds ``webhooks`` and ``webhook_deliveries``.

Lets a customer register "call me when it's done" instead of polling, which is
what makes ORION part of a CI pipeline rather than a site you visit.

Two notes on the columns:

``webhooks.secret`` is plaintext on purpose, unlike a password. It is a *shared*
secret - we need the original to compute the HMAC the customer verifies - so a
one-way hash would make the feature impossible. It is credential material at
rest and the column should be treated that way.

``webhook_deliveries`` stores outcomes and never response bodies. Echoing a body
back would turn a webhook into a way to read whatever the URL pointed at, and
the error is a category rather than the transport's message because "connection
refused" and "timed out" are different enough to map a network with.

Revision ID: 013
Revises: 012
Create Date: 2026-09-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webhooks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("events", sa.Text(), nullable=False),
        sa.Column("secret", sa.String(length=128), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("last_delivery_at", sa.DateTime(), nullable=True),
        sa.Column(
            "consecutive_failures", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhooks_org_id", "webhooks", ["org_id"])

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("webhook_id", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column(
            "delivered", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(length=64), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        # CASCADE: delivery history is meaningless without the webhook it
        # belongs to, and orphaned rows accumulate silently.
        sa.ForeignKeyConstraint(["webhook_id"], ["webhooks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_webhook_deliveries_webhook_id", "webhook_deliveries", ["webhook_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_deliveries_webhook_id", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
    op.drop_index("ix_webhooks_org_id", table_name="webhooks")
    op.drop_table("webhooks")
