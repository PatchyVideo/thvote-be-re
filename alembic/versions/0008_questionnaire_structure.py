"""add questionnaire structure tables + paper_answer (B-039)

5 tables for the backend-managed questionnaire structure (aligned to the
frontend questionnaireV2 shape) plus structured answer storage:
  questionnaire_def / question_group_def / question_def / option_def
  paper_answer (replaces the opaque papers_json blob)

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-08
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "questionnaire_def",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vote_year", sa.Integer(), nullable=False),
        sa.Column("slot", sa.String(32), nullable=False),
        sa.Column("category", sa.String(8), nullable=False),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column("introduction", sa.Text(), nullable=False, server_default=""),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint(
            "vote_year", "id", name="uq_questionnaire_def_year_id"
        ),
    )
    op.create_index(
        "ix_questionnaire_def_vote_year", "questionnaire_def", ["vote_year"]
    )

    op.create_table(
        "question_group_def",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("questionnaire_id", sa.Integer(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "initial_question_id",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_index(
        "ix_question_group_def_questionnaire_id",
        "question_group_def",
        ["questionnaire_id"],
    )

    op.create_table(
        "question_def",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column(
            "type", sa.String(8), nullable=False, server_default="Single"
        ),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "introduction", sa.Text(), nullable=False, server_default=""
        ),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "max_input_len", sa.Integer(), nullable=False, server_default="1000"
        ),
    )
    op.create_index("ix_question_def_group_id", "question_def", ["group_id"])

    op.create_table(
        "option_def",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("related_question_ids", sa.JSON(), nullable=False),
        sa.Column("mutex_option_ids", sa.JSON(), nullable=False),
        sa.Column(
            "option_group", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_option_def_question_id", "option_def", ["question_id"])

    op.create_table(
        "paper_answer",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("vote_id", sa.String(255), nullable=False),
        sa.Column("vote_year", sa.Integer(), nullable=False),
        sa.Column("questionnaire_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("active_question_id", sa.Integer(), nullable=True),
        sa.Column("selected_option_ids", sa.JSON(), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "vote_id",
            "vote_year",
            "questionnaire_id",
            "group_id",
            name="uq_paper_answer_voter_group",
        ),
    )
    op.create_index("ix_paper_answer_vote_id", "paper_answer", ["vote_id"])
    op.create_index("ix_paper_answer_vote_year", "paper_answer", ["vote_year"])


def downgrade() -> None:
    op.drop_table("paper_answer")
    op.drop_table("option_def")
    op.drop_table("question_def")
    op.drop_table("question_group_def")
    op.drop_table("questionnaire_def")
