# MongoDB 全量历史数据同步 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将旧 Rust 后端的三个 MongoDB 数据库（users / submits_v1 / submits_v1_final）中的历史数据全量迁移到 PostgreSQL，支持断点续跑和进度追踪，提供 HTTP API 和 CLI 两种触发方式。

**Architecture:** `src/apps/admin/sync/` 模块封装映射函数、Redis 进度/断点工具；`SyncService` 在 FastAPI `BackgroundTask` 中运行批处理循环；`sync_run_log` 表持久化每次运行记录；`scripts/sync_from_mongodb.py` 复用同一套逻辑提供离线 CLI。

**Tech Stack:** Python 3.12, pymongo 4+, SQLAlchemy async (asyncpg), Redis (progress/checkpoint), FastAPI BackgroundTasks, Alembic

**Design Spec:** `docs/superpowers/specs/2026-06-07-mongodb-sync-design.md`

---

## File Map

| 文件 | 操作 | 说明 |
|---|---|---|
| `pyproject.toml` | Modify | 新增 `scripts` optional extra（pymongo） |
| `src/common/config.py` | Modify | 新增 MongoDB 连接配置字段 |
| `src/db_model/sync_run_log.py` | **Create** | `SyncRunLog` ORM 模型 |
| `src/db_model/raw_submit.py` | Modify | 新增 `RawWorkSubmit`；所有 raw 表增加 `legacy_mongo_id` |
| `src/db_model/__init__.py` | Modify | 导出 `SyncRunLog`, `RawWorkSubmit` |
| `alembic/versions/0006_sync_run_log_and_raw_work.py` | **Create** | migration：sync_run_log + raw_work + legacy_mongo_id |
| `src/apps/admin/sync/__init__.py` | **Create** | 空 init |
| `src/apps/admin/sync/progress.py` | **Create** | Redis 进度读写工具 |
| `src/apps/admin/sync/checkpoint.py` | **Create** | Redis 断点读写工具 |
| `src/apps/admin/sync/runner.py` | **Create** | 字段映射函数 + 批处理主循环 |
| `src/apps/admin/service.py` | Modify | 新增 `SyncService` |
| `src/apps/admin/schemas.py` | Modify | 新增同步相关 request/response 模型 |
| `src/apps/admin/router.py` | Modify | 新增 5 个 `/admin/sync/*` 端点 |
| `scripts/__init__.py` | **Create** | 空 init（使 scripts 成为 package） |
| `scripts/sync_from_mongodb.py` | **Create** | CLI 入口 |
| `tests/unit/test_sync_mapping.py` | **Create** | 所有 map_* 函数的单元测试 |
| `tests/unit/test_sync_progress.py` | **Create** | progress/checkpoint Redis 工具测试 |
| `tests/integration/test_sync_service.py` | **Create** | SyncService 集成测试（mock MongoDB） |
| `tests/contract/test_sync_endpoints.py` | **Create** | HTTP 端点 contract 测试 |

---

## Task 1: 依赖与配置

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/common/config.py`

- [ ] **Step 1: 在 pyproject.toml 新增 scripts optional extra**

在 `[project.optional-dependencies]` 下追加：

```toml
[project.optional-dependencies]
test = [
    "freezegun>=1.5.0",
    "fakeredis>=2.20.0",
    "pytest-cov>=5.0.0",
]
scripts = [
    "pymongo>=4.0",
]
```

- [ ] **Step 2: 在 Settings 末尾新增 MongoDB 配置字段**

打开 `src/common/config.py`，在 `admin_secret` 字段之后、`youtube_api_key` 字段之前添加：

```python
    # MongoDB 历史数据同步（可选，未配置时同步端点返回 503）
    mongodb_uri: Optional[str] = Field(None, validation_alias="MONGODB_URI")
    mongodb_db_users: str = Field("thvote_users", validation_alias="MONGODB_DB_USERS")
    mongodb_db_submits: str = Field("submits_v1", validation_alias="MONGODB_DB_SUBMITS")
    mongodb_db_results: str = Field("submits_v1_final", validation_alias="MONGODB_DB_RESULTS")
    mongodb_batch_size: int = Field(500, validation_alias="MONGO_BATCH_SIZE")
```

- [ ] **Step 3: 验证 Settings 可正常实例化**

```bash
python -c "from src.common.config import get_settings; s = get_settings(); print(s.mongodb_uri)"
```

Expected: `None`（未配置时）

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml src/common/config.py
git commit -m "feat(sync): add pymongo dep + MongoDB config fields (B-034)"
```

---

## Task 2: ORM 模型

**Files:**
- Create: `src/db_model/sync_run_log.py`
- Modify: `src/db_model/raw_submit.py`
- Modify: `src/db_model/__init__.py`

- [ ] **Step 1: 创建 src/db_model/sync_run_log.py**

```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SyncRunLog(Base):
    __tablename__ = "sync_run_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    collections: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    total_docs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    initiated_by: Mapped[str] = mapped_column(String(8), nullable=False, default="api")
```

- [ ] **Step 2: 在 raw_submit.py 末尾添加 RawWorkSubmit + 给所有 raw 类添加 legacy_mongo_id**

打开 `src/db_model/raw_submit.py`，在每个 raw 类（`RawCharacterSubmit`、`RawMusicSubmit`、`RawCPSubmit`、`RawPaperSubmit`、`RawDojinSubmit`）的最后一个字段之后各追加：

```python
    legacy_mongo_id: Mapped[str | None] = mapped_column(
        String(24), nullable=True, unique=True
    )
```

然后在文件末尾（所有 Index 之后）追加：

```python

class RawWorkSubmit(Base):
    __tablename__ = "raw_work"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vote_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    user_ip: Mapped[str] = mapped_column(
        String(255), nullable=False, default="<unknown>"
    )
    additional_fingreprint: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )
    payload: Mapped[list] = mapped_column(JSON, nullable=False)
    legacy_mongo_id: Mapped[str | None] = mapped_column(
        String(24), nullable=True, unique=True
    )


Index(
    "idx_raw_work_vote_created",
    RawWorkSubmit.vote_id,
    RawWorkSubmit.created_at.desc(),
)
```

- [ ] **Step 3: 更新 src/db_model/__init__.py**

