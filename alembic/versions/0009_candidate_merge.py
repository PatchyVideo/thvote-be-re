"""add merged_into to candidate tables (B-040)

Normalization/dedup pointer: a non-null merged_into means this candidate row
has been merged into the referenced canonical candidate; NULL means the row is
itself canonical. Vote listing and tallying only consider canonical rows.

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-08
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "candidate_character",
        sa.Column("merged_into", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_candidate_character_merged_into",
        "candidate_character",
        ["merged_into"],
    )
    op.add_column(
        "candidate_music",
        sa.Column("merged_into", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_candidate_music_merged_into",
        "candidate_music",
        ["merged_into"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_candidate_music_merged_into", table_name="candidate_music"
    )
    op.drop_column("candidate_music", "merged_into")
    op.drop_index(
        "ix_candidate_character_merged_into", table_name="candidate_character"
    )
    op.drop_column("candidate_character", "merged_into")
