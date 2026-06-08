"""add dojin_nomination table (二创提名审核, B-037)

New table dojin_nomination — one row per nominated dojin work, with review
status (pending/approved/rejected). udid is the scraper-normalized work id
used for dedup; NULL when scraping failed (then the (vote_id, udid) unique
constraint is not triggered, leaving the row for manual review).

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-08
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dojin_nomination",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("vote_id", sa.String(255), nullable=False),
        sa.Column("udid", sa.String(255), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.String(512), nullable=False, server_default=""),
        sa.Column("author", sa.String(512), nullable=False, server_default=""),
        sa.Column("dojin_type", sa.String(32), nullable=False, server_default=""),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("publish_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status", sa.String(16), nullable=False, server_default="pending"
        ),
        sa.Column("reject_reason", sa.String(512), nullable=True),
        sa.Column("reviewed_by", sa.String(64), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("vote_id", "udid", name="uq_dojin_nom_voter_udid"),
    )
    op.create_index(
        "ix_dojin_nomination_vote_id", "dojin_nomination", ["vote_id"]
    )
    op.create_index("ix_dojin_nomination_udid", "dojin_nomination", ["udid"])


def downgrade() -> None:
    op.drop_index("ix_dojin_nomination_udid", table_name="dojin_nomination")
    op.drop_index("ix_dojin_nomination_vote_id", table_name="dojin_nomination")
    op.drop_table("dojin_nomination")
