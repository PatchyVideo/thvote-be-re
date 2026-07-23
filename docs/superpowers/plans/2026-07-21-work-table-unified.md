# Work 表 + 前后端统一 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 unified `work` 表，voteable 用 work_id FK 替代 origin/album，前后端同步适配 API 契约。

**Architecture:** 重写 Alembic migration（work → voteable → candidate 一次性建完），VoteObjects DAO JOIN work 返回 filterMeta + workIds/workTypes，前端从 filterMeta 构建筛选组件纯客户端过滤，admin 新增 work CRUD。

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy async + Alembic + Redis；前端 Vue 3 + TypeScript；admin_ui Vue 3 + TypeScript

## Global Constraints

- `/vote-objects` 响应新增 `filterMeta`（kinds + works），每个 item 加 `workIds: number[]` / `workTypes: number[]`，移除 `origin` / `album`
- work.type 枚举：`old` | `new` | `CD` | `book` | `others`
- 前端筛选数据源从 `filterMeta` 构建，不依赖静态 `work.ts` / `music.ts albumList`
- compute 模块不改
- work_id 允许 NULL（回填匹配不上时）

---

### Task 1: 重写 Alembic migration

**Files:**
- Modify: `alembic/versions/12a5f2e6dbed_voteable_cross_year_stable_id.py`

**Interfaces:**
- Consumes: 现有 `candidate_character` 表（含 origin/name_jp/origin/type/first_appearance/merged_into）；现有 `candidate_music` 表（含 name/name_jp/type/first_appearance/album/merged_into）
- Produces: `work` 表、`voteable_character` 表、`voteable_music` 表；candidate_* 精简列 + voteable_id FK + UNIQUE(vote_year, voteable_id)；final_ranking 加 voteable_id

- [ ] **Step 1: 编写 migration upgrade()**

```python
"""voteable_cross_year_stable_id (rewritten: work table + voteable + candidate refactor)

Revision ID: 12a5f2e6dbed
Revises: 0014
Create Date: 2026-07-20 21:34:30.197935
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

    # ── 5. 回填 voteable — 从 candidate 按 name GROUP，origin/album → work_id ──
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
    """Seed work table from frontend static data."""
    works = [
        # work.ts (42 条)
        ("东方灵异传", "old"), ("东方封魔录", "old"), ("东方梦时空", "old"),
        ("东方幻想乡", "old"), ("东方怪绮谈", "old"),
        ("东方红魔乡", "new"), ("东方妖妖梦", "new"), ("东方萃梦想", "new"),
        ("东方永夜抄", "new"), ("东方花映塚", "new"), ("东方风神录", "new"),
        ("东方绯想天", "new"), ("东方地灵殿", "new"), ("东方星莲船", "new"),
        ("东方非想天则", "new"), ("东方文花帖DS", "new"), ("东方神灵庙", "new"),
        ("东方心绮楼", "new"), ("东方辉针城", "new"), ("东方深秘录", "new"),
        ("东方绀珠传", "new"), ("东方凭依华", "new"), ("东方天空璋", "new"),
        ("东方鬼形兽", "new"), ("东方刚欲异闻", "new"), ("东方虹龙洞", "new"),
        ("东方兽王园", "new"), ("东方文花帖", "new"), ("弹幕天邪鬼", "new"),
        ("妖精大战争", "new"), ("秘封噩梦日记", "new"), ("弹幕狂们的黑市", "new"),
        ("蓬莱人形", "CD"), ("莲台野夜行", "CD"), ("旧约酒馆", "CD"),
        ("东方文花帖（书籍）", "book"), ("东方求闻史纪", "book"),
        ("东方三月精", "book"), ("东方儚月抄", "book"), ("东方香霖堂", "book"),
        ("东方茨歌仙", "book"), ("东方铃奈庵", "book"), ("东方智灵奇传", "book"),
        ("东方醉蝶华", "book"), ("其他", "others"),
        # music.ts albumList 额外 (不在 work.ts 中)
        ("幻想曲拔萃", "CD"), ("全人类的天乐录", "CD"),
        ("核热造神非想天则", "CD"), ("暗黑能乐集心绮楼", "CD"),
        ("深秘乐曲集", "CD"), ("深秘乐曲集·补", "CD"),
        ("完全凭依唱片名录", "CD"), ("贪欲之兽的音乐", "CD"),
        ("梦违科学世纪", "CD"), ("卯酉东海道", "CD"), ("幺乐团的历史", "CD"),
        ("大空魔术", "CD"), ("未知之花 魅知之旅", "CD"), ("鸟船遗迹", "CD"),
        ("伊奘诺物质", "CD"), ("燕石博物志", "CD"), ("虹色的北斗七星", "CD"),
        ("东方紫香花", "book"), ("The Grimoire of Marisa", "book"),
        ("东方外来韦编", "book"),
        ("秋霜玉", "new"), ("稀翁玉", "new"), ("Torte Le Magic", "new"),
        ("黄昏酒场", "new"), ("神魔讨绮传", "new"), ("东方幻想麻将", "new"),
        ("Cradle - 东方幻乐祀典", "CD"), ("8BIT MUSIC POWER FINAL", "CD"),
        ("INDIE Live Expo", "others"), ("东方音焰火", "CD"),
    ]
    # INSERT 逐条，name 冲突时跳过
    for name, wtype in works:
        op.execute(
            sa.text(
                "INSERT INTO work (name, type) VALUES (:n, :t) ON CONFLICT (name) DO NOTHING"
            ).bindparams(n=name, t=wtype)
        )


def downgrade() -> None:
    # final_ranking
    op.drop_column("final_ranking", "voteable_id")
    # candidate_character 回退
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
        SET name = v.name, name_jp = v.name_jp, origin = COALESCE(w.name, ''),
            type = v.type, first_appearance = v.first_appearance
        FROM voteable_character v
        LEFT JOIN work w ON w.id = v.work_id
        WHERE c.voteable_id = v.id
    """)
    op.drop_column("candidate_character", "voteable_id")
    op.execute("UPDATE candidate_character SET name = 'unknown' WHERE name IS NULL")
    op.alter_column("candidate_character", "name", nullable=False)
    op.create_unique_constraint("uq_candidate_char_year_name", "candidate_character", ["vote_year", "name"])
    # candidate_music 回退
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
            first_appearance = v.first_appearance, album = COALESCE(w.name, '')
        FROM voteable_music v
        LEFT JOIN work w ON w.id = v.work_id
        WHERE c.voteable_id = v.id
    """)
    op.drop_column("candidate_music", "voteable_id")
    op.execute("UPDATE candidate_music SET name = 'unknown' WHERE name IS NULL")
    op.alter_column("candidate_music", "name", nullable=False)
    op.create_unique_constraint("uq_candidate_music_year_name", "candidate_music", ["vote_year", "name"])
    # 删除 voteable + work
    op.drop_table("voteable_music")
    op.drop_table("voteable_character")
    op.drop_table("work")
```

