"""remodel questionnaire structure to free-form (B-041)

Drop & recreate the 4 structure tables (empty on this branch) with the new
shape: free-form questionnaire list (no vote_year/slot), autoincrement PKs,
key/required on questionnaire, hidden_by_default on group. paper_answer
is unchanged.

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-08
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("option_def")
    op.drop_table("question_def")
    op.drop_table("question_group_def")
    op.drop_table("questionnaire_def")

    op.create_table(
        "questionnaire_def",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False, server_default=""),
        sa.Column("introduction", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.String(8), nullable=False, server_default="main"),
        sa.Column(
            "required", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("key", name="uq_questionnaire_def_key"),
    )

    op.create_table(
        "question_group_def",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("questionnaire_id", sa.Integer(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "hidden_by_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "ix_question_group_def_questionnaire_id",
        "question_group_def",
        ["questionnaire_id"],
    )

    op.create_table(
        "question_def",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(8), nullable=False, server_default="Single"),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("introduction", sa.Text(), nullable=False, server_default=""),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "max_input_len", sa.Integer(), nullable=False, server_default="1000"
        ),
    )
    op.create_index("ix_question_def_group_id", "question_def", ["group_id"])

    op.create_table(
        "option_def",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
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


def downgrade() -> None:
    op.drop_table("option_def")
    op.drop_table("question_def")
    op.drop_table("question_group_def")
    op.drop_table("questionnaire_def")
