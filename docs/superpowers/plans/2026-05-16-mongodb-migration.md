# MongoDB → PostgreSQL Migration Script Plan (B-008)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write an idempotent, batch-capable script that reads all voter documents from the legacy MongoDB `thvote_users.voters` collection and upserts them into the PostgreSQL `user` table, mapping every field from the old schema to the new one.

**Architecture:** Standalone script in `scripts/migrate_users_from_mongodb.py`. Uses `pymongo` for MongoDB and `asyncpg` (via SQLAlchemy async) for PostgreSQL. Reads env vars from the shell. `INSERT … ON CONFLICT (id) DO NOTHING` makes it safe to run multiple times. Errors are written to `migrate_errors.jsonl` for manual review. A `--dry-run` flag prints rows without writing.

**Tech Stack:** Python 3.12, pymongo 4+, SQLAlchemy async (asyncpg), argparse

**Prerequisite:** Migration 0004 (`alembic upgrade head`) must be applied to the PostgreSQL DB before running this script (requires `thbwiki_uid` and `qq_openid` columns).

---

## File Map

| File | Action |
|---|---|
| `pyproject.toml` | Modify (add `scripts` optional extra with `pymongo`) |
| `scripts/__init__.py` | Create (empty, makes scripts a package) |
| `scripts/migrate_users_from_mongodb.py` | Create (main migration script) |
| `tests/unit/test_migration_mapping.py` | Create (field mapping logic tests) |

---

## Task 1: Add pymongo dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add pymongo to an optional extra**

Find the `[project]` section in `pyproject.toml`. Add (or append to) an optional `scripts` extra:

```toml
[project.optional-dependencies]
scripts = [
    "pymongo>=4.0",
]
```

- [ ] **Step 2: Verify the section is valid**

```bash
pip install -e ".[scripts]" --dry-run 2>&1 | head -5
```

Expected: shows pymongo in the install list, no parse errors.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore(deps): add pymongo to scripts optional extra (B-008)"
```

---

## Task 2: Field mapping unit tests

**Files:**
- Create: `tests/unit/test_migration_mapping.py`

- [ ] **Step 1: Write tests for the mapping function**

```python
"""Tests for the MongoDB → PostgreSQL field mapping logic."""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock


def _fake_object_id(hex_str: str = "507f1f77bcf86cd799439011"):
    """Return a minimal ObjectId-like mock."""
    oid = MagicMock()
    oid.__str__ = MagicMock(return_value=hex_str)
    return oid


