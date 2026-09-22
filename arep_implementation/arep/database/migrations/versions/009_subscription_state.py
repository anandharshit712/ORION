"""Subscription state on organisations (Phase 1.4)

Adds the fields a Stripe subscription needs beyond ``stripe_customer_id``:
the subscription id, its status, and the end of the current period.

``current_period_end`` is what the billing page shows as the renewal date, and
what tells an ``invoice.paid`` handler which period it is topping up for. Status
is stored rather than inferred because Stripe distinguishes states we care
about differently — ``past_due`` still has access, ``canceled`` does not.

Nullable throughout: orgs created in beta have no Stripe presence at all, and
must keep working.

Revision ID: 009
Revises: 008
Create Date: 2026-09-21
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organisations",
        sa.Column("stripe_subscription_id", sa.String(128), nullable=True),
    )
    op.add_column(
        "organisations",
        sa.Column("subscription_status", sa.String(32), nullable=True),
    )
    op.add_column(
        "organisations",
        sa.Column("current_period_end", sa.DateTime, nullable=True),
    )
    # Webhooks arrive keyed by customer, so that lookup must not table-scan.
    op.create_index(
        "ix_organisations_stripe_customer_id",
        "organisations",
        ["stripe_customer_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_organisations_stripe_customer_id", table_name="organisations")
    op.drop_column("organisations", "current_period_end")
    op.drop_column("organisations", "subscription_status")
    op.drop_column("organisations", "stripe_subscription_id")
