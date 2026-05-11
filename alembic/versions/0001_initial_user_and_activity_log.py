"""initial: user and activity_log tables

Baseline migration that brings the User and ActivityLog tables under
Alembic's version control.  The schemas mirror src/db_model/{user,activity_log}.py
field-by-field; partial unique indexes guard against duplicate email/phone
while still allowing NULLs (Rust voter fields are optional).

Note: existing voting tables (raw_*, character, music, cp, questionnaire)
are intentionally NOT created here — they live outside this baseline and
should be brought under Alembic in a follow-up migration when their
schema is finalized.

Revision ID: 0001
Revises:
Create Date: 2026-04-27
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("phone_number", sa.String(length=32), nullable=True),
        sa.Column(
            "phone_verified", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column(
            "email_verified", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("password_hash", sa.String(length=512), nullable=True),
        sa.Column("legacy_salt", sa.String(length=255), nullable=True),
        sa.Column("nickname", sa.String(length=64), nullable=True),
        sa.Column("pfp", sa.String(length=512), nullable=True),
        sa.Column("removed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "register_date",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "register_ip_address",
            sa.String(length=64),
            nullable=False,
            server_default="",
        ),
        sa.CheckConstraint(
            "removed = TRUE OR phone_number IS NOT NULL OR email IS NOT NULL",
            name="at_least_one_identifier",
        ),
    )
    # partial unique indexes — Rust voters allow NULL email/phone (SSO-only signups)
    op.create_index(
        "ix_user_email_unique",
        "user",
        ["email"],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )
    op.create_index(
        "ix_user_phone_unique",
        "user",
        ["phone_number"],
        unique=True,
        postgresql_where=sa.text("phone_number IS NOT NULL"),
    )

    op.create_table(
        "activity_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("target_email", sa.String(length=255), nullable=True),
        sa.Column("target_phone", sa.String(length=32), nullable=True),
        sa.Column("old_value", sa.String(length=512), nullable=True),
        sa.Column("new_value", sa.String(length=512), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("requester_ip", sa.String(length=64), nullable=True),
        sa.Column("additional_fingerprint", sa.String(length=1024), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_activity_log_event_type", "activity_log", ["event_type"])
    op.create_index("ix_activity_log_user_id", "activity_log", ["user_id"])
    op.create_index("ix_activity_log_created_at", "activity_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_activity_log_created_at", table_name="activity_log")
    op.drop_index("ix_activity_log_user_id", table_name="activity_log")
    op.drop_index("ix_activity_log_event_type", table_name="activity_log")
    op.drop_table("activity_log")

    op.drop_index("ix_user_phone_unique", table_name="user")
    op.drop_index("ix_user_email_unique", table_name="user")
    op.drop_table("user")
