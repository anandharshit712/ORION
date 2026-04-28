"""Add organisations, api_keys, webhook_deliveries; extend users for multi-tenancy

Revision ID: 002
Revises: 001
Create Date: 2026-04-26
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organisations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("plan", sa.String(32), nullable=False, server_default="free"),
        sa.Column("run_credits", sa.Integer, nullable=False, server_default="50"),
        sa.Column("stripe_customer_id", sa.String(128), nullable=True),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("key_hash", sa.String(128), nullable=False, unique=True, index=True),
        sa.Column("key_prefix", sa.String(16), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("last_used_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("revoked_at", sa.DateTime, nullable=True),
    )
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
    # Extend users for multi-tenancy
    op.add_column("users", sa.Column("org_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=True, index=True))
    op.add_column("users", sa.Column("role", sa.String(32), nullable=False, server_default="member"))


def downgrade() -> None:
    op.drop_column("users", "role")
    op.drop_column("users", "org_id")
    op.drop_table("webhook_deliveries")
    op.drop_table("api_keys")
    op.drop_table("organisations")