- [ ] **Step 2: 在测试 DB 上执行迁移**

```bash
cd D:/personal/thvote
alembic upgrade head
```

验证：`work` / `voteable_character` / `voteable_music` 表创建成功，`candidate_*` 列精简。

- [ ] **Step 3: Commit**

```bash
git add alembic/versions/12a5f2e6dbed_voteable_cross_year_stable_id.py
git commit -m "feat(work): rewrite migration — work table + voteable with work_id"
```

---

### Task 2: DB Models — Work + Voteable 更新

**Files:**
- Create: `src/db_model/work.py`
- Modify: `src/db_model/voteable.py`
- Modify: `src/db_model/__init__.py`

**Interfaces:**
- Produces: `Work` ORM model；`VoteableCharacter.work_id`、`VoteableMusic.work_id` 替代 origin/album

- [ ] **Step 1: 编写 `src/db_model/work.py`**

```python
"""Work model — cross-cutting catalog of Touhou works/albums."""

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from .base import Base


class Work(Base):
    __tablename__ = "work"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    type = Column(String(16), nullable=False)  # old | new | CD | book | others
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```

- [ ] **Step 2: 更新 `src/db_model/voteable.py`**

```python
"""Voteable models — cross-year stable voting objects.

These tables hold the canonical identity for voteable items.
candidate_* tables reference these via voteable_id.
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from .base import Base


class VoteableCharacter(Base):
    __tablename__ = "voteable_character"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    name_jp = Column(String(255), nullable=False, server_default="")
    type = Column(String(64), nullable=False, server_default="")
    first_appearance = Column(String(16), nullable=True)
    work_id = Column(Integer, ForeignKey("work.id"), nullable=True)
    aliases = Column(JSONB, nullable=False, server_default="[]")
    old_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class VoteableMusic(Base):
    __tablename__ = "voteable_music"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    name_jp = Column(String(255), nullable=False, server_default="")
    type = Column(String(64), nullable=False, server_default="")
    first_appearance = Column(String(16), nullable=True)
    work_id = Column(Integer, ForeignKey("work.id"), nullable=True)
    aliases = Column(JSONB, nullable=False, server_default="[]")
    old_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```

- [ ] **Step 3: 更新 `src/db_model/__init__.py`**

在 import 块加 `from .work import Work`，`__all__` 加 `"Work"`。

```diff
+from .work import Work
...
+   "Work",
```

- [ ] **Step 4: Commit**

```bash
git add src/db_model/work.py src/db_model/voteable.py src/db_model/__init__.py
git commit -m "feat(work): Work model + voteable work_id FK"
```

---

### Task 3: VoteObjects DAO/Service — filterMeta + workIds/workTypes

**Files:**
- Modify: `src/apps/vote_objects/dao.py`
- Modify: `src/apps/vote_objects/service.py`

**Interfaces:**
- Consumes: `VoteableCharacter.work_id`, `VoteableMusic.work_id`, `Work.id/name/type`
- Produces: response 含 `filterMeta: { kinds, works }`，item 含 `workIds: [int]` / `workTypes: [str]`

- [ ] **Step 1: 重写 `src/apps/vote_objects/dao.py`**