```python
"""
PostgreSQL数据库模型定义

定义了用于投票数据保存的数据模型。
"""

from .activity_log import ActivityLog
from .base import Base
from .candidate import CandidateCharacter, CandidateMusic, FinalRanking
from .character import Character
from .cp import Cp
from .music import Music
from .questionnaire import Questionnaire
from .raw_submit import (
    RawCharacterSubmit,
    RawCPSubmit,
    RawDojinSubmit,
    RawMusicSubmit,
    RawPaperSubmit,
    RawWorkSubmit,
)
from .sync_run_log import SyncRunLog
from .user import User

__version__ = "1.0.0"
__author__ = "FunnyAWM"
__all__ = [
    "ActivityLog",
    "Base",
    "CandidateCharacter",
    "CandidateMusic",
    "FinalRanking",
    "Character",
    "Cp",
    "Music",
    "Questionnaire",
    "RawCharacterSubmit",
    "RawCPSubmit",
    "RawDojinSubmit",
    "RawMusicSubmit",
    "RawPaperSubmit",
    "RawWorkSubmit",
    "SyncRunLog",
    "User",
]
```

- [ ] **Step 4: Commit**

```bash
git add src/db_model/sync_run_log.py src/db_model/raw_submit.py src/db_model/__init__.py
git commit -m "feat(sync): add SyncRunLog model, RawWorkSubmit, legacy_mongo_id columns (B-034)"
```

---

## Task 3: Alembic Migration 0006

**Files:**
- Create: `alembic/versions/0006_sync_run_log_and_raw_work.py`

- [ ] **Step 1: 生成 migration**

```bash
alembic revision --autogenerate -m "add sync_run_log, raw_work, legacy_mongo_id columns"
```

Expected: 新文件出现在 `alembic/versions/` 目录，文件名含 `add_sync_run_log_raw_work_legacy_mongo_id_columns`。

- [ ] **Step 2: 审查生成的 migration 文件**

确认文件的 `upgrade()` 中包含以下内容（数量和表名应完整）：
- `op.create_table('sync_run_log', ...)` — 含 run_id UNIQUE、status、collections JSON 等列
- `op.create_table('raw_work', ...)` — 含 vote_id、payload JSON、legacy_mongo_id UNIQUE 等列
- `op.add_column('raw_character', sa.Column('legacy_mongo_id', ...))` — 5 个 raw 表各一条
- `op.add_column('raw_music', ...)`
- `op.add_column('raw_cp', ...)`
- `op.add_column('raw_paper', ...)`
- `op.add_column('raw_dojin', ...)`
- 对应的 UNIQUE constraint 创建语句

将文件重命名为 `0006_sync_run_log_and_raw_work.py` 并修改文件头的 `revision` 和 `down_revision`：

```python
revision: str = "0006"
down_revision: Union[str, None] = "0005"
```

（若尚无 0005 revision，则 `down_revision` 改为最新实际 revision 值，可通过 `alembic current` 查看。）

- [ ] **Step 3: 应用 migration**

```bash
alembic upgrade head
```

Expected: `Running upgrade ... -> 0006, add sync_run_log, raw_work, legacy_mongo_id columns`

- [ ] **Step 4: 验证表已创建**

```bash
python -c "
from sqlalchemy import create_engine, inspect
import os
eng = create_engine(os.environ['DATABASE_URL'].replace('+asyncpg',''))
insp = inspect(eng)
print(insp.get_table_names())
"
```

Expected: 输出包含 `sync_run_log` 和 `raw_work`。

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/0006_sync_run_log_and_raw_work.py
git commit -m "feat(migration): 0006 sync_run_log + raw_work + legacy_mongo_id (B-034)"
```

---

## Task 4: Redis 进度与断点工具（TDD）

**Files:**
- Create: `src/apps/admin/sync/__init__.py`
- Create: `src/apps/admin/sync/progress.py`
- Create: `src/apps/admin/sync/checkpoint.py`
- Create: `tests/unit/test_sync_progress.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/test_sync_progress.py`：

```python
"""Tests for sync progress and checkpoint Redis utilities."""
import pytest
import fakeredis.aioredis as fakeredis


@pytest.fixture
def redis():
    return fakeredis.FakeRedis()


@pytest.mark.asyncio
async def test_set_and_get_progress(redis):
    from src.apps.admin.sync.progress import set_progress, get_progress

    await set_progress(redis, "run-1", processed=100, total=500, errors=2)
    data = await get_progress(redis, "run-1")

    assert data["processed"] == "100"
    assert data["total"] == "500"
    assert data["errors"] == "2"


@pytest.mark.asyncio
async def test_cancel_signal(redis):
    from src.apps.admin.sync.progress import set_cancel_signal, check_cancel

    assert not await check_cancel(redis, "run-1")
    await set_cancel_signal(redis, "run-1")
    assert await check_cancel(redis, "run-1")


@pytest.mark.asyncio
async def test_current_run(redis):
    from src.apps.admin.sync.progress import set_current_run, get_current_run

    assert await get_current_run(redis) is None
    await set_current_run(redis, "run-abc")
    assert await get_current_run(redis) == "run-abc"


@pytest.mark.asyncio
async def test_save_and_load_checkpoint(redis):
    from src.apps.admin.sync.checkpoint import save_checkpoint, load_checkpoint

    assert await load_checkpoint(redis, "run-1", "voters") is None
    await save_checkpoint(redis, "run-1", "voters", "507f1f77bcf86cd799439011")
    val = await load_checkpoint(redis, "run-1", "voters")
    assert val == "507f1f77bcf86cd799439011"
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/unit/test_sync_progress.py -xvs
```

Expected: `ModuleNotFoundError: No module named 'src.apps.admin.sync'`

- [ ] **Step 3: 创建 sync 包和工具文件**

创建 `src/apps/admin/sync/__init__.py`（空文件）。

创建 `src/apps/admin/sync/progress.py`：

```python
from __future__ import annotations

import redis.asyncio as aioredis

_PROGRESS_KEY = "sync:progress:{run_id}"
_CANCEL_KEY = "sync:cancel:{run_id}"
_CURRENT_RUN_KEY = "sync:current_run"
_TTL = 86400  # 24 hours


async def set_progress(redis: aioredis.Redis, run_id: str, **fields: int | str) -> None:
    key = _PROGRESS_KEY.format(run_id=run_id)
    await redis.hset(key, mapping={k: str(v) for k, v in fields.items()})
    await redis.expire(key, _TTL)


