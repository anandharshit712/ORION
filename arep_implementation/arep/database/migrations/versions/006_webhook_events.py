"""Webhook idempotency ledger (Phase 0.3)

Adds ``webhook_events``, keyed by the provider's own event id.

Payment providers retry a delivery whenever the response is slow, non-2xx or
simply lost, so the same event id arrives more than once in normal operation.
Without this table a retried ``invoice.paid`` grants the credits twice. The
table lands before the Stripe integration in 1.4 so the handler is built on it
from the first line rather than retrofitted onto a money path.

The payload is deliberately not stored: it carries customer billing details and
nothing in the replay path needs it.

Revision ID: 006
Revises: 005
Create Date: 2026-09-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webhook_events",
        # The provider's id ("evt_..."), not one we generate — matching across
        # retries of the same delivery is the entire point of the table.
        sa.Column("event_id", sa.String(255), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False, server_default="stripe"),
        sa.Column("event_type", sa.String(100), nullable=True),
        # received = signature verified, handler not finished (a retry is let
        # through, since the effect may never have been applied).
        # processed = handler completed; later retries are dropped.
        sa.Column("status", sa.String(16), nullable=False, server_default="received"),
        sa.Column(
            "received_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
        sa.Column("processed_at", sa.DateTime, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("webhook_events")