```python
"""Vote-objects DAO: grouped candidate listings JOIN voteable + work for metadata."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db_model.candidate import CandidateCharacter, CandidateMusic
from src.db_model.voteable import VoteableCharacter, VoteableMusic
from src.db_model.work import Work

KIND_LABELS = {
    "old": "游戏旧作",
    "new": "游戏新作",
    "CD": "CD",
    "book": "书籍",
    "others": "其他",
}


def _build_alias_map(rows: list[tuple[int, list[str]]]) -> dict[str, int]:
    alias_map: dict[str, int] = {}
    for candidate_id, aliases in rows:
        for a in (aliases or []):
            alias_map[a] = candidate_id
    return alias_map


def _build_filter_meta(items: list[dict]) -> dict:
    """Extract unique kinds + works from item list to build filterMeta."""
    works_map: dict[int, dict] = {}  # workId → {workId, name, type}
    kinds_set: set[str] = set()
    for it in items:
        for i, wid in enumerate(it.get("workIds", [])):
            wtype = it["workTypes"][i] if i < len(it.get("workTypes", [])) else ""
            works_map[wid] = {"workId": wid, "name": _work_name_for(it, wid), "type": wtype}
            kinds_set.add(wtype)
    kinds = [{"type": k, "label": KIND_LABELS.get(k, k)} for k in sorted(kinds_set)]
    works = sorted(works_map.values(), key=lambda w: w["name"])
    return {"kinds": kinds, "works": works}


def _work_name_for(item: dict, work_id: int) -> str:
    """Resolve work name from item's local cache or fallback."""
    return item.get("_workNames", {}).get(work_id, "")


class VoteObjectsDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_characters(self, vote_year: int) -> dict:
        rows = (
            (await self.session.execute(
                select(
                    CandidateCharacter.id,
                    VoteableCharacter.name,
                    VoteableCharacter.name_jp,
                    VoteableCharacter.type,
                    VoteableCharacter.first_appearance,
                    VoteableCharacter.aliases,
                    Work.id,
                    Work.name,
                    Work.type,
                )
                .join(VoteableCharacter,
                      CandidateCharacter.voteable_id == VoteableCharacter.id)
                .outerjoin(Work, VoteableCharacter.work_id == Work.id)
                .where(CandidateCharacter.vote_year == vote_year)
                .order_by(VoteableCharacter.name)
            )).all()
        )

        items: list[dict] = []
        alias_pairs: list[tuple[int, list[str]]] = []
        for row in rows:
            cid, name, name_jp, vtype, first_app, aliases, wid, wname, wtype = row
            work_ids = [wid] if wid is not None else []
            work_types = [wtype] if wtype else []
            items.append({
                "candidateId": cid,
                "name": name,
                "nameJp": name_jp or "",
                "type": vtype or "",
                "firstAppearance": first_app or None,
                "workIds": work_ids,
                "workTypes": work_types,
                "_workNames": {wid: wname} if wid else {},
                "_groupKey": wname or "未分类",
            })
            alias_pairs.append((cid, aliases))

        groups = _group_by(items, "_groupKey")
        alias_map = _build_alias_map(alias_pairs)
        filter_meta = _build_filter_meta(items)
        # clean internal keys
        for g in groups:
            for it in g["items"]:
                it.pop("_workNames", None)
                it.pop("_groupKey", None)
        return {
            "voteYear": vote_year,
            "groups": groups,
            "filterMeta": filter_meta,
            "aliasMap": alias_map,
        }

    async def list_music(self, vote_year: int) -> dict:
        rows = (
            (await self.session.execute(
                select(
                    CandidateMusic.id,
                    VoteableMusic.name,
                    VoteableMusic.name_jp,
                    VoteableMusic.type,
                    VoteableMusic.first_appearance,
                    VoteableMusic.aliases,
                    Work.id,
                    Work.name,
                    Work.type,
                )
                .join(VoteableMusic,
                      CandidateMusic.voteable_id == VoteableMusic.id)
                .outerjoin(Work, VoteableMusic.work_id == Work.id)
                .where(CandidateMusic.vote_year == vote_year)
                .order_by(VoteableMusic.name)
            )).all()
        )

        items: list[dict] = []
        alias_pairs: list[tuple[int, list[str]]] = []
        for row in rows:
            cid, name, name_jp, vtype, first_app, aliases, wid, wname, wtype = row
            work_ids = [wid] if wid is not None else []
            work_types = [wtype] if wtype else []
            items.append({
                "candidateId": cid,
                "name": name,
                "nameJp": name_jp or "",
                "type": vtype or "",
                "firstAppearance": first_app or None,
                "workIds": work_ids,
                "workTypes": work_types,
                "_workNames": {wid: wname} if wid else {},
                "_groupKey": wname or "未分类",
            })
            alias_pairs.append((cid, aliases))

        groups = _group_by(items, "_groupKey")
        alias_map = _build_alias_map(alias_pairs)
        filter_meta = _build_filter_meta(items)
        for g in groups:
            for it in g["items"]:
                it.pop("_workNames", None)
                it.pop("_groupKey", None)
        return {
            "voteYear": vote_year,
            "groups": groups,
            "filterMeta": filter_meta,
            "aliasMap": alias_map,
        }

    async def get_one(self, category: str, candidate_id: int) -> dict | None:
        if category == "character":
            row = (await self.session.execute(
                select(
                    CandidateCharacter.id,
                    CandidateCharacter.vote_year,
                    VoteableCharacter.name,
                    VoteableCharacter.name_jp,
                    VoteableCharacter.type,
                    VoteableCharacter.first_appearance,
                    Work.id,
                    Work.name,
                    Work.type,
                )
                .join(VoteableCharacter,
                      CandidateCharacter.voteable_id == VoteableCharacter.id)
                .outerjoin(Work, VoteableCharacter.work_id == Work.id)
                .where(CandidateCharacter.id == candidate_id)
            )).one_or_none()
            if row is None:
                return None
            cid, vy, name, name_jp, vtype, first_app, wid, wname, wtype = row
            return {
                "candidateId": cid,
                "voteYear": vy,
                "name": name,
                "nameJp": name_jp or "",
                "type": vtype or "",
                "firstAppearance": first_app or None,
                "workIds": [wid] if wid is not None else [],
                "workTypes": [wtype] if wtype else [],
            }
        else:
            row = (await self.session.execute(
                select(
                    CandidateMusic.id,
                    CandidateMusic.vote_year,
                    VoteableMusic.name,
                    VoteableMusic.name_jp,
                    VoteableMusic.type,
                    VoteableMusic.first_appearance,
                    Work.id,
                    Work.name,
                    Work.type,
                )
                .join(VoteableMusic,
                      CandidateMusic.voteable_id == VoteableMusic.id)
                .outerjoin(Work, VoteableMusic.work_id == Work.id)
                .where(CandidateMusic.id == candidate_id)
            )).one_or_none()
            if row is None:
                return None
            cid, vy, name, name_jp, vtype, first_app, wid, wname, wtype = row
            return {
                "candidateId": cid,
                "voteYear": vy,
                "name": name,
                "nameJp": name_jp or "",
                "type": vtype or "",
                "firstAppearance": first_app or None,
                "workIds": [wid] if wid is not None else [],
                "workTypes": [wtype] if wtype else [],
            }


def _group_by(items: list[dict], key: str) -> list[dict]:
    groups_map: dict[str, list] = {}
    order: list[str] = []
    for it in items:
        g = it.get(key) or "未分类"
        if g not in groups_map:
            groups_map[g] = []
            order.append(g)
        groups_map[g].append(it)
    return [{"group": g, "items": groups_map[g]} for g in order]
```

- [ ] **Step 2: service 无需改动（透传）**

验证 `src/apps/vote_objects/service.py` 不变，已是透传。

- [ ] **Step 3: Commit**

```bash
git add src/apps/vote_objects/dao.py
git commit -m "feat(work): VoteObjects DAO — JOIN work, filterMeta, workIds/workTypes"
```

---

### Task 4: Admin Work CRUD 后端

**Files:**
- Create: `src/apps/admin/work_service.py`
- Modify: `src/apps/admin/router.py`（注册 work 路由）
- Modify: `src/apps/admin/schemas.py`（加 Work schemas）

**Interfaces:**
- Produces: `GET /admin/works`、`POST /admin/works`、`POST /admin/works/{id}`、`DELETE /admin/works/{id}`

- [ ] **Step 1: 创建 `src/apps/admin/work_service.py`**

