"""Email verification on user accounts (Phase 0.4, defect D-04)

Adds ``users.email_verified`` (default FALSE) plus the verified-at timestamp and
the single outstanding verification token.

The token lives on the user row rather than in a side table: there is only ever
one outstanding verification per user, a resend replaces it, and nothing needs
the history. Only the SHA256 is stored, as with password resets.

Existing users are backfilled to verified. They signed up before the requirement
existed, and there is no address on file we can prove was checked — locking out
current accounts to retro-enforce a rule they were never shown would be an
outage, not a security win. New signups start unverified.

Revision ID: 007
Revises: 006
Create Date: 2026-09-20
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime, nullable=True))
    op.add_column("users", sa.Column("verification_token_hash", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("verification_sent_at", sa.DateTime, nullable=True))
    op.create_index(
        "ix_users_verification_token_hash", "users", ["verification_token_hash"]
    )

    # Grandfather everyone who already had an account (see module docstring).
    op.execute(
        "UPDATE users SET email_verified = TRUE, email_verified_at = CURRENT_TIMESTAMP"
    )


def downgrade() -> None:
    op.drop_index("ix_users_verification_token_hash", table_name="users")
    op.drop_column("users", "verification_sent_at")
    op.drop_column("users", "verification_token_hash")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "email_verified")
