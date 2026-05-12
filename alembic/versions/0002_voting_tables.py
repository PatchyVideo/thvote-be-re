"""voting tables: raw_submit and legacy character/music/cp/questionnaire

Brings the remaining ORM models under Alembic version control.  The 0001
baseline intentionally deferred these tables until their schemas were
finalised; they are now stable.

Active tables (used by submit-handler):
  raw_character, raw_music, raw_cp, raw_paper, raw_dojin

Legacy tables (still present in db_model/ but no longer written to;
kept here so that Base.metadata stays consistent with the Alembic history):
  character, music, cp, questionnaire

Deploying to an existing instance
----------------------------------
If the target database already has these tables (created via DEBUG=true /
``Base.metadata.create_all``), do NOT run ``upgrade`` — it will fail with
"table already exists".  Instead, stamp the current state as 0002 without
applying DDL::

    alembic stamp 0002

Then continue with any future migrations normally.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-12
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # Active submit tables                                                  #
    # ------------------------------------------------------------------ #
    op.create_table(
        "raw_character",
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
    )
    op.create_index("ix_raw_character_vote_id", "raw_character", ["vote_id"])
    op.create_index(
        "idx_raw_character_vote_created",
        "raw_character",
        ["vote_id", sa.text("created_at DESC")],
        postgresql_ops={"created_at": "DESC"},
    )

    op.create_table(
        "raw_music",
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
    )
    op.create_index("ix_raw_music_vote_id", "raw_music", ["vote_id"])
    op.create_index(
        "idx_raw_music_vote_created",
        "raw_music",
        ["vote_id", sa.text("created_at DESC")],
        postgresql_ops={"created_at": "DESC"},
    )

    op.create_table(
        "raw_cp",
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
    )
    op.create_index("ix_raw_cp_vote_id", "raw_cp", ["vote_id"])
    op.create_index(
        "idx_raw_cp_vote_created",
        "raw_cp",
        ["vote_id", sa.text("created_at DESC")],
        postgresql_ops={"created_at": "DESC"},
    )

    op.create_table(
        "raw_paper",
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
        sa.Column("papers_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_raw_paper_vote_id", "raw_paper", ["vote_id"])
    op.create_index(
        "idx_raw_paper_vote_created",
        "raw_paper",
        ["vote_id", sa.text("created_at DESC")],
        postgresql_ops={"created_at": "DESC"},
    )

    op.create_table(
        "raw_dojin",
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
    )
    op.create_index("ix_raw_dojin_vote_id", "raw_dojin", ["vote_id"])
    op.create_index(
        "idx_raw_dojin_vote_created",
        "raw_dojin",
        ["vote_id", sa.text("created_at DESC")],
        postgresql_ops={"created_at": "DESC"},
    )

    # ------------------------------------------------------------------ #
    # Legacy tables (no longer written to; retained for schema consistency) #
    # ------------------------------------------------------------------ #
    op.create_table(
        "character",
        sa.Column(
            "id",
            sa.String(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("submit_datetime", sa.DateTime(), nullable=False),
        sa.Column("character_list", sa.JSON(), nullable=False),
    )

    op.create_table(
        "music",
        sa.Column(
            "id",
            sa.String(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("submit_datetime", sa.DateTime(), nullable=False),
        sa.Column("music_list", sa.JSON(), nullable=False),
    )

    op.create_table(
        "cp",
        sa.Column(
            "id",
            sa.String(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("submit_datetime", sa.DateTime(), nullable=False),
        sa.Column("cp_list", sa.JSON(), nullable=False),
    )

    op.create_table(
        "questionnaire",
        sa.Column(
            "id",
            sa.String(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("submit_datetime", sa.DateTime(), nullable=False),
        sa.Column("questionnaire_list", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    # Legacy tables first (no FK dependencies between them)
    op.drop_table("questionnaire")
    op.drop_table("cp")
    op.drop_table("music")
    op.drop_table("character")

    # Raw submit tables
    op.drop_index("idx_raw_dojin_vote_created", table_name="raw_dojin")
    op.drop_index("ix_raw_dojin_vote_id", table_name="raw_dojin")
    op.drop_table("raw_dojin")

    op.drop_index("idx_raw_paper_vote_created", table_name="raw_paper")
    op.drop_index("ix_raw_paper_vote_id", table_name="raw_paper")
    op.drop_table("raw_paper")

    op.drop_index("idx_raw_cp_vote_created", table_name="raw_cp")
    op.drop_index("ix_raw_cp_vote_id", table_name="raw_cp")
    op.drop_table("raw_cp")

    op.drop_index("idx_raw_music_vote_created", table_name="raw_music")
    op.drop_index("ix_raw_music_vote_id", table_name="raw_music")
    op.drop_table("raw_music")

    op.drop_index("idx_raw_character_vote_created", table_name="raw_character")
    op.drop_index("ix_raw_character_vote_id", table_name="raw_character")
    op.drop_table("raw_character")