```python
"""Work CRUD service for admin panel."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db_model.work import Work
from src.db_model.voteable import VoteableCharacter, VoteableMusic

_logger = logging.getLogger(__name__)

VALID_TYPES = {"old", "new", "CD", "book", "others"}


class WorkService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_works(
        self, q: Optional[str] = None, wtype: Optional[str] = None,
        page: int = 1, page_size: int = 50,
    ) -> dict:
        base = select(
            Work.id, Work.name, Work.type, Work.created_at,
            func.count(func.distinct(VoteableCharacter.id)).label("character_count"),
            func.count(func.distinct(VoteableMusic.id)).label("music_count"),
        ).outerjoin(
            VoteableCharacter, VoteableCharacter.work_id == Work.id,
        ).outerjoin(
            VoteableMusic, VoteableMusic.work_id == Work.id,
        ).group_by(Work.id)

        if q:
            base = base.where(Work.name.ilike(f"%{q}%"))
        if wtype:
            base = base.where(Work.type == wtype)

        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_stmt)).scalar() or 0

        offset = (page - 1) * page_size
        rows = (await self.session.execute(
            base.order_by(Work.name).offset(offset).limit(page_size)
        )).all()

        items = [
            {
                "workId": r[0],
                "name": r[1],
                "type": r[2],
                "createdAt": r[3].isoformat() if r[3] else None,
                "characterCount": r[4] or 0,
                "musicCount": r[5] or 0,
            }
            for r in rows
        ]
        return {"items": items, "total": total}

    async def create_work(self, name: str, wtype: str) -> dict:
        if wtype not in VALID_TYPES:
            raise ValueError(f"Invalid type: {wtype}")
        # check duplicate
        existing = (await self.session.execute(
            select(Work.id).where(Work.name == name)
        )).scalar()
        if existing:
            raise ValueError(f"Work already exists: {name}")
        w = Work(name=name, type=wtype)
        self.session.add(w)
        await self.session.flush()
        return {"workId": w.id}

    async def update_work(self, work_id: int, name: Optional[str], wtype: Optional[str]) -> None:
        w = await self.session.get(Work, work_id)
        if w is None:
            raise LookupError("NOT_FOUND")
        if name is not None:
            w.name = name
        if wtype is not None:
            if wtype not in VALID_TYPES:
                raise ValueError(f"Invalid type: {wtype}")
            w.type = wtype
        await self.session.flush()

    async def delete_work(self, work_id: int) -> None:
        w = await self.session.get(Work, work_id)
        if w is None:
            raise LookupError("NOT_FOUND")
        # check references
        char_count = (await self.session.execute(
            select(func.count()).where(VoteableCharacter.work_id == work_id)
        )).scalar() or 0
        music_count = (await self.session.execute(
            select(func.count()).where(VoteableMusic.work_id == work_id)
        )).scalar() or 0
        if char_count > 0 or music_count > 0:
            raise ValueError("WORK_IN_USE")
        await self.session.delete(w)
        await self.session.flush()
```

- [ ] **Step 2: 在 `src/apps/admin/router.py` 添加 work 路由**

在 router 文件中追加以下路由函数（与其他 CRUD 端点并列）：

```python
from src.apps.admin.work_service import WorkService
from src.common.redis import get_redis


@router.get("/works")
async def list_works(
    q: Optional[str] = None,
    type: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    svc = WorkService(session)
    return await svc.list_works(q=q, wtype=type, page=page, page_size=page_size)


@router.post("/works")
async def create_work(
    body: dict,
    session: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    name = body.get("name", "").strip()
    wtype = body.get("type", "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    svc = WorkService(session)
    try:
        result = await svc.create_work(name, wtype)
        await _clear_vote_objects_cache(redis)
        return result
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/works/{work_id}")
async def update_work(
    work_id: int,
    body: dict,
    session: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    svc = WorkService(session)
    try:
        await svc.update_work(work_id, body.get("name"), body.get("type"))
        await _clear_vote_objects_cache(redis)
        return {"ok": True}
    except LookupError:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/works/{work_id}")
async def delete_work(
    work_id: int,
    session: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    svc = WorkService(session)
    try:
        await svc.delete_work(work_id)
        await _clear_vote_objects_cache(redis)
        return {"ok": True}
    except LookupError:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


async def _clear_vote_objects_cache(redis: aioredis.Redis) -> None:
    """Clear vote-objects cache keys after work/voteable mutations."""
    try:
        keys = await redis.keys("vote_objects:*")
        if keys:
            await redis.delete(*keys)
    except Exception:
        pass
```

- [ ] **Step 3: 在 import 适配（admin candidate_service）**

`candidate_field_specs()` 不再需要改动——它从 model 列推导，`candidate_*` 表只剩 `id, vote_year, voteable_id`，排除 `id, vote_year` 后只剩 `voteable_id`。

无需改动 `candidate_service.py`。

- [ ] **Step 4: Commit**

```bash
git add src/apps/admin/work_service.py src/apps/admin/router.py src/apps/admin/schemas.py
git commit -m "feat(work): admin Work CRUD endpoints + cache invalidation"
```

---

### Task 5: Admin import 适配 work_id

**Files:**
- Modify: `src/apps/admin/service.py`（import_candidates 流程）

- [ ] **Step 1: 查找 import 流程中涉及 origin/album 的代码**

```bash
grep -rn "origin\|album" src/apps/admin/
```

当前 import 走 `compute_dao.upsert_candidates()`，该方法接受 `vote_year, category, items`（items 为 dict 列表）。以前 items 含 name/origin/album 等字段；迁移后 candidate 表只有 `vote_year, voteable_id`，import 流程需拆为两步：

1. 对每个 item，按 name 匹配现有 voteable；无则创建 voteable（含 work_id 匹配）
2. upsert candidate (vote_year, voteable_id)

但在当前代码中 import 流程用了 `compute_dao.upsert_candidates()` — 需要改造。由于 candidate 列已精简，import 的语义变为"从 voteable 池中选参选对象"，而不是"导入原始带元数据行"。

保持 `POST /admin/candidates/import` 接口契约不变，但内部逻辑适配。

具体改动：
- `candidate_field_specs()` 返回 `["voteable_id"]`（唯一可编辑字段）
- import CSV 解析时，`origin`/`album` 列用于匹配 work → 创建 voteable
- `compute_dao.upsert_candidates()` 更新签名