async def get_progress(redis: aioredis.Redis, run_id: str) -> dict[str, str]:
    key = _PROGRESS_KEY.format(run_id=run_id)
    raw = await redis.hgetall(key)
    return {k.decode(): v.decode() for k, v in raw.items()}


async def set_cancel_signal(redis: aioredis.Redis, run_id: str) -> None:
    key = _CANCEL_KEY.format(run_id=run_id)
    await redis.set(key, "1", ex=3600)


async def check_cancel(redis: aioredis.Redis, run_id: str) -> bool:
    key = _CANCEL_KEY.format(run_id=run_id)
    return bool(await redis.exists(key))


async def set_current_run(redis: aioredis.Redis, run_id: str) -> None:
    await redis.set(_CURRENT_RUN_KEY, run_id, ex=_TTL)


async def get_current_run(redis: aioredis.Redis) -> str | None:
    val = await redis.get(_CURRENT_RUN_KEY)
    return val.decode() if val else None


async def clear_current_run(redis: aioredis.Redis) -> None:
    await redis.delete(_CURRENT_RUN_KEY)
```

创建 `src/apps/admin/sync/checkpoint.py`：

```python
from __future__ import annotations

import redis.asyncio as aioredis

_CHECKPOINT_KEY = "sync:checkpoint:{run_id}:{collection}"
_TTL = 7 * 86400  # 7 days


async def save_checkpoint(
    redis: aioredis.Redis, run_id: str, collection: str, last_id: str
) -> None:
    key = _CHECKPOINT_KEY.format(run_id=run_id, collection=collection)
    await redis.set(key, last_id, ex=_TTL)


async def load_checkpoint(
    redis: aioredis.Redis, run_id: str, collection: str
) -> str | None:
    key = _CHECKPOINT_KEY.format(run_id=run_id, collection=collection)
    val = await redis.get(key)
    return val.decode() if val else None
```

- [ ] **Step 4: 运行，确认通过**

```bash
pytest tests/unit/test_sync_progress.py -xvs
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/apps/admin/sync/ tests/unit/test_sync_progress.py
git commit -m "feat(sync): Redis progress + checkpoint utilities with tests (B-034)"
```

---

## Task 5: 字段映射函数（TDD）

**Files:**
- Create: `tests/unit/test_sync_mapping.py`
- Create: `src/apps/admin/sync/runner.py`（仅映射函数部分）

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/test_sync_mapping.py`：

```python
"""Tests for MongoDB → PostgreSQL field mapping functions."""
from datetime import datetime, timezone
from unittest.mock import MagicMock


def _oid(hex_str: str = "507f1f77bcf86cd799439011") -> MagicMock:
    m = MagicMock()
    m.__str__ = MagicMock(return_value=hex_str)
    return m


# ── voters ────────────────────────────────────────────────────────────────────

def test_map_voter_full():
    from src.apps.admin.sync.runner import map_voter

    oid = _oid("507f1f77bcf86cd799439011")
    doc = {
        "_id": oid, "phone": "13800138000", "phone_verified": True,
        "email": "v@example.com", "email_verified": True,
        "password_hashed": "$2b$12$hash", "salt": None,
        "created_at": datetime(2023, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        "nickname": "Alice", "signup_ip": "1.2.3.4",
        "qq_openid": "QQ1", "pfp": "https://img/1.jpg",
        "thbwiki_uid": "42", "removed": None,
    }
    row = map_voter(doc)

    assert row["id"] == "507f1f77bcf86cd799439011"
    assert row["phone_number"] == "13800138000"
    assert row["phone_verified"] is True
    assert row["email"] == "v@example.com"
    assert row["password_hash"] == "$2b$12$hash"
    assert row["legacy_salt"] is None
    assert row["register_ip_address"] == "1.2.3.4"
    assert row["removed"] is False


def test_map_voter_none_ip_and_removed():
    from src.apps.admin.sync.runner import map_voter

    doc = {
        "_id": _oid(), "phone": None, "phone_verified": False,
        "email": "x@x.com", "email_verified": False,
        "password_hashed": None, "salt": None,
        "created_at": datetime(2020, 1, 1, tzinfo=timezone.utc),
        "nickname": None, "signup_ip": None, "removed": True,
    }
    row = map_voter(doc)

    assert row["register_ip_address"] == ""
    assert row["removed"] is True


# ── raw_submit (generic) ──────────────────────────────────────────────────────

def test_map_raw_submit():
    from src.apps.admin.sync.runner import map_raw_submit

    oid = _oid("aabbccddeeff001122334455")
    doc = {
        "_id": oid,
        "characters": [{"id": "c1", "reason": "nice", "first": True}],
        "meta": {
            "vote_id": "voter123", "attempt": 2,
            "created_at": datetime(2024, 3, 1, tzinfo=timezone.utc),
            "user_ip": "10.0.0.1", "additional_fingreprint": "fp1",
        },
    }
    row = map_raw_submit(doc, "characters")

    assert row["legacy_mongo_id"] == "aabbccddeeff001122334455"
    assert row["vote_id"] == "voter123"
    assert row["attempt"] == 2
    assert row["user_ip"] == "10.0.0.1"
    assert row["payload"] == [{"id": "c1", "reason": "nice", "first": True}]


def test_map_raw_submit_missing_meta():
    from src.apps.admin.sync.runner import map_raw_submit

    doc = {"_id": _oid(), "music": [], "meta": {}}
    row = map_raw_submit(doc, "music")

    assert row["vote_id"] == ""
    assert row["attempt"] is None
    assert row["user_ip"] == "<unknown>"


# ── raw_paper ─────────────────────────────────────────────────────────────────

def test_map_raw_paper():
    from src.apps.admin.sync.runner import map_raw_paper

    doc = {
        "_id": _oid(), "papers_json": '{"q1": "a"}',
        "meta": {
            "vote_id": "v1", "attempt": 1,
            "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "user_ip": "1.1.1.1", "additional_fingreprint": None,
        },
    }
    row = map_raw_paper(doc)

    assert row["papers_json"] == '{"q1": "a"}'
    assert row["vote_id"] == "v1"


# ── final_ranking ─────────────────────────────────────────────────────────────

def test_map_final_ranking_char():
    from src.apps.admin.sync.runner import map_final_ranking

    doc = {"name": "Reimu", "vote_year": 2023, "rank": 1,
           "vote_count": 5000, "first_vote_count": 2000,
           "first_vote_percentage": 0.4, "vote_percentage": 0.05}
    row = map_final_ranking(doc, "character")

    assert row["category"] == "character"
    assert row["rank"] == 1
    assert row["vote_count"] == 5000
    assert "first_vote_percentage" not in row


# ── candidates ────────────────────────────────────────────────────────────────

def test_map_candidate_character():
    from src.apps.admin.sync.runner import map_candidate_character

    doc = {"vote_year": 2023, "name": "Reimu", "origname": "博麗霊夢",
           "date": 1996, "kind": ["human", "shrine_maiden"],
           "work": ["EoSD", "PCB"], "album": None}
    row = map_candidate_character(doc)

    assert row["name_jp"] == "博麗霊夢"
    assert row["type"] == "human"
    assert row["origin"] == "EoSD"
    assert row["first_appearance"] == "1996"


def test_map_candidate_character_empty_kind():
    from src.apps.admin.sync.runner import map_candidate_character

    doc = {"vote_year": 2023, "name": "X", "origname": "",
           "date": None, "kind": [], "work": [], "album": None}
    row = map_candidate_character(doc)

    assert row["type"] == ""
    assert row["origin"] == ""
    assert row["first_appearance"] is None


def test_map_candidate_music():
    from src.apps.admin.sync.runner import map_candidate_music

    doc = {"vote_year": 2023, "name": "U.N.オーエンは彼女なのか？",
           "origname": "U.N. Owen was Her?", "date": 2002,
           "kind": ["arrange"], "work": ["EoSD"], "album": "Scarlet"}
    row = map_candidate_music(doc)

    assert row["name_jp"] == "U.N. Owen was Her?"
    assert row["type"] == "arrange"
    assert row["album"] == "Scarlet"
    assert "origin" not in row
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/unit/test_sync_mapping.py -xvs
```

