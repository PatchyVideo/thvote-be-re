"""voteable_cross_year_stable_id (rewritten: work table + voteable + candidate refactor)

Revision ID: 12a5f2e6dbed
Revises: 0014
Create Date: 2026-07-20 21:34:30.197935

新增 work 表、voteable_* 表（work_id FK 替代 origin/album）；
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
    # ── 1. CREATE work 表 ──────────────────────────────────────────────
    op.create_table(
        "work",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_unique_constraint("uq_work_name", "work", ["name"])

    # ── 2. 灌入 work 种子数据 ───────────────────────────────────────────
    _seed_work(op)

    # ── 3. CREATE voteable_character ───────────────────────────────────
    op.create_table(
        "voteable_character",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_jp", sa.String(255), nullable=False, server_default=""),
        sa.Column("type", sa.String(64), nullable=False, server_default=""),
        sa.Column("first_appearance", sa.String(16), nullable=True),
        sa.Column("work_id", sa.Integer(), nullable=True),
        sa.Column("aliases", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("old_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_foreign_key("fk_voteable_char_work", "voteable_character",
                          "work", ["work_id"], ["id"])

    # ── 4. CREATE voteable_music ───────────────────────────────────────
    op.create_table(
        "voteable_music",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_jp", sa.String(255), nullable=False, server_default=""),
        sa.Column("type", sa.String(64), nullable=False, server_default=""),
        sa.Column("first_appearance", sa.String(16), nullable=True),
        sa.Column("work_id", sa.Integer(), nullable=True),
        sa.Column("aliases", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("old_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_foreign_key("fk_voteable_music_work", "voteable_music",
                          "work", ["work_id"], ["id"])

    # ── 5. 回填 voteable — candidate 按 name GROUP，origin/album → work_id ──
    op.execute("""
        INSERT INTO voteable_character (name, name_jp, type, first_appearance, work_id)
        SELECT c.name,
               MAX(c.name_jp) FILTER (WHERE c.name_jp <> '')     AS name_jp,
               MAX(c.type)    FILTER (WHERE c.type <> '')        AS type,
               MAX(c.first_appearance)                           AS first_appearance,
               w.id AS work_id
        FROM candidate_character c
        LEFT JOIN work w ON w.name = c.origin
        WHERE c.merged_into IS NULL
        GROUP BY c.name, w.id
    """)
    op.execute("""
        INSERT INTO voteable_music (name, name_jp, type, first_appearance, work_id)
        SELECT c.name,
               MAX(c.name_jp) FILTER (WHERE c.name_jp <> '')     AS name_jp,
               MAX(c.type)    FILTER (WHERE c.type <> '')        AS type,
               MAX(c.first_appearance)                           AS first_appearance,
               w.id AS work_id
        FROM candidate_music c
        LEFT JOIN work w ON w.name = c.album
        WHERE c.merged_into IS NULL
        GROUP BY c.name, w.id
    """)

    # ── 6. candidate 加 voteable_id ────────────────────────────────────
    op.add_column("candidate_character",
                  sa.Column("voteable_id", sa.Integer(), nullable=True))
    op.add_column("candidate_music",
                  sa.Column("voteable_id", sa.Integer(), nullable=True))

    # ── 7. 回填 candidate.voteable_id ───────────────────────────────────
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

    # ── 8. DROP 旧列 + 旧约束 ──────────────────────────────────────────
    op.drop_constraint("uq_candidate_char_year_name", "candidate_character", type_="unique")
    op.drop_column("candidate_character", "name")
    op.drop_column("candidate_character", "name_jp")
    op.drop_column("candidate_character", "origin")
    op.drop_column("candidate_character", "type")
    op.drop_column("candidate_character", "first_appearance")
    op.drop_column("candidate_character", "merged_into")

    op.drop_constraint("uq_candidate_music_year_name", "candidate_music", type_="unique")
    op.drop_column("candidate_music", "name")
    op.drop_column("candidate_music", "name_jp")
    op.drop_column("candidate_music", "type")
    op.drop_column("candidate_music", "first_appearance")
    op.drop_column("candidate_music", "album")
    op.drop_column("candidate_music", "merged_into")

    # ── 9. voteable_id NOT NULL + 新 UNIQUE + FK ────────────────────────
    op.alter_column("candidate_character", "voteable_id", nullable=False)
    op.alter_column("candidate_music", "voteable_id", nullable=False)

    op.create_unique_constraint(
        "uq_candidate_char_year_voteable", "candidate_character",
        ["vote_year", "voteable_id"])
    op.create_unique_constraint(
        "uq_candidate_music_year_voteable", "candidate_music",
        ["vote_year", "voteable_id"])

    op.create_foreign_key(
        "fk_candidate_char_voteable", "candidate_character",
        "voteable_character", ["voteable_id"], ["id"])
    op.create_foreign_key(
        "fk_candidate_music_voteable", "candidate_music",
        "voteable_music", ["voteable_id"], ["id"])

    # ── 10. final_ranking 加 voteable_id ────────────────────────────────
    op.add_column("final_ranking",
                  sa.Column("voteable_id", sa.Integer(), nullable=True))
    op.execute("""
        UPDATE final_ranking f
        SET voteable_id = v.id
        FROM voteable_character v
        WHERE v.name = f.name AND f.category = 'character'
    """)
    op.execute("""
        UPDATE final_ranking f
        SET voteable_id = v.id
        FROM voteable_music v
        WHERE v.name = f.name AND f.category = 'music'
    """)


def _seed_work(op) -> None:
    """Seed work table from frontend static data (work.ts + music.ts albumList, deduplicated)."""
    works = [
        # ── work.ts (42 条) ──────────────────────────────────
        ("东方灵异传", "old"),
        ("东方封魔录", "old"),
        ("东方梦时空", "old"),
        ("东方幻想乡", "old"),
        ("东方怪绮谈", "old"),
        ("东方红魔乡", "new"),
        ("东方妖妖梦", "new"),
        ("东方萃梦想", "new"),
        ("东方永夜抄", "new"),
        ("东方花映塚", "new"),
        ("东方风神录", "new"),
        ("东方绯想天", "new"),
        ("东方地灵殿", "new"),
        ("东方星莲船", "new"),
        ("东方非想天则", "new"),
        ("东方文花帖DS", "new"),
        ("东方神灵庙", "new"),
        ("东方心绮楼", "new"),
        ("东方辉针城", "new"),
        ("东方深秘录", "new"),
        ("东方绀珠传", "new"),
        ("东方凭依华", "new"),
        ("东方天空璋", "new"),
        ("东方鬼形兽", "new"),
        ("东方刚欲异闻", "new"),
        ("东方虹龙洞", "new"),
        ("东方兽王园", "new"),
        ("东方文花帖", "new"),
        ("弹幕天邪鬼", "new"),
        ("妖精大战争", "new"),
        ("秘封噩梦日记", "new"),
        ("弹幕狂们的黑市", "new"),
        ("蓬莱人形", "CD"),
        ("莲台野夜行", "CD"),
        ("旧约酒馆", "CD"),
        ("东方文花帖（书籍）", "book"),
        ("东方求闻史纪", "book"),
        ("东方三月精", "book"),
        ("东方儚月抄", "book"),
        ("东方香霖堂", "book"),
        ("东方茨歌仙", "book"),
        ("东方铃奈庵", "book"),
        ("东方智灵奇传", "book"),
        ("东方醉蝶华", "book"),
        ("其他", "others"),
        # ── music.ts albumList 额外（不在 work.ts 中）──────────────────
        ("幻想曲拔萃", "CD"),
        ("全人类的天乐录", "CD"),
        ("核热造神非想天则", "CD"),
        ("暗黑能乐集心绮楼", "CD"),
        ("深秘乐曲集", "CD"),
        ("深秘乐曲集·补", "CD"),
        ("完全凭依唱片名录", "CD"),
        ("贪欲之兽的音乐", "CD"),
        ("梦违科学世纪", "CD"),
        ("卯酉东海道", "CD"),
        ("幺乐团的历史", "CD"),
        ("大空魔术", "CD"),
        ("未知之花 魅知之旅", "CD"),
        ("鸟船遗迹", "CD"),
        ("伊奘诺物质", "CD"),
        ("燕石博物志", "CD"),
        ("虹色的北斗七星", "CD"),
        ("东方紫香花", "book"),
        ("The Grimoire of Marisa", "book"),
        ("东方外来韦编", "book"),
        ("秋霜玉", "new"),
        ("稀翁玉", "new"),
        ("Torte Le Magic", "new"),
        ("黄昏酒场", "new"),
        ("神魔讨绮传", "new"),
        ("东方幻想麻将", "new"),
        ("Cradle - 东方幻乐祀典", "CD"),
        ("8BIT MUSIC POWER FINAL", "CD"),
        ("INDIE Live Expo", "others"),
        ("东方音焰火", "CD"),
    ]
    for name, wtype in works:
        op.execute(
            sa.text(
                "INSERT INTO work (name, type) VALUES (:n, :t) ON CONFLICT (name) DO NOTHING"
            ).bindparams(n=name, t=wtype)
        )


def downgrade() -> None:
    # ── final_ranking ──────────────────────────────────────────────────
    op.drop_column("final_ranking", "voteable_id")

    # ── candidate_character 回退 ───────────────────────────────────────
    op.drop_constraint("fk_candidate_char_voteable", "candidate_character", type_="foreignkey")
    op.drop_constraint("uq_candidate_char_year_voteable", "candidate_character", type_="unique")
    op.add_column("candidate_character", sa.Column("name", sa.String(255), nullable=True))
    op.add_column("candidate_character", sa.Column("name_jp", sa.String(255), nullable=True, server_default=""))
    op.add_column("candidate_character", sa.Column("origin", sa.String(255), nullable=True, server_default=""))
    op.add_column("candidate_character", sa.Column("type", sa.String(64), nullable=True, server_default=""))
    op.add_column("candidate_character", sa.Column("first_appearance", sa.String(16), nullable=True))
    op.add_column("candidate_character", sa.Column("merged_into", sa.Integer(), nullable=True))
    op.execute("""
        UPDATE candidate_character c
        SET name = v.name, name_jp = v.name_jp,
            origin = COALESCE(w.name, ''),
            type = v.type, first_appearance = v.first_appearance
        FROM voteable_character v
        LEFT JOIN work w ON w.id = v.work_id
        WHERE c.voteable_id = v.id
    """)
    op.drop_column("candidate_character", "voteable_id")
    op.execute("UPDATE candidate_character SET name = 'unknown' WHERE name IS NULL")
    op.alter_column("candidate_character", "name", nullable=False)
    op.create_unique_constraint("uq_candidate_char_year_name", "candidate_character", ["vote_year", "name"])

    # ── candidate_music 回退 ───────────────────────────────────────────
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
            first_appearance = v.first_appearance,
            album = COALESCE(w.name, '')
        FROM voteable_music v
        LEFT JOIN work w ON w.id = v.work_id
        WHERE c.voteable_id = v.id
    """)
    op.drop_column("candidate_music", "voteable_id")
    op.execute("UPDATE candidate_music SET name = 'unknown' WHERE name IS NULL")
    op.alter_column("candidate_music", "name", nullable=False)
    op.create_unique_constraint("uq_candidate_music_year_name", "candidate_music", ["vote_year", "name"])

    # ── 删除 voteable + work ───────────────────────────────────────────
    op.drop_table("voteable_music")
    op.drop_table("voteable_character")
    op.drop_table("work")