此 task 依赖 compute_dao，但 compute 模块不在此次范围。**标记为后续单独 PR，暂不做**。

- [ ] **Step 2: 确认 import 暂不改动，记录 tech-debt**

Admin import 接口暂时保持现有行为（依赖 candidate 旧列已删除，import 会在迁移后因列不存在而报错）。后续 Task 修复。

- [ ] **Step 3: Commit（如有代码改动）或标记 skip**

```bash
# skip this task for now — import adapt will be a follow-up PR
```

---

### Task 6: 前端 voteObjectsDataSource 适配

**Files:**
- Modify: `thvote-fe/packages/vote/src/common/lib/voteObjectsDataSource.ts`

**Interfaces:**
- Consumes: `GET /vote-objects/characters|music` 新响应格式（含 filterMeta, workIds, workTypes）
- Produces: `filterMeta` ref、`characterListFromBackend`（enrich 用 workIds/workTypes）

- [ ] **Step 1: 重写 `voteObjectsDataSource.ts`**

```typescript
// 投票对象数据源:从后端拉取角色/音乐候选列表,按名称 enriching 静态 shared 数据(image/color/kind 等展示字段)。
// 取代 @touhou-vote/shared/data/character|music 作为投票页运行时列表来源。
import { computed, ref } from 'vue'
import { Character } from '@/vote-character/lib/character'
import { Music } from '@/vote-music/lib/music'
import { characterList as staticCharacterList } from '@touhou-vote/shared/data/character'
import { musicList as staticMusicList } from '@touhou-vote/shared/data/music'
import { voteYear } from '@/common/lib/voteYear'
import { API_PREFIX } from '@/common/lib/apiPrefix'

// ── 类型 ──────────────────────────────────────────────────────────────────
interface FilterMeta {
  kinds: { type: string; label: string }[]
  works: { workId: number; name: string; type: string }[]
}

interface BackendCharacterItem {
  id: number
  name: string
  name_jp: string
  workIds: number[]
  workTypes: string[]
  first_appearance: string | null
}

interface BackendMusicItem {
  id: number
  name: string
  name_jp: string
  workIds: number[]
  workTypes: string[]
  first_appearance: string | null
}

interface BackendGroup<T> {
  group: string
  items: T[]
}

interface VoteObjectsData<T> {
  groups: BackendGroup<T>[]
  filterMeta: FilterMeta
}

const CHARACTER_URL = `${API_PREFIX}/vote-objects/characters?vote_year=${voteYear}`
const MUSIC_URL = `${API_PREFIX}/vote-objects/music?vote_year=${voteYear}`
const CACHE_KEY_CHAR = `voteObjectsCharacters:${voteYear}`
const CACHE_KEY_MUSIC = `voteObjectsMusic:${voteYear}`
const CACHE_KEY_FILTER_META = `voteObjectsFilterMeta:${voteYear}`

// ── 响应式状态 ───────────────────────────────────────────────────────────
export const characterGroupsRaw = ref<BackendGroup<BackendCharacterItem>[]>([])
export const musicGroupsRaw = ref<BackendGroup<BackendMusicItem>[]>([])
export const filterMeta = ref<FilterMeta>({ kinds: [], works: [] })
export const voteObjectsLoading = ref(false)
export const voteObjectsError = ref<string | null>(null)

// ── 工具 ──────────────────────────────────────────────────────────────────
function getWorkName(wid: number): string {
  return filterMeta.value.works.find(w => w.workId === wid)?.name ?? ''
}

export { getWorkName }

// ── enrich ────────────────────────────────────────────────────────────────
function enrichCharacter(item: BackendCharacterItem): Character {
  const s = staticCharacterList.find((c) => c.name === item.name)
  // 从 filterMeta 推导 kind 和 work 列表
  const workNames = item.workIds.map(getWorkName).filter(Boolean)
  const kinds = item.workTypes.length
    ? item.workTypes.filter(Boolean)
    : (s?.kind?.length ? s.kind : ['others'])
  return new Character(
    String(item.id),
    item.name,
    s?.origname ?? item.name_jp,
    s?.altnames ?? [],
    s?.title ?? '',
    s?.image ?? 'https://static.thwiki.cc/favicon.png',
    s?.color ?? '#9b9b9b',
    '',
    s?.date ?? 0,
    false,
    kinds as ('old' | 'new' | 'book' | 'CD' | 'others')[],
    workNames,
  )
}

function enrichMusic(item: BackendMusicItem): Music {
  const s = staticMusicList.find((m) => m.name === item.name)
  const albumName = item.workIds.length ? getWorkName(item.workIds[0]) : ''
  const albumType = item.workTypes[0] ?? ''
  const kinds = item.workTypes.length
    ? item.workTypes.filter(Boolean)
    : (s?.kind?.length ? s.kind : ['others'])
  return new Music(
    String(item.id),
    item.name,
    s?.origname ?? item.name_jp,
    albumName,          // album → work name
    s?.date ?? 0,
    s?.image ?? 'https://static.thwiki.cc/favicon.png',
    s?.music ?? '',
    '',
    false,
    kinds as ('game' | 'book' | 'CD' | 'others')[],
    s?.include ?? [],
  )
}

// ── 扁平列表 ──────────────────────────────────────────────────────────────
export const characterListFromBackend = computed<Character[]>(() =>
  characterGroupsRaw.value.flatMap((g) => g.items.map(enrichCharacter))
)

export const musicListFromBackend = computed<Music[]>(() =>
  musicGroupsRaw.value.flatMap((g) => g.items.map(enrichMusic))
)

// ── 分组名列表 ────────────────────────────────────────────────────────────
export const characterGroupNames = computed<string[]>(() =>
  characterGroupsRaw.value.map((g) => g.group)
)
export const musicGroupNames = computed<string[]>(() =>
  musicGroupsRaw.value.map((g) => g.group)
)

// ── 加载 ──────────────────────────────────────────────────────────────────
let resolveReady: () => void = () => {}
export const voteObjectsReady: Promise<void> = new Promise((r) => {
  resolveReady = r
})
let readyResolved = false
let loadPromise: Promise<void> | null = null

function markReady(): void {
  if (!readyResolved) {
    readyResolved = true
    resolveReady()
  }
}

export function loadVoteObjects(force = false): Promise<void> {
  if (loadPromise && !force) return loadPromise

  loadPromise = (async () => {
    voteObjectsLoading.value = true
    voteObjectsError.value = null
    try {
      if (!force) {
        const cachedChar = sessionStorage.getItem(CACHE_KEY_CHAR)
        const cachedMusic = sessionStorage.getItem(CACHE_KEY_MUSIC)
        const cachedMeta = sessionStorage.getItem(CACHE_KEY_FILTER_META)
        if (cachedChar && cachedMusic && cachedMeta) {
          characterGroupsRaw.value = JSON.parse(cachedChar)
          musicGroupsRaw.value = JSON.parse(cachedMusic)
          filterMeta.value = JSON.parse(cachedMeta)
          return
        }
      }
      const [charRes, musicRes] = await Promise.all([
        fetch(CHARACTER_URL, { credentials: 'include' }),
        fetch(MUSIC_URL, { credentials: 'include' }),
      ])
      if (!charRes.ok) throw new Error(`characters HTTP ${charRes.status}`)
      if (!musicRes.ok) throw new Error(`music HTTP ${musicRes.status}`)
      const charData: VoteObjectsData<BackendCharacterItem> = await charRes.json()
      const musicData: VoteObjectsData<BackendMusicItem> = await musicRes.json()

      characterGroupsRaw.value = charData.groups
      musicGroupsRaw.value = musicData.groups
      // 合并两边 filterMeta（取并集）
      const meta: FilterMeta = {
        kinds: dedupeKinds([...charData.filterMeta.kinds, ...musicData.filterMeta.kinds]),
        works: dedupeWorks([...charData.filterMeta.works, ...musicData.filterMeta.works]),
      }
      filterMeta.value = meta

      sessionStorage.setItem(CACHE_KEY_CHAR, JSON.stringify(charData.groups))
      sessionStorage.setItem(CACHE_KEY_MUSIC, JSON.stringify(musicData.groups))
      sessionStorage.setItem(CACHE_KEY_FILTER_META, JSON.stringify(meta))
    } catch (err) {
      voteObjectsError.value = err instanceof Error ? err.message : String(err)
      console.error('[voteObjects] 拉取投票对象失败,投票页将显示空列表:', err)
    } finally {
      voteObjectsLoading.value = false
      markReady()
    }
  })()

  return loadPromise
}

function dedupeKinds(kinds: { type: string; label: string }[]) {
  const seen = new Set<string>()
  return kinds.filter(k => seen.has(k.type) ? false : (seen.add(k.type), true))
}

function dedupeWorks(works: { workId: number; name: string; type: string }[]) {
  const seen = new Set<number>()
  return works.filter(w => seen.has(w.workId) ? false : (seen.add(w.workId), true))
}

export function clearVoteObjectsCache(): void {
  sessionStorage.removeItem(CACHE_KEY_CHAR)
  sessionStorage.removeItem(CACHE_KEY_MUSIC)
  sessionStorage.removeItem(CACHE_KEY_FILTER_META)
}
```