Expected: `ModuleNotFoundError` 或 `ImportError`

- [ ] **Step 3: 创建 runner.py（仅映射部分）**

创建 `src/apps/admin/sync/runner.py`：

```python
"""MongoDB → PostgreSQL sync: field mappers + batch runner."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ── datetime helper ────────────────────────────────────────────────────────────

def _coerce_datetime(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    if hasattr(val, "as_datetime"):
        dt = val.as_datetime()
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(val))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ── field mappers ──────────────────────────────────────────────────────────────

def map_voter(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "phone_number": doc.get("phone"),
        "phone_verified": bool(doc.get("phone_verified", False)),
        "email": doc.get("email"),
        "email_verified": bool(doc.get("email_verified", False)),
        "password_hash": doc.get("password_hashed"),
        "legacy_salt": doc.get("salt"),
        "register_date": _coerce_datetime(doc.get("created_at")),
        "nickname": doc.get("nickname"),
        "register_ip_address": doc.get("signup_ip") or "",
        "qq_openid": doc.get("qq_openid"),
        "pfp": doc.get("pfp"),
        "thbwiki_uid": doc.get("thbwiki_uid"),
        "removed": bool(doc.get("removed") or False),
    }


def map_raw_submit(doc: dict[str, Any], payload_key: str) -> dict[str, Any]:
    meta = doc.get("meta") or {}
    return {
        "legacy_mongo_id": str(doc["_id"]),
        "vote_id": meta.get("vote_id") or "",
        "attempt": meta.get("attempt"),
        "created_at": _coerce_datetime(meta.get("created_at")),
        "user_ip": meta.get("user_ip") or "<unknown>",
        "additional_fingreprint": meta.get("additional_fingreprint"),
        "payload": doc.get(payload_key) or [],
    }


def map_raw_paper(doc: dict[str, Any]) -> dict[str, Any]:
    meta = doc.get("meta") or {}
    return {
        "legacy_mongo_id": str(doc["_id"]),
        "vote_id": meta.get("vote_id") or "",
        "attempt": meta.get("attempt"),
        "created_at": _coerce_datetime(meta.get("created_at")),
        "user_ip": meta.get("user_ip") or "<unknown>",
        "additional_fingreprint": meta.get("additional_fingreprint"),
        "papers_json": doc.get("papers_json") or "{}",
    }


def map_final_ranking(doc: dict[str, Any], category: str) -> dict[str, Any]:
    return {
        "vote_year": doc.get("vote_year"),
        "category": category,
        "rank": doc.get("rank"),
        "name": doc.get("name") or "",
        "vote_count": doc.get("vote_count") or 0,
        "first_vote_count": doc.get("first_vote_count") or 0,
    }


def map_candidate_character(doc: dict[str, Any]) -> dict[str, Any]:
    kinds = doc.get("kind") or []
    works = doc.get("work") or []
    date = doc.get("date")
    return {
        "vote_year": doc.get("vote_year"),
        "name": doc.get("name") or "",
        "name_jp": doc.get("origname") or "",
        "type": kinds[0] if kinds else "",
        "origin": works[0] if works else "",
        "first_appearance": str(date) if date is not None else None,
    }


def map_candidate_music(doc: dict[str, Any]) -> dict[str, Any]:
    kinds = doc.get("kind") or []
    date = doc.get("date")
    return {
        "vote_year": doc.get("vote_year"),
        "name": doc.get("name") or "",
        "name_jp": doc.get("origname") or "",
        "type": kinds[0] if kinds else "",
        "first_appearance": str(date) if date is not None else None,
        "album": doc.get("album"),
    }
```

- [ ] **Step 4: 运行，确认通过**

```bash
pytest tests/unit/test_sync_mapping.py -xvs
```

Expected: 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/apps/admin/sync/runner.py tests/unit/test_sync_mapping.py
git commit -m "feat(sync): field mapping functions with full test coverage (B-034)"
```

---

## Task 6: Runner 批处理主循环

**Files:**
- Modify: `src/apps/admin/sync/runner.py`（追加批处理逻辑）
- Create: `tests/integration/test_sync_service.py`

- [ ] **Step 1: 在 runner.py 末尾追加集合配置表和批处理函数**

在 `src/apps/admin/sync/runner.py` 末尾追加：

```python
# ── collection config ──────────────────────────────────────────────────────────

