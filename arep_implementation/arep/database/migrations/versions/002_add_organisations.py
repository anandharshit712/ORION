"""Add organisations, api_keys, and update users for multi-tenancy

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
        sa.Column("id", sa.String(36), primary_key=True),   # UUID as string
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False, unique=True),
        sa.Column("plan", sa.String(32), nullable=False, default="free"),
        sa.Column("run_credits", sa.Integer, nullable=False, default=50),
        sa.Column("stripe_customer_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("label", sa.String(128), nullable=False, default=""),
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
    # Add org_id and role to existing users table
    op.add_column("users", sa.Column("org_id", sa.String(36), nullable=True))
    op.add_column("users", sa.Column("role", sa.String(32), nullable=True, default="member"))


def downgrade() -> None:
    op.drop_column("users", "role")
    op.drop_column("users", "org_id")
    op.drop_table("webhook_deliveries")
    op.drop_table("api_keys")
    op.drop_table("organisations")
