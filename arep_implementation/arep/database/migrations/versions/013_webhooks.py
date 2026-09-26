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

**This migration replaces an older ``webhook_deliveries``.** Migration 002 created
a table of that name for an outbound-webhook feature that was never built: it has
``url`` and ``payload`` columns, no ``webhook_id``, and nothing in the codebase has
ever read or written it. As first written, this migration simply created the name
again, so ``alembic upgrade head`` failed on any fresh database. It was not caught
because dev builds the schema with ``create_all`` from the ORM - where the name is
defined exactly once - and the migration chain only runs in the Postgres CI job.

The old table is dropped here rather than in a migration of its own, so that the
name is never defined twice at any point in the chain. The downgrade recreates it,
because downgrading to 012 has to leave the schema that upgrading to 012 produces.

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
    # Migration 002's dead table, dropped before the name is used again.
    op.drop_table("webhook_deliveries")

    op.create_table(
        "webhooks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("events", sa.Text(), nullable=False),
        sa.Column("secret", sa.String(length=128), nullable=False),
        # sa.true(), not sa.text("1"): Postgres renders the latter as
        # `BOOLEAN DEFAULT 1` and refuses it as an integer default on a boolean
        # column. SQLite accepts it, which is why dev never saw this.
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
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
        sa.Column("delivered", sa.Boolean(), nullable=False, server_default=sa.false()),
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

    # Put migration 002's table back. Downgrading to 012 has to leave the schema
    # that upgrading to 012 produces, or 002's own downgrade fails later on a
    # table that is no longer there - which turns one bad migration into a chain
    # nobody can reverse.
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("url", sa.String(512), nullable=False),
        sa.Column("payload", sa.Text, nullable=False),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("delivered_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
