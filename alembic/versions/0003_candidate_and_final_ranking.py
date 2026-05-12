"""add candidate_character, candidate_music, final_ranking tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidate_character",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vote_year", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_jp", sa.String(255), nullable=False, server_default=""),
        sa.Column("origin", sa.Text(), nullable=False, server_default=""),
        sa.Column("type", sa.String(64), nullable=False, server_default=""),
        sa.Column("first_appearance", sa.String(16), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vote_year", "name", name="uq_candidate_char_year_name"),
    )
    op.create_index("ix_candidate_character_vote_year", "candidate_character", ["vote_year"])

    op.create_table(
        "candidate_music",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vote_year", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_jp", sa.String(255), nullable=False, server_default=""),
        sa.Column("type", sa.String(64), nullable=False, server_default=""),
        sa.Column("first_appearance", sa.String(16), nullable=True),
        sa.Column("album", sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vote_year", "name", name="uq_candidate_music_year_name"),
    )
    op.create_index("ix_candidate_music_vote_year", "candidate_music", ["vote_year"])

    op.create_table(
        "final_ranking",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vote_year", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("vote_count", sa.Integer(), nullable=False),
        sa.Column("first_vote_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "vote_year", "category", "rank", name="uq_final_ranking_year_cat_rank"
        ),
    )
    op.create_index("ix_final_ranking_vote_year", "final_ranking", ["vote_year"])


def downgrade() -> None:
    op.drop_table("final_ranking")
    op.drop_table("candidate_music")
    op.drop_table("candidate_character")