def test_map_full_voter_document():
    """All fields from a fully-populated MongoDB document must map correctly."""
    from scripts.migrate_users_from_mongodb import map_voter_to_user_row

    oid = _fake_object_id("507f1f77bcf86cd799439011")
    created = datetime(2023, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    doc = {
        "_id": oid,
        "phone": "13800138000",
        "phone_verified": True,
        "email": "voter@example.com",
        "email_verified": True,
        "password_hashed": "$2b$12$hashedpassword",
        "salt": None,
        "created_at": created,
        "nickname": "TestUser",
        "signup_ip": "192.168.1.1",
        "qq_openid": "QQ123",
        "pfp": "https://example.com/avatar.jpg",
        "thbwiki_uid": "42",
        "removed": None,
    }

    row = map_voter_to_user_row(doc)

    assert row["id"] == "507f1f77bcf86cd799439011"
    assert row["phone_number"] == "13800138000"
    assert row["phone_verified"] is True
    assert row["email"] == "voter@example.com"
    assert row["email_verified"] is True
    assert row["password_hash"] == "$2b$12$hashedpassword"
    assert row["legacy_salt"] is None
    assert row["register_date"] == created
    assert row["nickname"] == "TestUser"
    assert row["register_ip_address"] == "192.168.1.1"
    assert row["qq_openid"] == "QQ123"
    assert row["pfp"] == "https://example.com/avatar.jpg"
    assert row["thbwiki_uid"] == "42"
    assert row["removed"] is False


def test_map_voter_minimal_document():
    """Fields absent in MongoDB (None/missing) must map to safe defaults."""
    from scripts.migrate_users_from_mongodb import map_voter_to_user_row

    oid = _fake_object_id("000000000000000000000001")
    doc = {
        "_id": oid,
        "phone": None,
        "phone_verified": False,
        "email": "minimal@example.com",
        "email_verified": False,
        "password_hashed": None,
        "salt": None,
        "created_at": datetime(2020, 1, 1, tzinfo=timezone.utc),
        "nickname": None,
        "signup_ip": None,
        # qq_openid, pfp, thbwiki_uid, removed all absent
    }

    row = map_voter_to_user_row(doc)

    assert row["id"] == "000000000000000000000001"
    assert row["phone_number"] is None
    assert row["register_ip_address"] == ""   # None → ""
    assert row["qq_openid"] is None
    assert row["thbwiki_uid"] is None
    assert row["removed"] is False             # None → False


def test_map_voter_removed_true():
    """removed=True in MongoDB must map to removed=True in PostgreSQL."""
    from scripts.migrate_users_from_mongodb import map_voter_to_user_row

    oid = _fake_object_id("000000000000000000000002")
    doc = {
        "_id": oid,
        "phone": None,
        "phone_verified": False,
        "email": "gone@example.com",
        "email_verified": False,
        "password_hashed": None,
        "salt": None,
        "created_at": datetime(2020, 1, 1, tzinfo=timezone.utc),
        "nickname": None,
        "signup_ip": None,
        "removed": True,
    }

    row = map_voter_to_user_row(doc)
    assert row["removed"] is True
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/unit/test_migration_mapping.py -xvs
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts'`

- [ ] **Step 3: Create scripts/__init__.py**

```bash
mkdir -p scripts
touch scripts/__init__.py
```

- [ ] **Step 4: Create the mapping function (minimal — just enough to pass tests)**

Create `scripts/migrate_users_from_mongodb.py` with only the mapping function for now:

```python
"""MongoDB → PostgreSQL voter migration script.

Usage:
    MONGODB_URI=mongodb://... MONGODB_DB=thvote DATABASE_URL=postgresql+asyncpg://... \\
        python scripts/migrate_users_from_mongodb.py [--batch-size 500] [--dry-run]

Prerequisite: alembic upgrade head (including migration 0004) must have been run.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def map_voter_to_user_row(doc: dict[str, Any]) -> dict[str, Any]:
    """Map a MongoDB voter document to a PostgreSQL user row dict.

    Args:
        doc: raw MongoDB document from the voters collection.

    Returns:
        Dict suitable for insertion into the ``user`` table.
    """
    raw_id = doc["_id"]
    user_id = str(raw_id)

    created_at = doc.get("created_at")
    if created_at is not None and not isinstance(created_at, datetime):
        # bson.DateTime wraps a datetime — call as_datetime() if available
        if hasattr(created_at, "as_datetime"):
            created_at = created_at.as_datetime()
        else:
            created_at = datetime.fromisoformat(str(created_at))
    if created_at is not None and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    return {
        "id": user_id,
        "phone_number": doc.get("phone"),
        "phone_verified": bool(doc.get("phone_verified", False)),
        "email": doc.get("email"),
        "email_verified": bool(doc.get("email_verified", False)),
        "password_hash": doc.get("password_hashed"),
        "legacy_salt": doc.get("salt"),
        "register_date": created_at,
        "nickname": doc.get("nickname"),
        "register_ip_address": doc.get("signup_ip") or "",
        "qq_openid": doc.get("qq_openid"),
        "pfp": doc.get("pfp"),
        "thbwiki_uid": doc.get("thbwiki_uid"),
        "removed": bool(doc.get("removed") or False),
    }
```

- [ ] **Step 5: Run mapping tests to verify they pass**

```bash
pytest tests/unit/test_migration_mapping.py -xvs
```

Expected: PASS

---

## Task 3: Complete the migration script

**Files:**
- Modify: `scripts/migrate_users_from_mongodb.py`

- [ ] **Step 1: Add the main migration logic**

Replace the file content with the complete script:

```python
"""MongoDB → PostgreSQL voter migration script.

Usage:
    MONGODB_URI=mongodb://... MONGODB_DB=thvote DATABASE_URL=postgresql+asyncpg://... \\
        python scripts/migrate_users_from_mongodb.py [--batch-size 500] [--dry-run]

Prerequisite: alembic upgrade head (including migration 0004) must have been run.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def map_voter_to_user_row(doc: dict[str, Any]) -> dict[str, Any]:
    """Map a MongoDB voter document to a PostgreSQL user row dict."""
    raw_id = doc["_id"]
    user_id = str(raw_id)

    created_at = doc.get("created_at")
    if created_at is not None and not isinstance(created_at, datetime):
        if hasattr(created_at, "as_datetime"):
            created_at = created_at.as_datetime()
        else:
            created_at = datetime.fromisoformat(str(created_at))
    if created_at is not None and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    return {
        "id": user_id,
        "phone_number": doc.get("phone"),
        "phone_verified": bool(doc.get("phone_verified", False)),
        "email": doc.get("email"),
        "email_verified": bool(doc.get("email_verified", False)),
        "password_hash": doc.get("password_hashed"),
        "legacy_salt": doc.get("salt"),
        "register_date": created_at,
        "nickname": doc.get("nickname"),
        "register_ip_address": doc.get("signup_ip") or "",
        "qq_openid": doc.get("qq_openid"),
        "pfp": doc.get("pfp"),
        "thbwiki_uid": doc.get("thbwiki_uid"),
        "removed": bool(doc.get("removed") or False),
    }


async def migrate(
    mongodb_uri: str,
    mongodb_db: str,
    database_url: str,
    batch_size: int = 500,
    dry_run: bool = False,
) -> None:
    """Run the full migration."""
    import pymongo
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text

    # ── Connect to MongoDB ────────────────────────────────────────────
    logger.info("Connecting to MongoDB: %s / %s", mongodb_uri, mongodb_db)
    mongo_client = pymongo.MongoClient(mongodb_uri)
    db = mongo_client[mongodb_db]
    voters_coll = db["voters"]

    total = voters_coll.count_documents({})
    logger.info("Found %d documents in voters collection", total)

    # ── Connect to PostgreSQL ─────────────────────────────────────────
    if not dry_run:
        engine = create_async_engine(database_url, echo=False)

    # ── Migrate in batches ────────────────────────────────────────────
    inserted = 0
    skipped = 0
    errors = 0
    error_file = "migrate_errors.jsonl"

    batch: list[dict] = []
    num_batches = (total + batch_size - 1) // batch_size

    def flush_log_errors(bad_rows: list[dict]) -> None:
        nonlocal errors
        with open(error_file, "a", encoding="utf-8") as f:
            for row in bad_rows:
                f.write(json.dumps(row, default=str) + "\n")
        errors += len(bad_rows)

    for i, doc in enumerate(voters_coll.find({})):
        try:
            row = map_voter_to_user_row(doc)
        except Exception as exc:
            logger.warning("Mapping error for _id=%s: %s", doc.get("_id"), exc)
            flush_log_errors([{"_id": str(doc.get("_id")), "error": str(exc)}])
            continue

        batch.append(row)

        if len(batch) >= batch_size or i == total - 1:
            batch_num = (i // batch_size) + 1
            if dry_run:
                logger.info(
                    "[dry-run] Batch %d/%d: would insert %d rows",
                    batch_num, num_batches, len(batch),
                )
                for row in batch[:3]:
                    logger.info("  sample: id=%s email=%s", row["id"], row.get("email"))
                batch = []
                continue

            # Upsert batch
            insert_sql = text("""
                INSERT INTO "user" (
                    id, phone_number, phone_verified, email, email_verified,
                    password_hash, legacy_salt, register_date, nickname,
                    register_ip_address, qq_openid, pfp, thbwiki_uid, removed
                ) VALUES (
                    :id, :phone_number, :phone_verified, :email, :email_verified,
                    :password_hash, :legacy_salt, :register_date, :nickname,
                    :register_ip_address, :qq_openid, :pfp, :thbwiki_uid, :removed
                )
                ON CONFLICT (id) DO NOTHING
            """)

            batch_errors: list[dict] = []
            batch_inserted = 0
            batch_skipped = 0

            async with engine.begin() as conn:
                for row in batch:
                    try:
                        result = await conn.execute(insert_sql, row)
                        if result.rowcount == 0:
                            batch_skipped += 1
                        else:
                            batch_inserted += 1
                    except Exception as exc:
                        batch_errors.append({"id": row["id"], "error": str(exc)})

            inserted += batch_inserted
            skipped += batch_skipped
            if batch_errors:
                flush_log_errors(batch_errors)

            logger.info(
                "Batch %d/%d: inserted=%d skipped=%d errors=%d",
                batch_num, num_batches, batch_inserted, batch_skipped, len(batch_errors),
            )
            batch = []

    mongo_client.close()
    if not dry_run:
        await engine.dispose()

    logger.info(
        "Migration complete: inserted=%d skipped=%d errors=%d",
        inserted, skipped, errors,
    )
    if errors:
        logger.warning("Error details written to %s", error_file)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate voters from MongoDB to PostgreSQL")
    parser.add_argument("--batch-size", type=int, default=500, help="Documents per batch")
    parser.add_argument("--dry-run", action="store_true", help="Print rows without writing")
    args = parser.parse_args()

    mongodb_uri = os.environ.get("MONGODB_URI")
    mongodb_db = os.environ.get("MONGODB_DB", "thvote")
    database_url = os.environ.get("DATABASE_URL")

    if not mongodb_uri:
        logger.error("MONGODB_URI environment variable is required")
        sys.exit(1)
    if not database_url and not args.dry_run:
        logger.error("DATABASE_URL environment variable is required (or use --dry-run)")
        sys.exit(1)

    asyncio.run(
        migrate(
            mongodb_uri=mongodb_uri,
            mongodb_db=mongodb_db,
            database_url=database_url or "",
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run unit tests to verify mapping still passes**

```bash
pytest tests/unit/test_migration_mapping.py -xvs
```

Expected: PASS

- [ ] **Step 3: Verify script CLI parses correctly (no MongoDB needed)**

```bash
python scripts/migrate_users_from_mongodb.py --help
```

Expected: shows usage without errors.

- [ ] **Step 4: Dry-run smoke test with a mock MongoDB (optional)**

If you have a local MongoDB with test data:

```bash
MONGODB_URI=mongodb://localhost:27017 MONGODB_DB=thvote_test \
    python scripts/migrate_users_from_mongodb.py --dry-run
```

Expected: logs show mapped rows without writing to PostgreSQL.

- [ ] **Step 5: Commit**

```bash
git add scripts/__init__.py scripts/migrate_users_from_mongodb.py tests/unit/test_migration_mapping.py
git commit -m "feat(scripts): add MongoDB → PostgreSQL voter migration script (B-008)"
```

---

## Task 4: Document the migration procedure

**Files:**
- Create: `docs/operations/mongodb-migration.md`

- [ ] **Step 1: Write the runbook**

```markdown
# MongoDB → PostgreSQL 用户数据迁移

> 创建日期：2026-05-16
> 最后更新：2026-05-16

## 前提条件

1. PostgreSQL 已应用 `alembic upgrade head`（含 migration 0004，需要 `thbwiki_uid` 和 `qq_openid` 列）
2. 安装脚本依赖：`pip install -e ".[scripts]"`
3. 准备好 MongoDB 连接串

## 运行方式

```bash
MONGODB_URI=mongodb://user:pass@host:27017 \
MONGODB_DB=thvote \
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/thvote \
    python scripts/migrate_users_from_mongodb.py \
    [--batch-size 500] \
    [--dry-run]
```

## 参数说明

| 参数 | 说明 |
|---|---|
| `MONGODB_URI` | MongoDB 连接串（必填） |
| `MONGODB_DB` | 数据库名（默认 `thvote`） |
| `DATABASE_URL` | PostgreSQL 连接串（dry-run 时可省略） |
| `--batch-size` | 每批处理的文档数（默认 500） |
| `--dry-run` | 只读取 MongoDB，打印映射结果，不写 PostgreSQL |

## 幂等性

脚本使用 `INSERT … ON CONFLICT (id) DO NOTHING`，可多次执行，已存在的行不会被覆盖。

## 错误处理

失败的行会追加写入当前目录的 `migrate_errors.jsonl`，每行一个 JSON 对象，包含 `id` 和 `error` 字段。

## 字段映射

| MongoDB | PostgreSQL |
|---|---|
| `_id`（ObjectId） | `id`（hex string） |
| `phone` | `phone_number` |
| `password_hashed` | `password_hash` |
| `salt` | `legacy_salt` |
| `created_at` | `register_date` |
| `signup_ip` | `register_ip_address`（NULL → `""`） |
| `qq_openid` | `qq_openid` |
| `thbwiki_uid` | `thbwiki_uid` |
| `removed` | `removed`（NULL → `False`） |
```

- [ ] **Step 2: Commit**

```bash
git add docs/operations/mongodb-migration.md
git commit -m "docs(ops): add MongoDB → PostgreSQL migration runbook (B-008)"
```
