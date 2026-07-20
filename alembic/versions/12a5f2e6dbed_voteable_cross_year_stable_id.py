"""voteable_cross_year_stable_id

Revision ID: 12a5f2e6dbed
Revises: 0014
Create Date: 2026-07-20 21:34:30.197935

新增 voteable_music / voteable_character 表作为跨年稳定投票对象；
candidate_* 精简为纯年度关联表 (vote_year, voteable_id)；
final_ranking 加 voteable_id。
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "12a5f2e6dbed"
down_revision: Union[str, Sequence[str], None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. 新建 voteable_character ──────────────────────────────────────
    op.create_table(
        "voteable_character",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_jp", sa.String(255), nullable=False, server_default=""),
        sa.Column("origin", sa.String(255), nullable=False, server_default=""),
        sa.Column("type", sa.String(64), nullable=False, server_default=""),
        sa.Column("first_appearance", sa.String(16), nullable=True),
        sa.Column("aliases", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("old_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── 2. 新建 voteable_music ──────────────────────────────────────────
    op.create_table(
        "voteable_music",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_jp", sa.String(255), nullable=False, server_default=""),
        sa.Column("type", sa.String(64), nullable=False, server_default=""),
        sa.Column("first_appearance", sa.String(16), nullable=True),
        sa.Column("album", sa.String(255), nullable=True),
        sa.Column("aliases", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("old_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── 3. 回填 voteable — 从 candidate 按 name 分组 ─────────────────────
    # character
    op.execute("""
        INSERT INTO voteable_character (name, name_jp, origin, type, first_appearance)
        SELECT name,
               MAX(name_jp)       FILTER (WHERE name_jp <> '') AS name_jp,
               MAX(origin)        FILTER (WHERE origin <> '')  AS origin,
               MAX(type)          FILTER (WHERE type <> '')    AS type,
               MAX(first_appearance) AS first_appearance
        FROM candidate_character
        WHERE merged_into IS NULL
        GROUP BY name
    """)
    # music
    op.execute("""
        INSERT INTO voteable_music (name, name_jp, type, first_appearance, album)
        SELECT name,
               MAX(name_jp)       FILTER (WHERE name_jp <> '') AS name_jp,
               MAX(type)          FILTER (WHERE type <> '')    AS type,
               MAX(first_appearance) AS first_appearance,
               MAX(album)         FILTER (WHERE album IS NOT NULL) AS album
        FROM candidate_music
        WHERE merged_into IS NULL
        GROUP BY name
    """)

    # ── 4. candidate 加 voteable_id ────────────────────────────────────
    op.add_column("candidate_character",
                  sa.Column("voteable_id", sa.Integer(), nullable=True))
    op.add_column("candidate_music",
                  sa.Column("voteable_id", sa.Integer(), nullable=True))

    # ── 5. 回填 candidate.voteable_id ───────────────────────────────────
    op.execute("""
        UPDATE candidate_character c
        SET voteable_id = v.id
        FROM voteable_character v
        WHERE v.name = c.name
    """)
    op.execute("""
        UPDATE candidate_music c
        SET voteable_id = v.id
        FROM voteable_music v
        WHERE v.name = c.name
    """)

    # ── 6. 删除旧列 + 旧约束 ────────────────────────────────────────────
    # candidate_character
    op.drop_constraint("uq_candidate_char_year_name", "candidate_character", type_="unique")
    op.drop_column("candidate_character", "name")
    op.drop_column("candidate_character", "name_jp")
    op.drop_column("candidate_character", "origin")
    op.drop_column("candidate_character", "type")
    op.drop_column("candidate_character", "first_appearance")
    op.drop_column("candidate_character", "merged_into")

    # candidate_music
    op.drop_constraint("uq_candidate_music_year_name", "candidate_music", type_="unique")
    op.drop_column("candidate_music", "name")
    op.drop_column("candidate_music", "name_jp")
    op.drop_column("candidate_music", "type")
    op.drop_column("candidate_music", "first_appearance")
    op.drop_column("candidate_music", "album")
    op.drop_column("candidate_music", "merged_into")

    # ── 7. 设置 NOT NULL + 新 UNIQUE ────────────────────────────────────
    # voteable_id 设为 NOT NULL（回填后所有行都有值）
    op.alter_column("candidate_character", "voteable_id", nullable=False)
    op.alter_column("candidate_music", "voteable_id", nullable=False)

    # 新唯一约束
    op.create_unique_constraint(
        "uq_candidate_char_year_voteable",
        "candidate_character",
        ["vote_year", "voteable_id"],
    )
    op.create_unique_constraint(
        "uq_candidate_music_year_voteable",
        "candidate_music",
        ["vote_year", "voteable_id"],
    )

    # 外键
    op.create_foreign_key(
        "fk_candidate_char_voteable",
        "candidate_character", "voteable_character",
        ["voteable_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_candidate_music_voteable",
        "candidate_music", "voteable_music",
        ["voteable_id"], ["id"],
    )

    # ── 8. final_ranking 加 voteable_id ──────────────────────────────────
    op.add_column("final_ranking",
                  sa.Column("voteable_id", sa.Integer(), nullable=True))

    # 回填 character
    op.execute("""
        UPDATE final_ranking f
        SET voteable_id = v.id
        FROM voteable_character v
        WHERE v.name = f.name AND f.category = 'character'
    """)
    # 回填 music
    op.execute("""
        UPDATE final_ranking f
        SET voteable_id = v.id
        FROM voteable_music v
        WHERE v.name = f.name AND f.category = 'music'
    """)


def downgrade() -> None:
    # ── 反向：final_ranking ──────────────────────────────────────────────
    op.drop_column("final_ranking", "voteable_id")

    # ── 反向：candidate_character ────────────────────────────────────────
    op.drop_constraint("fk_candidate_char_voteable", "candidate_character", type_="foreignkey")
    op.drop_constraint("uq_candidate_char_year_voteable", "candidate_character", type_="unique")
    op.add_column("candidate_character", sa.Column("name", sa.String(255), nullable=True))
    op.add_column("candidate_character", sa.Column("name_jp", sa.String(255), nullable=True, server_default=""))
    op.add_column("candidate_character", sa.Column("origin", sa.String(255), nullable=True, server_default=""))
    op.add_column("candidate_character", sa.Column("type", sa.String(64), nullable=True, server_default=""))
    op.add_column("candidate_character", sa.Column("first_appearance", sa.String(16), nullable=True))
    op.add_column("candidate_character", sa.Column("merged_into", sa.Integer(), nullable=True))
    # 尝试从 voteable 恢复数据
    op.execute("""
        UPDATE candidate_character c
        SET name = v.name, name_jp = v.name_jp, origin = v.origin,
            type = v.type, first_appearance = v.first_appearance
        FROM voteable_character v
        WHERE c.voteable_id = v.id
    """)
    op.drop_column("candidate_character", "voteable_id")
    op.execute("UPDATE candidate_character SET name = 'unknown' WHERE name IS NULL")
    op.alter_column("candidate_character", "name", nullable=False)
    op.create_unique_constraint("uq_candidate_char_year_name", "candidate_character", ["vote_year", "name"])

    # ── 反向：candidate_music ────────────────────────────────────────────
    op.drop_constraint("fk_candidate_music_voteable", "candidate_music", type_="foreignkey")
    op.drop_constraint("uq_candidate_music_year_voteable", "candidate_music", type_="unique")
    op.add_column("candidate_music", sa.Column("name", sa.String(255), nullable=True))
    op.add_column("candidate_music", sa.Column("name_jp", sa.String(255), nullable=True, server_default=""))
    op.add_column("candidate_music", sa.Column("type", sa.String(64), nullable=True, server_default=""))
    op.add_column("candidate_music", sa.Column("first_appearance", sa.String(16), nullable=True))
    op.add_column("candidate_music", sa.Column("album", sa.String(255), nullable=True))
    op.add_column("candidate_music", sa.Column("merged_into", sa.Integer(), nullable=True))
    op.execute("""
        UPDATE candidate_music c
        SET name = v.name, name_jp = v.name_jp, type = v.type,
            first_appearance = v.first_appearance, album = v.album
        FROM voteable_music v
        WHERE c.voteable_id = v.id
    """)
    op.drop_column("candidate_music", "voteable_id")
    op.execute("UPDATE candidate_music SET name = 'unknown' WHERE name IS NULL")
    op.alter_column("candidate_music", "name", nullable=False)
    op.create_unique_constraint("uq_candidate_music_year_name", "candidate_music", ["vote_year", "name"])

    # ── 反向：删除 voteable 表 ───────────────────────────────────────────
    op.drop_table("voteable_music")
    op.drop_table("voteable_character")