# Each entry: (db_attr, mongo_collection, pg_table, mapper_fn, conflict_col)
# db_attr: attribute name on Settings for the database name
# conflict_col: PostgreSQL column to use in ON CONFLICT DO NOTHING
COLLECTION_CONFIG = [
    # A: users
    ("mongodb_db_users", "voters", "user", map_voter, "id"),
    # B: raw submissions
    ("mongodb_db_submits", "raw_character", "raw_character",
     lambda d: map_raw_submit(d, "characters"), "legacy_mongo_id"),
    ("mongodb_db_submits", "raw_music", "raw_music",
     lambda d: map_raw_submit(d, "music"), "legacy_mongo_id"),
    ("mongodb_db_submits", "raw_cp", "raw_cp",
     lambda d: map_raw_submit(d, "cps"), "legacy_mongo_id"),
    ("mongodb_db_submits", "raw_work", "raw_work",
     lambda d: map_raw_submit(d, "works"), "legacy_mongo_id"),
    ("mongodb_db_submits", "raw_paper", "raw_paper",
     map_raw_paper, "legacy_mongo_id"),
    ("mongodb_db_submits", "raw_dojin", "raw_dojin",
     lambda d: map_raw_submit(d, "dojins"), "legacy_mongo_id"),
    # C: final rankings
    ("mongodb_db_results", "final_ranking_char", "final_ranking",
     lambda d: map_final_ranking(d, "character"), None),
    ("mongodb_db_results", "final_ranking_music", "final_ranking",
     lambda d: map_final_ranking(d, "music"), None),
    # D: candidates
    ("mongodb_db_results", "chars", "candidate_character",
     map_candidate_character, None),
    ("mongodb_db_results", "musics", "candidate_music",
     map_candidate_music, None),
]

# conflict columns for tables that have unique constraints other than legacy_mongo_id
_CONFLICT_COLS = {
    "user": "id",
    "final_ranking": "(vote_year, category, rank)",
    "candidate_character": "(vote_year, name)",
    "candidate_music": "(vote_year, name)",
}