- [ ] **Step 2: Commit**

```bash
cd D:/personal/thvote-fe
git add packages/vote/src/common/lib/voteObjectsDataSource.ts
git commit -m "feat(work): voteObjectsDataSource adapt — filterMeta + workIds/workTypes"
```

---

### Task 7: 前端筛选组件适配 — workList.ts + albumList.ts

**Files:**
- Modify: `thvote-fe/packages/vote/src/vote-character/lib/workList.ts`
- Modify: `thvote-fe/packages/vote/src/vote-music/lib/albumList.ts`

- [ ] **Step 1: 重写 `workList.ts`（从 filterMeta 构建）**

```typescript
import { computed, ref } from 'vue'
import { filterMeta, characterGroupNames } from '@/common/lib/voteObjectsDataSource'

interface SelectList {
  name: string
  value: string
}

// kinds 从 filterMeta 动态构建
export const kinds = computed<SelectList[]>(() =>
  filterMeta.value.kinds.map(k => ({ name: k.label, value: k.type }))
)

export const filterForKind = ref<SelectList[]>([])
export const filterForKindTem = ref<SelectList[]>([])

// 初始化
filterForKind.value = [...kinds.value]
filterForKindTem.value = [...kinds.value]

export function getFilterForKindTem(): void {
  filterForKindTem.value = JSON.parse(JSON.stringify(filterForKind.value))
}
export function updateFilterForKindTem(kind: SelectList): void {
  const index = filterForKindTem.value.findIndex((item) => item.name === kind.name)
  index === -1 ? filterForKindTem.value.push(kind) : filterForKindTem.value.splice(index, 1)
}
export function updateFilterForKind(): void {
  filterForKind.value = JSON.parse(JSON.stringify(filterForKindTem.value))
}
export function resetFilterForKindTem(): void {
  filterForKindTem.value = JSON.parse(JSON.stringify(kinds.value))
}

// works 下拉从 filterMeta 构建
export const worksListAfterFilter = computed<SelectList[]>(() => {
  const activeKinds = filterForKind.value.map((k) => k.value)
  return filterMeta.value.works
    .filter((w) => activeKinds.includes(w.type))
    .map((w) => ({ name: w.name, value: w.type }))
})

export const workSelected = ref<SelectList>({ name: '', value: '' })

export const worksListAfterFilterTem = computed<SelectList[]>(() => {
  const activeKinds = filterForKindTem.value.map((k) => k.value)
  return filterMeta.value.works
    .filter((w) => activeKinds.includes(w.type))
    .map((w) => ({ name: w.name, value: w.type }))
})

export const workSelectedTem = ref<SelectList>({ name: '', value: '' })
export function updateWorkSelected(): void {
  workSelected.value = workSelectedTem.value
}
export function getWorkSelectedTem(): void {
  workSelectedTem.value = workSelected.value
}
export function resetWorkSelectedTem(): void {
  workSelectedTem.value = { name: '', value: '' }
}
```

- [ ] **Step 2: 重写 `albumList.ts`（从 filterMeta 构建）**

