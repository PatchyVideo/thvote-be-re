"""add sync_run_log, raw_work, and legacy_mongo_id columns

New tables needed for MongoDB sync (B-034):
  sync_run_log  — one row per sync run, records progress and outcome.
  raw_work      — stores raw work-category submit payloads, mirrors the
                  shape of raw_character / raw_music / raw_cp / raw_dojin.

New nullable UNIQUE column on each of the five existing raw submit tables:
  legacy_mongo_id VARCHAR(24) — the 24-hex-char MongoDB ObjectId of the
  document this row was migrated from, NULL for rows created natively.
  UNIQUE constraint allows the sync runner to do upsert-by-mongo-id without
  table scans.

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-07
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # New table: sync_run_log                                              #
    # ------------------------------------------------------------------ #
    op.create_table(
        "sync_run_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("collections", sa.JSON(), nullable=False),
        sa.Column("total_docs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "initiated_by", sa.String(8), nullable=False, server_default="api"
        ),
        sa.UniqueConstraint("run_id", name="uq_sync_run_log_run_id"),
    )

    # ------------------------------------------------------------------ #
    # New table: raw_work                                                   #
    # ------------------------------------------------------------------ #
    op.create_table(
        "raw_work",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("vote_id", sa.String(255), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("user_ip", sa.String(255), nullable=False, server_default="<unknown>"),
        sa.Column("additional_fingreprint", sa.String(1024), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("legacy_mongo_id", sa.String(24), nullable=True),
        sa.UniqueConstraint("legacy_mongo_id", name="uq_raw_work_legacy_mongo_id"),
    )
    op.create_index("ix_raw_work_vote_id", "raw_work", ["vote_id"])
    op.create_index(
        "idx_raw_work_vote_created",
        "raw_work",
        ["vote_id", sa.text("created_at DESC")],
        postgresql_ops={"created_at": "DESC"},
    )

    # ------------------------------------------------------------------ #
    # Add legacy_mongo_id to the five existing raw submit tables           #
    # ------------------------------------------------------------------ #
    for table in ("raw_character", "raw_music", "raw_cp", "raw_paper", "raw_dojin"):
        op.add_column(
            table,
            sa.Column("legacy_mongo_id", sa.String(24), nullable=True),
        )
        op.create_unique_constraint(
            f"uq_{table}_legacy_mongo_id",
            table,
            ["legacy_mongo_id"],
        )


def downgrade() -> None:
    # Remove legacy_mongo_id from the five raw submit tables (reverse order)
    for table in ("raw_dojin", "raw_paper", "raw_cp", "raw_music", "raw_character"):
        op.drop_constraint(f"uq_{table}_legacy_mongo_id", table, type_="unique")
        op.drop_column(table, "legacy_mongo_id")

    # Drop raw_work
    op.drop_index("idx_raw_work_vote_created", table_name="raw_work")
    op.drop_index("ix_raw_work_vote_id", table_name="raw_work")
    op.drop_table("raw_work")

    # Drop sync_run_log
    op.drop_table("sync_run_log")