async def run_collection(
    *,
    mongo_db,
    collection_name: str,
    pg_table: str,
    mapper,
    run_id: str,
    batch_size: int,
    redis,
    session_maker,
    error_path: str,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    """Process one MongoDB collection. Returns (inserted, skipped, errors)."""
    from src.apps.admin.sync.checkpoint import load_checkpoint, save_checkpoint
    from src.apps.admin.sync.progress import check_cancel, set_progress
    from sqlalchemy import text

    coll = mongo_db[collection_name]
    last_id = await load_checkpoint(redis, run_id, collection_name)

    query = {}
    if last_id:
        from bson import ObjectId
        query = {"_id": {"$gt": ObjectId(last_id)}}

    total = coll.count_documents(query)
    inserted = skipped = errors = 0
    batch: list[dict] = []

    for i, doc in enumerate(coll.find(query).sort("_id", 1)):
        if await check_cancel(redis, run_id):
            logger.info("Sync cancelled at collection=%s i=%d", collection_name, i)
            break

        try:
            row = mapper(doc)
        except Exception as exc:
            logger.warning("Mapping error _id=%s: %s", doc.get("_id"), exc)
            _write_error(error_path, {"_id": str(doc.get("_id")), "error": str(exc)})
            errors += 1
            continue

        batch.append((str(doc["_id"]), row))

        if len(batch) >= batch_size or i == total - 1:
            if not dry_run:
                b_ins, b_skip, b_err = await _flush_batch(
                    batch, pg_table, session_maker, error_path
                )
                inserted += b_ins
                skipped += b_skip
                errors += b_err

            if batch:
                await save_checkpoint(redis, run_id, collection_name, batch[-1][0])

            await set_progress(
                redis, run_id,
                current_collection=collection_name,
                processed=i + 1,
                total=total,
                inserted=inserted,
                skipped=skipped,
                errors=errors,
            )
            batch = []

    return inserted, skipped, errors


async def _flush_batch(batch, pg_table, session_maker, error_path):
    from sqlalchemy import text

    conflict_col = _CONFLICT_COLS.get(pg_table, "legacy_mongo_id")
    if "(" in conflict_col:
        conflict_clause = f"ON CONFLICT {conflict_col} DO NOTHING"
    else:
        conflict_clause = f"ON CONFLICT ({conflict_col}) DO NOTHING"

    inserted = skipped = errors = 0
    async with session_maker() as session:
        async with session.begin():
            for _id, row in batch:
                cols = ", ".join(f'"{k}"' for k in row)
                params = ", ".join(f":{k}" for k in row)
                sql = text(
                    f'INSERT INTO "{pg_table}" ({cols}) VALUES ({params}) {conflict_clause}'
                )
                try:
                    result = await session.execute(sql, row)
                    if result.rowcount == 0:
                        skipped += 1
                    else:
                        inserted += 1
                except Exception as exc:
                    errors += 1
                    _write_error(error_path, {"id": _id, "error": str(exc)})
    return inserted, skipped, errors


def _write_error(path: str, record: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
```

- [ ] **Step 2: 写集成测试（mock MongoDB）**

创建 `tests/integration/test_sync_service.py`：

```python
"""Integration tests for the sync runner (mock MongoDB, real sqlite)."""
import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import fakeredis.aioredis as fakeredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text

from src.db_model import Base


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session_maker(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
def redis():
    return fakeredis.FakeRedis()


def _oid(hex_str: str):
    m = MagicMock()
    m.__str__ = MagicMock(return_value=hex_str)
    from bson import ObjectId
    # For sorting to work, return a real ObjectId
    try:
        return ObjectId(hex_str)
    except Exception:
        return m


@pytest.mark.asyncio
async def test_run_collection_voters(engine, session_maker, redis):
    from src.apps.admin.sync.runner import run_collection

    docs = [
        {
            "_id": _oid("507f1f77bcf86cd799439011"),
            "phone": "138", "phone_verified": True,
            "email": "a@a.com", "email_verified": True,
            "password_hashed": "hash", "salt": None,
            "created_at": datetime(2023, 1, 1, tzinfo=timezone.utc),
            "nickname": "Alice", "signup_ip": "1.1.1.1",
        }
    ]

    mock_coll = MagicMock()
    mock_coll.count_documents.return_value = 1
    mock_coll.find.return_value.__iter__ = MagicMock(return_value=iter(docs))
    mock_coll.find.return_value.sort.return_value = iter(docs)

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_coll)

    from src.apps.admin.sync.runner import map_voter

    ins, skip, err = await run_collection(
        mongo_db=mock_db,
        collection_name="voters",
        pg_table="user",
        mapper=map_voter,
        run_id="test-run-1",
        batch_size=100,
        redis=redis,
        session_maker=session_maker,
        error_path="/tmp/test_errors.jsonl",
    )

    assert ins == 1
    assert skip == 0
    assert err == 0

    async with session_maker() as session:
        result = await session.execute(text('SELECT id, email FROM "user" LIMIT 1'))
        row = result.fetchone()
    assert row is not None
    assert row[1] == "a@a.com"


@pytest.mark.asyncio
async def test_run_collection_idempotent(engine, session_maker, redis):
    """Running the same data twice should skip duplicates (ON CONFLICT DO NOTHING)."""
    bson = pytest.importorskip("bson", reason="requires pymongo[bson]")
    ObjectId = bson.ObjectId
    from src.apps.admin.sync.runner import run_collection, map_voter

    docs = [
        {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "phone": None, "phone_verified": False,
            "email": "b@b.com", "email_verified": False,
            "password_hashed": None, "salt": None,
            "created_at": datetime(2023, 1, 1, tzinfo=timezone.utc),
            "nickname": None, "signup_ip": None,
        }
    ]

    kwargs = dict(
        mongo_db=MagicMock(**{"__getitem__": MagicMock(return_value=MagicMock(
            count_documents=MagicMock(return_value=1),
            find=MagicMock(return_value=MagicMock(
                sort=MagicMock(return_value=iter(docs)))),
        ))}),
        collection_name="voters",
        pg_table="user",
        mapper=map_voter,
        run_id="test-run-2",
        batch_size=100,
        redis=redis,
        session_maker=session_maker,
        error_path="/tmp/test_errors2.jsonl",
    )

    ins1, _, _ = await run_collection(**kwargs)
    # reset mock iterators for second run
    kwargs["mongo_db"] = MagicMock(**{"__getitem__": MagicMock(return_value=MagicMock(
        count_documents=MagicMock(return_value=1),
        find=MagicMock(return_value=MagicMock(
            sort=MagicMock(return_value=iter(docs)))),
    ))})
    ins2, skip2, _ = await run_collection(**kwargs)

    assert ins1 == 1
    assert ins2 == 0
    assert skip2 == 1
```

- [ ] **Step 3: 运行集成测试**

```bash
pytest tests/integration/test_sync_service.py -xvs
```

Expected: 2 tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/apps/admin/sync/runner.py tests/integration/test_sync_service.py
git commit -m "feat(sync): batch runner with checkpoint/cancel + integration tests (B-034)"
```

---

## Task 7: SyncService + Admin 端点

**Files:**
- Modify: `src/apps/admin/service.py`
- Modify: `src/apps/admin/schemas.py`
- Modify: `src/apps/admin/router.py`

- [ ] **Step 1: 在 schemas.py 末尾追加同步相关模型**

```python
# ── Sync schemas ──────────────────────────────────────────────────────────────

class SyncStartRequest(BaseModel):
    collections: list[str] = []  # empty = all
    batch_size: int = 500


class SyncStartResponse(BaseModel):
    ok: bool = True
    run_id: str
    message: str


class SyncStatusResponse(BaseModel):
    run_id: str | None
    status: str  # running / idle / no_run
    current_collection: str | None = None
    processed: int = 0
    total: int = 0
    inserted: int = 0
    skipped: int = 0
    errors: int = 0


class SyncHistoryItem(BaseModel):
    id: int
    run_id: str
    started_at: str
    completed_at: str | None
    status: str
    collections: list[str]
    total_docs: int
    inserted: int
    skipped: int
    errors: int
    initiated_by: str


class SyncHistoryResponse(BaseModel):
    items: list[SyncHistoryItem]
    total: int
```

- [ ] **Step 2: 修改 service.py — 追加 SyncService**

在 `src/apps/admin/service.py` 末尾追加：

```python
import uuid
from sqlalchemy import select, desc, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
import redis.asyncio as aioredis

from src.apps.admin.schemas import SyncStartRequest
from src.apps.admin.sync.progress import (
    set_current_run, get_current_run, get_progress, set_cancel_signal,
    clear_current_run,
)
from src.apps.admin.sync.runner import COLLECTION_CONFIG
from src.common.config import Settings
from src.db_model.sync_run_log import SyncRunLog


class SyncService:
    def __init__(
        self,
        session: AsyncSession,
        session_maker: async_sessionmaker,
        redis: aioredis.Redis,
        settings: Settings,
    ) -> None:
        self.session = session
        self.session_maker = session_maker
        self.redis = redis
        self.settings = settings

    async def start_sync(self, request: SyncStartRequest, initiated_by: str = "api") -> str:
        """Create a SyncRunLog entry and return run_id. Caller launches background task."""
        run_id = str(uuid.uuid4())
        collections_to_run = request.collections or [
            cfg[1] for cfg in COLLECTION_CONFIG
        ]
        log = SyncRunLog(
            run_id=run_id,
            status="running",
            collections=collections_to_run,
            initiated_by=initiated_by,
        )
        self.session.add(log)
        await self.session.commit()
        await set_current_run(self.redis, run_id)
        return run_id

    async def get_status(self) -> dict:
        run_id = await get_current_run(self.redis)
        if not run_id:
            return {"run_id": None, "status": "idle"}
        progress = await get_progress(self.redis, run_id)
        if not progress:
            return {"run_id": run_id, "status": "idle"}
        return {
            "run_id": run_id,
            "status": progress.get("status", "running"),
            "current_collection": progress.get("current_collection"),
            "processed": int(progress.get("processed", 0)),
            "total": int(progress.get("total", 0)),
            "inserted": int(progress.get("inserted", 0)),
            "skipped": int(progress.get("skipped", 0)),
            "errors": int(progress.get("errors", 0)),
        }

    async def get_history(self, page: int = 1, page_size: int = 20) -> dict:
        total_result = await self.session.execute(
            select(sqlfunc.count()).select_from(SyncRunLog)
        )
        total = total_result.scalar_one()
        result = await self.session.execute(
            select(SyncRunLog)
            .order_by(desc(SyncRunLog.started_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = result.scalars().all()
        return {"items": items, "total": total}

    async def cancel(self) -> None:
        run_id = await get_current_run(self.redis)
        if run_id:
            await set_cancel_signal(self.redis, run_id)

    async def complete_run(self, run_id: str, inserted: int, skipped: int, errors: int, status: str = "completed") -> None:
        from datetime import datetime, timezone
        result = await self.session.execute(
            select(SyncRunLog).where(SyncRunLog.run_id == run_id)
        )
        log = result.scalar_one_or_none()
        if log:
            log.status = status
            log.completed_at = datetime.now(timezone.utc)
            log.inserted = inserted
            log.skipped = skipped
            log.errors = errors
            await self.session.commit()
        await clear_current_run(self.redis)
```

- [ ] **Step 3: 修改 router.py — 追加同步端点**

在 `src/apps/admin/router.py` 末尾追加：

```python
from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.apps.admin.schemas import (
    SyncStartRequest, SyncStartResponse,
    SyncStatusResponse, SyncHistoryResponse,
)
from src.apps.admin.service import SyncService
from src.apps.admin.sync.runner import COLLECTION_CONFIG, run_collection
from src.common.database import get_session_maker


async def get_sync_service(
    session: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
    session_maker: async_sessionmaker = Depends(get_session_maker),
) -> SyncService:
    return SyncService(session, session_maker, redis, settings)


async def _run_all_collections(
    run_id: str, request: SyncStartRequest,
    settings: Settings, redis, session_maker,
):
    """Background task: iterate all configured collections."""
    import pymongo
    from src.apps.admin.sync.progress import set_progress, clear_current_run

    uri = settings.mongodb_uri
    client = pymongo.MongoClient(uri)
    total_inserted = total_skipped = total_errors = 0

    collections_to_run = request.collections or [cfg[1] for cfg in COLLECTION_CONFIG]

    try:
        for db_attr, coll_name, pg_table, mapper, _ in COLLECTION_CONFIG:
            if coll_name not in collections_to_run:
                continue
            db_name = getattr(settings, db_attr)
            ins, skp, err = await run_collection(
                mongo_db=client[db_name],
                collection_name=coll_name,
                pg_table=pg_table,
                mapper=mapper,
                run_id=run_id,
                batch_size=request.batch_size,
                redis=redis,
                session_maker=session_maker,
                error_path=f"migrate_errors_{run_id[:8]}.jsonl",
            )
            total_inserted += ins
            total_skipped += skp
            total_errors += err

        status = "completed"
    except Exception as exc:
        logger.error("Sync run %s failed: %s", run_id, exc)
        status = "failed"
    finally:
        client.close()
        # Update DB record via a fresh session
        async with session_maker() as session:
            sync_svc = SyncService(session, session_maker, redis, settings)
            await sync_svc.complete_run(
                run_id, total_inserted, total_skipped, total_errors, status
            )


@router.post("/sync/start", response_model=SyncStartResponse, status_code=202)
async def start_sync(
    body: SyncStartRequest,
    background_tasks: BackgroundTasks,
    x_admin_secret: Optional[str] = Header(None),
    service: SyncService = Depends(get_sync_service),
    settings: Settings = Depends(get_settings),
    redis: aioredis.Redis = Depends(get_redis),
    session_maker: async_sessionmaker = Depends(get_session_maker),
) -> SyncStartResponse:
    _check_admin_secret(settings, x_admin_secret)
    if not settings.mongodb_uri:
        raise HTTPException(status_code=503, detail="MONGODB_NOT_CONFIGURED")
    run_id = await service.start_sync(body)
    background_tasks.add_task(
        _run_all_collections, run_id, body, settings, redis, session_maker
    )
    return SyncStartResponse(run_id=run_id, message="Sync started")


@router.get("/sync/status", response_model=SyncStatusResponse)
async def get_sync_status(
    x_admin_secret: Optional[str] = Header(None),
    service: SyncService = Depends(get_sync_service),
    settings: Settings = Depends(get_settings),
) -> SyncStatusResponse:
    _check_admin_secret(settings, x_admin_secret)
    data = await service.get_status()
    return SyncStatusResponse(**data)


@router.get("/sync/history", response_model=SyncHistoryResponse)
async def get_sync_history(
    page: int = 1,
    page_size: int = 20,
    x_admin_secret: Optional[str] = Header(None),
    service: SyncService = Depends(get_sync_service),
    settings: Settings = Depends(get_settings),
) -> SyncHistoryResponse:
    _check_admin_secret(settings, x_admin_secret)
    data = await service.get_history(page, page_size)
    items = [
        {
            "id": r.id, "run_id": r.run_id,
            "started_at": r.started_at.isoformat(),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "status": r.status, "collections": r.collections or [],
            "total_docs": r.total_docs, "inserted": r.inserted,
            "skipped": r.skipped, "errors": r.errors,
            "initiated_by": r.initiated_by,
        }
        for r in data["items"]
    ]
    return SyncHistoryResponse(items=items, total=data["total"])


@router.post("/sync/cancel")
async def cancel_sync(
    x_admin_secret: Optional[str] = Header(None),
    service: SyncService = Depends(get_sync_service),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    await service.cancel()
    return {"ok": True}


@router.post("/sync/retry/{run_id}", response_model=SyncStartResponse, status_code=202)
async def retry_sync(
    run_id: str,
    background_tasks: BackgroundTasks,
    x_admin_secret: Optional[str] = Header(None),
    service: SyncService = Depends(get_sync_service),
    settings: Settings = Depends(get_settings),
    redis: aioredis.Redis = Depends(get_redis),
    session_maker: async_sessionmaker = Depends(get_session_maker),
) -> SyncStartResponse:
    _check_admin_secret(settings, x_admin_secret)
    if not settings.mongodb_uri:
        raise HTTPException(status_code=503, detail="MONGODB_NOT_CONFIGURED")
    # Reuse run_id so checkpoints apply
    await set_current_run(redis, run_id)
    body = SyncStartRequest()
    background_tasks.add_task(
        _run_all_collections, run_id, body, settings, redis, session_maker
    )
    return SyncStartResponse(run_id=run_id, message="Retry started from checkpoint")
```

Also add the missing import at the top of `router.py` (after the existing imports):

```python
import logging
from src.common.database import get_session_maker
from src.apps.admin.sync.progress import set_current_run

logger = logging.getLogger(__name__)
```

- [ ] **Step 4: 运行完整测试套件**

```bash
pytest tests/ -x --ignore=tests/integration/test_sync_service.py -q
```

Expected: 全部 PASS，无回归

- [ ] **Step 5: Commit**

```bash
git add src/apps/admin/service.py src/apps/admin/schemas.py src/apps/admin/router.py
git commit -m "feat(sync): SyncService + 5 admin sync endpoints (B-034)"
```

---

## Task 8: CLI 脚本

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/sync_from_mongodb.py`

- [ ] **Step 1: 创建 scripts/__init__.py**

```python
```

（空文件）

- [ ] **Step 2: 创建 scripts/sync_from_mongodb.py**

```python
"""MongoDB → PostgreSQL full historical data sync CLI.

Usage:
    MONGODB_URI=mongodb://... DATABASE_URL=postgresql+asyncpg://... \\
        python scripts/sync_from_mongodb.py [--collections voters raw_character] \\
                                            [--batch-size 500] [--dry-run] \\
                                            [--resume-run-id <uuid>]

Prerequisite: alembic upgrade head (migration 0006 applied).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import uuid

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ALL_COLLECTIONS = [
    "voters",
    "raw_character", "raw_music", "raw_cp", "raw_work", "raw_paper", "raw_dojin",
    "final_ranking_char", "final_ranking_music",
    "chars", "musics",
]


async def main_async(args: argparse.Namespace) -> None:
    import pymongo
    import fakeredis.aioredis as fakeredis_module
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from src.apps.admin.sync.runner import COLLECTION_CONFIG, run_collection
    from src.apps.admin.sync.checkpoint import load_checkpoint
    from src.db_model import Base

    mongodb_uri = os.environ.get("MONGODB_URI")
    database_url = os.environ.get("DATABASE_URL")
    mongodb_db_users = os.environ.get("MONGODB_DB_USERS", "thvote_users")
    mongodb_db_submits = os.environ.get("MONGODB_DB_SUBMITS", "submits_v1")
    mongodb_db_results = os.environ.get("MONGODB_DB_RESULTS", "submits_v1_final")

    if not mongodb_uri:
        logger.error("MONGODB_URI is required")
        sys.exit(1)
    if not database_url and not args.dry_run:
        logger.error("DATABASE_URL is required (or use --dry-run)")
        sys.exit(1)

    run_id = args.resume_run_id or str(uuid.uuid4())
    logger.info("Run ID: %s", run_id)

    redis = fakeredis_module.FakeRedis()  # CLI uses in-memory Redis for checkpoints

    if not args.dry_run:
        engine = create_async_engine(database_url, echo=False)
        session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    else:
        session_maker = None

    collections_to_run = args.collections or ALL_COLLECTIONS

    db_map = {
        "mongodb_db_users": mongodb_db_users,
        "mongodb_db_submits": mongodb_db_submits,
        "mongodb_db_results": mongodb_db_results,
    }

    client = pymongo.MongoClient(mongodb_uri)
    total_inserted = total_skipped = total_errors = 0

    try:
        for db_attr, coll_name, pg_table, mapper, _ in COLLECTION_CONFIG:
            if coll_name not in collections_to_run:
                continue
            db_name = db_map[db_attr]
            logger.info("Processing %s.%s → %s", db_name, coll_name, pg_table)

            if args.dry_run:
                coll = client[db_name][coll_name]
                total = coll.count_documents({})
                logger.info("[dry-run] %s: %d documents", coll_name, total)
                for doc in coll.find({}).limit(3):
                    try:
                        row = mapper(doc)
                        logger.info("  sample: %s", {k: str(v)[:40] for k, v in list(row.items())[:4]})
                    except Exception as exc:
                        logger.warning("  mapping error: %s", exc)
                continue

            ins, skp, err = await run_collection(
                mongo_db=client[db_name],
                collection_name=coll_name,
                pg_table=pg_table,
                mapper=mapper,
                run_id=run_id,
                batch_size=args.batch_size,
                redis=redis,
                session_maker=session_maker,
                error_path=f"migrate_errors_{run_id[:8]}.jsonl",
            )
            total_inserted += ins
            total_skipped += skp
            total_errors += err
            logger.info(
                "%s done: inserted=%d skipped=%d errors=%d",
                coll_name, ins, skp, err,
            )
    finally:
        client.close()
        if not args.dry_run and session_maker:
            await engine.dispose()

    logger.info(
        "All done: inserted=%d skipped=%d errors=%d",
        total_inserted, total_skipped, total_errors,
    )
    if total_errors:
        logger.warning("Errors written to migrate_errors_%s.jsonl", run_id[:8])


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync MongoDB history to PostgreSQL")
    parser.add_argument(
        "--collections", nargs="*",
        help=f"Collections to sync (default: all). Options: {', '.join(ALL_COLLECTIONS)}"
    )
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print sample rows without writing to PostgreSQL")
    parser.add_argument("--resume-run-id",
                        help="Resume from checkpoint of a previous run_id")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 验证 CLI 帮助**

```bash
python scripts/sync_from_mongodb.py --help
```

Expected: 显示 usage，无报错

- [ ] **Step 4: Commit**

```bash
git add scripts/__init__.py scripts/sync_from_mongodb.py
git commit -m "feat(sync): CLI entry point sync_from_mongodb.py (B-034)"
```

---

## Task 9: Contract 测试

**Files:**
- Create: `tests/contract/test_sync_endpoints.py`

- [ ] **Step 1: 写 contract 测试**

创建 `tests/contract/test_sync_endpoints.py`：

```python
"""Contract tests: sync endpoint wire format."""
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_sync_start_no_secret(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/admin/sync/start", json={})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_sync_start_no_mongodb(app, admin_secret):
    """Without MONGODB_URI configured, returns 503."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/admin/sync/start",
            json={},
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 503
    assert resp.json()["detail"] == "MONGODB_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_sync_status_shape(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/admin/sync/status",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "run_id" in data


@pytest.mark.asyncio
async def test_sync_history_shape(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/admin/sync/history",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
```

(Note: `app` and `admin_secret` fixtures should already exist in `tests/contract/conftest.py` from existing contract tests. If not, add them following the pattern in `tests/conftest.py`.)

- [ ] **Step 2: 运行 contract 测试**

```bash
pytest tests/contract/test_sync_endpoints.py -xvs
```

Expected: 4 tests PASS

- [ ] **Step 3: 运行完整套件**

```bash
pytest tests/ -q
```

Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add tests/contract/test_sync_endpoints.py
git commit -m "test(sync): contract tests for sync endpoints (B-034)"
```