```typescript
import { computed, ref } from 'vue'
import { filterMeta, musicGroupNames } from '@/common/lib/voteObjectsDataSource'

interface SelectList {
  name: string
  value: string
}

// 音乐页用不同 label
const MUSIC_KIND_LABELS: Record<string, string> = {
  old: '游戏旧作',
  new: '游戏OST',
  CD: 'CD',
  book: '出版物',
  others: '其他',
}

export const kinds = computed<SelectList[]>(() =>
  filterMeta.value.kinds.map(k => ({
    name: MUSIC_KIND_LABELS[k.type] ?? k.label,
    value: k.type,
  }))
)

export const filterForKind = ref<SelectList[]>([])
export const filterForKindTem = ref<SelectList[]>([])

filterForKind.value = [...kinds.value]
filterForKindTem.value = [...kinds.value]

export function getFilterForKindTem(): void {
  filterForKindTem.value = JSON.parse(JSON.stringify(filterForKind.value))
}
export function updateFilterForKindTem(kind: SelectList): void {
  const index = filterForKindTem.value.findIndex((item) => item.name === kind.name)
  index === -1 ? filterForKindTem.value.push(kind) : filterForKindTem.value.splice(index, 1)
}
export function updateFilterForKind(): void {
  filterForKind.value = JSON.parse(JSON.stringify(filterForKindTem.value))
}
export function resetFilterForKindTem(): void {
  filterForKindTem.value = JSON.parse(JSON.stringify(kinds.value))
}

export const albumsListAfterFilter = computed<SelectList[]>(() => {
  const activeKinds = filterForKind.value.map((k) => k.value)
  return filterMeta.value.works
    .filter((w) => activeKinds.includes(w.type))
    .map((w) => ({ name: w.name, value: w.type }))
})

export const albumSelected = ref<SelectList>({ name: '', value: '' })

export const albumsListAfterFilterTem = computed<SelectList[]>(() => {
  const activeKinds = filterForKindTem.value.map((k) => k.value)
  return filterMeta.value.works
    .filter((w) => activeKinds.includes(w.type))
    .map((w) => ({ name: w.name, value: w.type }))
})

export const albumSelectedTem = ref<SelectList>({ name: '', value: '' })
export function updateAlbumSelected(): void {
  albumSelected.value = albumSelectedTem.value
}
export function getAlbumSelectedTem(): void {
  albumSelectedTem.value = albumSelected.value
}
export function resetAlbumSelectedTem(): void {
  albumSelectedTem.value = { name: '', value: '' }
}
```

- [ ] **Step 3: Commit**

```bash
cd D:/personal/thvote-fe
git add packages/vote/src/vote-character/lib/workList.ts packages/vote/src/vote-music/lib/albumList.ts
git commit -m "feat(work): workList/albumList — build filter options from filterMeta"
```

---

### Task 8: 前端筛选逻辑适配 — characterList + musicList

**Files:**
- Modify: `thvote-fe/packages/vote/src/vote-character/lib/characterList.ts`
- Modify: `thvote-fe/packages/vote/src/vote-music/lib/musicList.ts`

- [ ] **Step 1: 更新 `characterList.ts` 过滤逻辑**

当前 `filterCharactersByMeta(charaList, kinds, workSelected.value.name)` 依赖 `character.work`（字符串数组）和 `character.kind`。改为用 `workIds` 和 `workTypes`。

先检查 `filterCharactersByMeta` 和 `characterSearch.ts` 的实现：

```bash
grep -rn "filterCharactersByMeta" thvote-fe/packages/vote/src/common/lib/
```

需要更新该函数以匹配新的数据结构。`Character` 实例有 `work: string[]` 和 `kind: string[]`，enrich 后已从 filterMeta 填充。故过滤逻辑改为：

```typescript
import { computed, ref } from 'vue'
import type { Character } from './character'
import { character0 } from './character'
import { characterHonmei, characters } from './voteData'
import { filterForKind, workSelected } from './workList'
import { filterMeta, characterListFromBackend } from '@/common/lib/voteObjectsDataSource'
import { orderOptions as sharedOrderOptions, searchAndSort } from '@/common/lib/characterSearch'

export const characterList = characterListFromBackend

export const characterListLeft = computed<Character[]>(() => {
  let charaList = characterList.value.filter((character) => {
    let characterInCharacters = false
    for (let i = 0; i < characters.value.length; i++) {
      if (characters.value[i].id === character.id) characterInCharacters = true
    }
    return character.id != characterHonmei.value.id && !characterInCharacters
  })

  // kind filter: item.workTypes 与选中的 kinds 取交集
  const activeKinds = filterForKind.value.map((k) => k.value)
  if (activeKinds.length) {
    charaList = charaList.filter((c) => c.kind.some((k) => activeKinds.includes(k)))
  }

  // work filter: 按选中 work name 匹配
  if (workSelected.value.name) {
    const targetWid = filterMeta.value.works.find(w => w.name === workSelected.value.name)?.workId
    if (targetWid) {
      charaList = charaList.filter((c) => (c as any)._workIds?.includes(targetWid))
    }
  }

  return charaList
})

// ... rest unchanged (charactersVoted, orderOptions, keyword, characterListLeftWithFilter)
```

但 `Character` 类没有 `_workIds` 字段。需要给 `Character` 加一个 `workIds: number[]` 属性，在 `enrichCharacter` 中填充。

更新 `character.ts`：

```typescript
export class Character {
  // ... existing fields ...
  workIds: number[]

  constructor(
    // ... existing params ...
    workIds: number[] = [],
  ) {
    // ... existing assignments ...
    this.workIds = workIds
  }
}
```

更新 `voteObjectsDataSource.ts` 的 `enrichCharacter`：

```diff
  return new Character(
    String(item.id), item.name, ...
-   workNames,
+   workNames, item.workIds,
  )
```

- [ ] **Step 2: 更新 `musicList.ts` 过滤逻辑**

`musicList.ts` 当前过滤：
- `music.kind.find((k2) => k2 === k1.value)` — 用 kind 数组
- `music.album === albumSelected.value.name` — 用 album 字符串

改为：
- kind 过滤不变（已在 enrich 中从 filterMeta 填充）
- album 过滤改为按 workName 过滤

