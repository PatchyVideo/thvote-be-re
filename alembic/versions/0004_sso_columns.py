"""add thbwiki_uid and qq_openid SSO columns to user table

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user", sa.Column("thbwiki_uid", sa.String(128), nullable=True))
    op.add_column("user", sa.Column("qq_openid", sa.String(128), nullable=True))
    op.create_index(
        "uq_user_thbwiki_uid",
        "user",
        ["thbwiki_uid"],
        unique=True,
        postgresql_where=sa.text("thbwiki_uid IS NOT NULL"),
        sqlite_where=sa.text("thbwiki_uid IS NOT NULL"),
    )
    op.create_index(
        "uq_user_qq_openid",
        "user",
        ["qq_openid"],
        unique=True,
        postgresql_where=sa.text("qq_openid IS NOT NULL"),
        sqlite_where=sa.text("qq_openid IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_user_qq_openid", table_name="user")
    op.drop_index("uq_user_thbwiki_uid", table_name="user")
    op.drop_column("user", "qq_openid")
    op.drop_column("user", "thbwiki_uid")