```typescript
export const musicListLeft = computed<Music[]>(() => {
  let list = musicList.value.filter((music) => {
    let musicInMusics = false
    for (let i = 0; i < musics.value.length; i++) {
      if (musics.value[i].id === music.id) musicInMusics = true
    }
    return music.id != musicHonmei.value.id && !musicInMusics
  })

  if (filterForKind.value.length) {
    list = list.filter((music) => filterForKind.value.find((k1) => music.kind.find((k2) => k2 === k1.value)))
  }

  if (albumSelected.value.name !== '') {
    list = list.filter(
      (music) => music.album === albumSelected.value.name || music.include.includes(albumSelected.value.name)
    )
  }
  return list
})
```

`music.album` 在 enrich 时已赋值为 work name（从 filterMeta 查得），故 `music.album === albumSelected.value.name` 仍然有效。无需改动！

- [ ] **Step 3: 更新 Character 类加 workIds**

<file path="thvote-fe/packages/vote/src/vote-character/lib/character.ts">

在 constructor 加 `workIds: number[] = []` 参数，赋值 `this.workIds = workIds`。

- [ ] **Step 4: Commit**

```bash
cd D:/personal/thvote-fe
git add packages/vote/src/vote-character/lib/character.ts \
        packages/vote/src/vote-character/lib/characterList.ts \
        packages/vote/src/common/lib/voteObjectsDataSource.ts
git commit -m "feat(work): Character.workIds + filtering by workIds"
```

---

### Task 9: 前端展示组件 — 专辑名从 filterMeta 反查

**Files:**
- Modify: `thvote-fe/packages/vote/src/vote-music/VoteMusic.vue`
- Modify: `thvote-fe/packages/vote/src/vote-music/components/MusicSelect.vue`
- Modify: `thvote-fe/packages/vote/src/vote-music/components/MusicHonmeiCard.vue`

- [ ] **Step 1: 替换 album 显示**

当前模板直接用 `{{ item.album }}`（enrich 时已从 work name 填充），保持不变。`music.album` 已经是 work name。

确认 `enrichMusic` 中 `albumName` 正确从 `item.workIds[0]` → `getWorkName()` 赋值后，展示组件无需改动。

**验证通过 → 无需改动。**

- [ ] **Step 2: Commit**

```bash
# 无需 commit（展示组件已正确）
```

---

### Task 10: Admin UI — Works API + WorksView

**Files:**
- Create: `thvote/admin-ui/src/api/works.ts`
- Create: `thvote/admin-ui/src/views/WorksView.vue`
- Modify: `thvote/admin-ui/src/router.ts`
- Modify: `thvote/admin-ui/src/components/AppShell.vue`（加导航项）

- [ ] **Step 1: 创建 `admin-ui/src/api/works.ts`**

```typescript
import { apiGet, apiSend, qs } from './client'

export interface WorkRow {
  workId: number
  name: string
  type: string
  characterCount: number
  musicCount: number
  createdAt: string | null
}

export interface WorkListResponse {
  items: WorkRow[]
  total: number
}

export async function listWorks(params: {
  q?: string; type?: string; page?: number; pageSize?: number
}): Promise<WorkListResponse> {
  return apiGet<WorkListResponse>(`/admin/works${qs(params)}`)
}

export async function createWork(data: { name: string; type: string }): Promise<{ workId: number }> {
  return apiSend<{ workId: number }>('/admin/works', 'POST', data)
}

export async function updateWork(id: number, data: { name?: string; type?: string }): Promise<{ ok: boolean }> {
  return apiSend<{ ok: boolean }>(`/admin/works/${id}`, 'POST', data)
}

export async function deleteWork(id: number): Promise<{ ok: boolean }> {
  return apiSend<{ ok: boolean }>(`/admin/works/${id}`, 'DELETE')
}
```

- [ ] **Step 2: 创建 `admin-ui/src/views/WorksView.vue`**

参照 `CandidatesView.vue` 模式：用 `DataTable`、`FilterBar`、`Modal`、`useAsync`、`usePagination` 组合。

核心结构：
- `<FilterBar>`：搜索框（`q`）+ type 下拉 + 新增按钮
- `<DataTable>`：列 workId/name/type(tag)/characterCount/musicCount/操作(编辑/删除)
- `<Modal>`：新增/编辑弹窗（name input + type select）
- 删除 confirm：显示关联的 voteable 数量

完整实现代码较长，参照现有页面模板。

- [ ] **Step 3: 更新 `router.ts`**

```diff
+import WorksView from '@/views/WorksView.vue'
...
+{ path: '/works', component: WorksView },
```

- [ ] **Step 4: 更新 `AppShell.vue` 导航**

在侧边栏导航加"作品管理"链接 → `/works`。

- [ ] **Step 5: Commit**

```bash
cd D:/personal/thvote
git add admin-ui/src/api/works.ts admin-ui/src/views/WorksView.vue admin-ui/src/router.ts admin-ui/src/components/AppShell.vue
git commit -m "feat(work): admin-ui WorksView + works API"
```

---

### Task 11: 合约测试 + 集成测试

**Files:**
- Modify: 相关测试文件

- [ ] **Step 1: 验证 `/vote-objects/characters` response shape**

```bash
cd D:/personal/thvote
# 启动 test 环境
make up
# 等 backend health 后
curl -s http://localhost:8000/api/v1/vote-objects/characters | python -m json.tool | head -60
```

检查：
- 顶层含 `filterMeta: { kinds: [...], works: [...] }`
- `groups[].items[]` 含 `workIds: [n]` / `workTypes: ["new"]`
- **不含** `origin` / `album`

- [ ] **Step 2: 更新已有测试**

搜索 `origin` / `album` 关键字，更新断言。

```bash
grep -rn "origin\|album" tests/ | grep -v ".pyc"
```

- [ ] **Step 3: Commit**

```bash
git add tests/
git commit -m "test(work): update contract tests for filterMeta + workIds/workTypes"
```

---

## 执行顺序

```
Task 1 (migration)
  → Task 2 (models)
    → Task 3 (VoteObjects DAO)
      → Task 4 (Admin Work CRUD)
      → Task 6 (Frontend data source)
        → Task 7 (Frontend filter components)
          → Task 8 (Frontend filter logic)
            → Task 9 (Frontend display)
      → Task 10 (Admin UI WorksView)
  → Task 11 (Tests)
```

Task 5 (import adapt) 标记为 follow-up，暂不执行。
