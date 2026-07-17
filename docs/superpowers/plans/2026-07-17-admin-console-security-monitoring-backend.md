# Admin Console Security Monitoring — Backend Implementation Plan (B-049, Plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a lightweight security-monitoring REST API to the admin backend — traffic overview, IP/device clustering, a scored suspect list, a filterable paginated vote explorer, and per-account drill-down — plus fail-closed admin auth and record-only disposition actions (flag/annotate, ban reuse, invalidate-flag).

**Architecture:** New self-contained package `src/apps/admin/monitor/` (dao → scoring → service → schemas → router), reading the live `raw_*` forensic tables (path A). Guarded by a single fail-closed `require_admin` dependency (secret required + IP allowlist) shared with the existing admin router. Disposition actions only **record** state (`raw_*.invalidated` flag, `user.removed`, `voter_review` row) — making them affect rankings is the separate B-050 tally rewrite.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Pydantic v2 response models, Redis (light TTL cache; fakeredis in tests), Alembic (Postgres-only idempotent migration), pytest + sqlite/aiosqlite + fakeredis.

## Global Constraints

- **Auth:** every `/admin/*` endpoint requires a valid `X-Admin-Secret` header **and** a client IP in the allowlist. Fail-**closed**: if `admin_secret` is unset → 403 (no open backdoor). `admin_allowed_ips` empty → IP check skipped (documented escape hatch), secret still required.
- **Read source = path A only:** all monitoring reads hit `raw_*` = `raw_character/raw_music/raw_cp/raw_paper/raw_dojin`. Never read the dead path-B tables (`character/music/cp/questionnaire`). `raw_work` (B-038, deprecated) is excluded from monitoring.
- **Disposition = record only:** `invalidate`/`ban` set flags; they do **not** change rankings in this plan (deferred to B-050). Tests assert the flag lands and is reversible, never a ranking effect.
- **Migrations:** Postgres-only, idempotent `ADD COLUMN/INDEX IF NOT EXISTS`; sqlite test schemas come from `create_all` and skip migrations (same convention as 0011/0012/0013).
- **Scoring:** fixed-weight (constants centralized in `monitor/scoring.py`), exact-share grouping (group by exact IP / exact device string, no union-find). Ordering never auto-acts — human review only.
- **`vote_id` == `user.id`:** a submission's `vote_id` is the voter's user id; join `raw_*.vote_id` to `user.id`.
- **No PII/secret in logs:** never log the admin secret, phone, email, or full IP payloads.
- **Line length ≤ 88** (flake8). New Python has type annotations. Run `PYTHONPATH=$PWD python3 -m pytest tests/ -q` + `flake8 --max-line-length=88` before each commit.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/common/config.py` (modify) | add `admin_allowed_ips` setting |
| `src/apps/admin/deps.py` (create) | `require_admin` dependency (fail-closed secret + IP allowlist) + `_ip_allowed` helper |
| `src/apps/admin/router.py` (modify) | apply `require_admin` at router level |
| `src/api/rest/v1/__init__.py` (modify) | mount `monitor_router` at `/api/v1/admin/monitor` |
| `src/db_model/raw_submit.py` (modify) | `invalidated` column on 6 raw_* models + `user_ip` indexes |
| `src/db_model/voter_review.py` (create) | `voter_review` table |
| `src/db_model/user.py` (modify) | index on `register_date` |
| `src/db_model/__init__.py` (modify) | register `VoterReview` for `create_all` |
| `alembic/versions/0014_admin_monitor_support.py` (create) | invalidated column + indexes + voter_review table |
| `src/apps/admin/monitor/__init__.py` (create) | package marker |
| `src/apps/admin/monitor/scoring.py` (create) | fixed-weight suspect scoring (pure) |
| `src/apps/admin/monitor/dao.py` (create) | read/aggregate/action queries over raw_* + voter_review |
| `src/apps/admin/monitor/schemas.py` (create) | Pydantic response/request models |
| `src/apps/admin/monitor/service.py` (create) | orchestration + light Redis cache + scoring wiring |
| `src/apps/admin/monitor/router.py` (create) | monitor REST endpoints |
| `tests/unit/test_monitor_scoring.py` (create) | scoring unit tests |
| `tests/integration/test_admin_monitor.py` (create) | endpoint + auth + action integration tests |

---

## Task 1: Fail-closed admin auth — secret required + IP allowlist

**Files:**
- Modify: `src/common/config.py` (add `admin_allowed_ips`)
- Create: `src/apps/admin/deps.py`
- Modify: `src/apps/admin/router.py:46` (apply `require_admin` at router level)
- Test: `tests/unit/test_admin_ip_allowlist.py`, and auth cases in `tests/integration/test_admin_monitor.py` (Task 6)

**Interfaces:**
- Produces: `require_admin(request, x_admin_secret, settings) -> None` (FastAPI dependency, raises `HTTPException(403)`); `_ip_allowed(client_ip: str, allowlist: list[str]) -> bool` (pure); `Settings.admin_allowed_ips: list[str]`.
- Consumes: `get_client_ip(request: Request) -> str` from `src.apps.user.deps`; `Settings.admin_secret` (`src/common/config.py:222`, `Optional[str]`).

- [ ] **Step 1: Write the failing unit test for IP matching**

Create `tests/unit/test_admin_ip_allowlist.py`:

```python
from src.apps.admin.deps import _ip_allowed


def test_empty_allowlist_allows_everything():
    assert _ip_allowed("1.2.3.4", []) is True


def test_exact_ip_match():
    assert _ip_allowed("1.2.3.4", ["1.2.3.4"]) is True
    assert _ip_allowed("1.2.3.5", ["1.2.3.4"]) is False


def test_cidr_match():
    assert _ip_allowed("10.0.5.9", ["10.0.0.0/8"]) is True
    assert _ip_allowed("11.0.5.9", ["10.0.0.0/8"]) is False


def test_malformed_client_ip_denied_when_allowlist_set():
    assert _ip_allowed("not-an-ip", ["1.2.3.4"]) is False


def test_malformed_allowlist_entry_skipped():
    assert _ip_allowed("1.2.3.4", ["garbage", "1.2.3.4"]) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$PWD python3 -m pytest tests/unit/test_admin_ip_allowlist.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.apps.admin.deps'`

- [ ] **Step 3: Add the `admin_allowed_ips` setting**

In `src/common/config.py`, in the `# 安全配置` block next to `trusted_proxy_ips` (around line 236-238), add:

```python
    # 管理端 IP 白名单(B-049)。Nacos 里写 JSON 数组字符串,
    # 如 "ADMIN_ALLOWED_IPS": "[\"1.2.3.4\", \"10.0.0.0/8\"]"。
    # 空 = 不限 IP(仍需 X-Admin-Secret);pydantic-settings 自动 JSON 解码 list[str]。
    admin_allowed_ips: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Create `src/apps/admin/deps.py`**

```python
"""管理端鉴权依赖(B-049):X-Admin-Secret 强制必填 + IP 白名单,fail-closed。

放独立模块(不放 router.py)以便 admin/router 与 monitor/router 共用,避免循环导入。
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request

from src.apps.user.deps import get_client_ip
from src.common.config import Settings, get_settings

_logger = logging.getLogger(__name__)


def _ip_allowed(client_ip: str, allowlist: list[str]) -> bool:
    """空白名单=放行(逃生舱);否则精确 IP 或 CIDR 命中才放行。"""
    if not allowlist:
        return True
    try:
        ip = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for entry in allowlist:
        try:
            if "/" in entry:
                if ip in ipaddress.ip_network(entry, strict=False):
                    return True
            elif ip == ipaddress.ip_address(entry):
                return True
        except ValueError:
            continue  # 白名单里写错的条目跳过,不影响其余
    return False


async def require_admin(
    request: Request,
    x_admin_secret: Optional[str] = Header(None),
    settings: Settings = Depends(get_settings),
) -> None:
    # fail-closed:未配 secret 一律拒(不留"未配=放行"的开放后门)
    if not settings.admin_secret or x_admin_secret != settings.admin_secret:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    client_ip = get_client_ip(request)
    if not _ip_allowed(client_ip, settings.admin_allowed_ips):
        # 不记完整 IP,避免噪声;仅计一次拒绝
        _logger.warning("admin request rejected: IP not in allowlist")
        raise HTTPException(status_code=403, detail="FORBIDDEN_IP")
```

- [ ] **Step 5: Run the unit test to verify it passes**

Run: `PYTHONPATH=$PWD python3 -m pytest tests/unit/test_admin_ip_allowlist.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Apply `require_admin` at the admin router level**

In `src/apps/admin/router.py`, add the import and attach the dependency to the router constructor (line 46). This hardens **all** existing admin endpoints (fixes B-042 fail-open). Leave the existing per-endpoint `_check_admin_secret` calls in place — they are now redundant belt-and-suspenders and harmless (same 403). Add a one-line comment noting `require_admin` is the primary gate.

```python
from src.apps.admin.deps import require_admin
```

```python
router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    # B-049:统一鉴权闸门(secret 必填 + IP 白名单,fail-closed)。
    dependencies=[Depends(require_admin)],
)
```

(`Depends` is already imported in `router.py`.)

- [ ] **Step 7: Run the full admin test suite to confirm no breakage**

Run: `PYTHONPATH=$PWD python3 -m pytest tests/integration/test_admin_routes_ext.py tests/contract/test_admin_endpoints_ext.py -q`
Expected: PASS. (All admin tests already use the `admin_secret` fixture + `X-Admin-Secret` header; `admin_allowed_ips` defaults empty → IP check skipped. The httpx `ASGITransport` default client is `127.0.0.1`, so nothing is blocked.)

- [ ] **Step 8: Commit**

```bash
git add src/common/config.py src/apps/admin/deps.py src/apps/admin/router.py tests/unit/test_admin_ip_allowlist.py
git commit -m "feat(admin): fail-closed admin auth — secret required + IP allowlist (B-049, B-042)"
```

---

## Task 2: Migration 0014 + model columns (invalidated flag, indexes, voter_review)

**Files:**
- Modify: `src/db_model/raw_submit.py`
- Create: `src/db_model/voter_review.py`
- Modify: `src/db_model/user.py`, `src/db_model/__init__.py`
- Create: `alembic/versions/0014_admin_monitor_support.py`

**Interfaces:**
- Produces: `RawCharacterSubmit.invalidated: bool` (and on Music/CP/Paper/Dojin/Work); `VoterReview` model with `user_id: str` (PK), `status: str`, `note: str`, `updated_at`.
- Consumes: `Base` from `src/db_model/base.py`.

- [ ] **Step 1: Add `invalidated` column to each raw_* model**

In `src/db_model/raw_submit.py`, update the imports:

```python
from sqlalchemy import (
    Boolean, DateTime, Index, Integer, String, Text, func, text,
)
```

Add this line to **each** of the 6 model classes (`RawCharacterSubmit`, `RawMusicSubmit`, `RawCPSubmit`, `RawPaperSubmit`, `RawDojinSubmit`, `RawWorkSubmit`), right after the `client_env` column:

```python
    # 管理端作废软标记(B-049):可逆,仅记录。让它影响排名属 B-050 计票重写。
    invalidated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
```

- [ ] **Step 2: Add `user_ip` indexes for the 5 monitored raw_* tables**

At the bottom of `src/db_model/raw_submit.py`, after the existing `idx_raw_*_vote_created` indexes, add (skip `raw_work`):

```python
Index("idx_raw_character_user_ip", RawCharacterSubmit.user_ip)
Index("idx_raw_music_user_ip", RawMusicSubmit.user_ip)
Index("idx_raw_cp_user_ip", RawCPSubmit.user_ip)
Index("idx_raw_paper_user_ip", RawPaperSubmit.user_ip)
Index("idx_raw_dojin_user_ip", RawDojinSubmit.user_ip)
```

- [ ] **Step 3: Create the `voter_review` model**

Create `src/db_model/voter_review.py`:

```python
from __future__ import annotations

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class VoterReview(Base):
    """管理端对某账号的人工复核记录(B-049):标记状态 + 备注。

    每账号一行(user_id 作 PK,= 投票用户 id)。不破坏投票数据,纯附加复核信息。
    """

    __tablename__ = "voter_review"

    user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="")
    note: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

- [ ] **Step 4: Register the model + add `register_date` index**

In `src/db_model/__init__.py`, add alongside the other model imports (after the `from .user import User` line):

```python
from .voter_review import VoterReview  # noqa: F401  (registers table for create_all)
```

In `src/db_model/user.py`, ensure `Index` is imported (`from sqlalchemy import ... Index`) and add at module level (bottom of file, after the class):

```python
Index("idx_user_register_date", User.register_date)
```

- [ ] **Step 5: Write migration 0014**

Create `alembic/versions/0014_admin_monitor_support.py`:

```python
"""0014 admin monitor support (B-049): raw_*.invalidated + indexes + voter_review.

Adds a reversible ``invalidated`` soft-flag to the 6 raw_* submit tables (admin
can void a specific vote — recorded only; making it affect rankings is B-050),
btree indexes on ``raw_*.user_ip`` and ``user.register_date`` for the monitoring
aggregations, and the ``voter_review`` table (per-account review status + note).

Idempotent ``ADD COLUMN/INDEX IF NOT EXISTS`` (Postgres-only, same convention as
0011/0012/0013). sqlite test schemas are built via ``create_all`` and skip this.
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

_RAW_TABLES = (
    "raw_character", "raw_music", "raw_cp", "raw_paper", "raw_dojin", "raw_work",
)
_IP_INDEXED = ("raw_character", "raw_music", "raw_cp", "raw_paper", "raw_dojin")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in _RAW_TABLES:
        op.execute(
            f'ALTER TABLE "{table}" '
            f"ADD COLUMN IF NOT EXISTS invalidated BOOLEAN NOT NULL DEFAULT false"
        )
    for table in _IP_INDEXED:
        op.execute(
            f'CREATE INDEX IF NOT EXISTS "idx_{table}_user_ip" '
            f'ON "{table}" (user_ip)'
        )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_user_register_date" '
        'ON "user" (register_date)'
    )
    op.execute(
        'CREATE TABLE IF NOT EXISTS "voter_review" ('
        "user_id VARCHAR(255) PRIMARY KEY, "
        "status VARCHAR(32) NOT NULL DEFAULT '', "
        "note TEXT NOT NULL DEFAULT '', "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute('DROP TABLE IF EXISTS "voter_review"')
    op.execute('DROP INDEX IF EXISTS "idx_user_register_date"')
    for table in _IP_INDEXED:
        op.execute(f'DROP INDEX IF EXISTS "idx_{table}_user_ip"')
    for table in _RAW_TABLES:
        op.execute(f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS invalidated')
```

- [ ] **Step 6: Verify models import + single alembic head**

Run:
```bash
PYTHONPATH=$PWD python3 -c "from src.db_model.voter_review import VoterReview; from src.db_model.raw_submit import RawCharacterSubmit; print('col', RawCharacterSubmit.invalidated is not None, 'tbl', VoterReview.__tablename__)"
PYTHONPATH=$PWD python3 -c "import alembic.config, alembic.script; s=alembic.script.ScriptDirectory.from_config(alembic.config.Config('alembic.ini')); print('heads:', s.get_heads())"
```
Expected: first prints `col True tbl voter_review`; second prints `heads: ('0014',)`.

- [ ] **Step 7: Commit**

```bash
git add src/db_model/raw_submit.py src/db_model/voter_review.py src/db_model/user.py src/db_model/__init__.py alembic/versions/0014_admin_monitor_support.py
git commit -m "feat(admin): migration 0014 — raw_*.invalidated + monitor indexes + voter_review (B-049)"
```

---

## Task 3: MonitorDAO — read & aggregate queries over raw_*

**Files:**
- Create: `src/apps/admin/monitor/__init__.py` (empty marker)
- Create: `src/apps/admin/monitor/dao.py`
- Test: `tests/integration/test_admin_monitor.py` (DAO-level tests using the `db_session` fixture)

**Interfaces:**
- Produces: `MonitorDAO(session)` with async methods:
  - `category_totals() -> dict[str, int]`
  - `distinct_ip_count() -> int`, `distinct_device_count() -> int`
  - `submissions_by_day() -> list[dict]`  (`{"date": "YYYY-MM-DD", "count": int}`)
  - `ip_groups(min_size: int, limit: int) -> list[dict]`  (`{"key": ip, "voter_count": int}`)
  - `device_groups(min_size: int, limit: int) -> list[dict]`
  - `group_members(kind: str, key: str) -> list[str]`  (`kind` ∈ {"ip","device"})
  - `list_votes(category, vote_id, user_ip, device, invalidated, page, page_size) -> tuple[list[dict], int]`
  - `account_votes(vote_id) -> dict`  (per-category rows incl. payload)
  - `account_features(vote_id) -> AccountFeatures`
  - `candidate_vote_ids(cluster_min: int, fast_fill_ms: int, cap: int) -> list[str]`
- Consumes: raw_* models from `src.db_model.raw_submit`; `AccountFeatures` from `monitor/scoring.py` (Task 4 — order Task 4 before this task's Step 5, or import lazily).

> **Note on scale:** each aggregate is one indexed GROUP BY over ~50k-row tables (sub-second on Postgres). The suspect path scores only `candidate_vote_ids(...)` (accounts already matching a cheap SQL signal), capped, not every voter.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_admin_monitor.py` with the shared fixtures (copied from the established admin-test pattern) and the first DAO tests:

```python
"""Integration tests for the admin security-monitoring API (B-049)."""
import os

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db_model.base import Base


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncSession:
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s


@pytest_asyncio.fixture
async def app(engine):
    from src.common.database import get_db_session
    from src.common.redis import get_redis
    from src.main import create_app

    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db():
        async with maker() as s:
            yield s

    async def _override_get_redis():
        import fakeredis
        return fakeredis.aioredis.FakeRedis(decode_responses=True)

    a = create_app()
    a.dependency_overrides[get_db_session] = _override_get_db
    a.dependency_overrides[get_redis] = _override_get_redis
    yield a


@pytest.fixture
def admin_secret():
    secret = os.environ.get("ADMIN_SECRET", "test-admin-secret")
    os.environ["ADMIN_SECRET"] = secret
    import src.common.config as cfg
    cfg._settings_instance = None
    yield secret
    cfg._settings_instance = None


async def _seed_char(session, vote_id, user_ip, device=None, fill=None, env=None):
    from src.db_model.raw_submit import RawCharacterSubmit
    session.add(RawCharacterSubmit(
        vote_id=vote_id, user_ip=user_ip, additional_fingreprint=device,
        fill_duration_ms=fill, client_env=env, payload=[1, 2], attempt=1,
    ))
    await session.commit()


@pytest.mark.asyncio
async def test_category_totals_and_ip_groups(db_session):
    from src.apps.admin.monitor.dao import MonitorDAO
    # two accounts share one IP, a third is alone
    await _seed_char(db_session, "u1", "1.1.1.1")
    await _seed_char(db_session, "u2", "1.1.1.1")
    await _seed_char(db_session, "u3", "2.2.2.2")

    dao = MonitorDAO(db_session)
    totals = await dao.category_totals()
    assert totals["character"] == 3

    groups = await dao.ip_groups(min_size=2, limit=10)
    assert groups == [{"key": "1.1.1.1", "voter_count": 2}]

    members = await dao.group_members("ip", "1.1.1.1")
    assert sorted(members) == ["u1", "u2"]


@pytest.mark.asyncio
async def test_list_votes_filters_and_pagination(db_session):
    from src.apps.admin.monitor.dao import MonitorDAO
    await _seed_char(db_session, "u1", "1.1.1.1", fill=500)
    await _seed_char(db_session, "u2", "9.9.9.9", fill=8000)

    dao = MonitorDAO(db_session)
    rows, total = await dao.list_votes(
        category="character", vote_id=None, user_ip="1.1.1.1",
        device=None, invalidated=None, page=1, page_size=20,
    )
    assert total == 1
    assert rows[0]["vote_id"] == "u1"
    assert rows[0]["fill_duration_ms"] == 500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$PWD python3 -m pytest tests/integration/test_admin_monitor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.apps.admin.monitor.dao'`

- [ ] **Step 3: Create the package marker + DAO**

Create `src/apps/admin/monitor/__init__.py` (empty).

Create `src/apps/admin/monitor/dao.py`:

```python
"""管理端安全监控读侧查询(B-049)。只读 raw_*(路径 A);排除 raw_work(废弃)。

每个聚合都是单表/UNION 上的索引 GROUP BY,取证量级(每表约 5 万行)亚秒。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Date, cast, func, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.admin.monitor.scoring import AccountFeatures
from src.db_model.raw_submit import (
    RawCharacterSubmit,
    RawCPSubmit,
    RawDojinSubmit,
    RawMusicSubmit,
    RawPaperSubmit,
)
from src.db_model.user import User

# 参与监控的 5 类(raw_work 废弃,不含)。paper 用 papers_json,其余用 payload。
CATEGORY_MODELS: dict[str, type] = {
    "character": RawCharacterSubmit,
    "music": RawMusicSubmit,
    "cp": RawCPSubmit,
    "paper": RawPaperSubmit,
    "dojin": RawDojinSubmit,
}
_MODELS = tuple(CATEGORY_MODELS.values())

_SCRIPTED_UA_MARKERS = ("headless", "phantom", "selenium", "python-requests",
                        "curl", "wget", "httpx", "bot")


class MonitorDAO:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ── 概览 ────────────────────────────────────────────────────────────────
    async def category_totals(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for name, model in CATEGORY_MODELS.items():
            stmt = select(func.count(func.distinct(model.vote_id)))
            out[name] = (await self.session.execute(stmt)).scalar_one()
        return out

    async def distinct_ip_count(self) -> int:
        sub = union_all(*[select(m.user_ip.label("ip")) for m in _MODELS]).subquery()
        stmt = select(func.count(func.distinct(sub.c.ip)))
        return (await self.session.execute(stmt)).scalar_one()

    async def distinct_device_count(self) -> int:
        sub = union_all(*[
            select(m.additional_fingreprint.label("dev")) for m in _MODELS
        ]).subquery()
        stmt = select(func.count(func.distinct(sub.c.dev))).where(
            sub.c.dev.isnot(None)
        )
        return (await self.session.execute(stmt)).scalar_one()

    async def submissions_by_day(self) -> list[dict]:
        sub = union_all(*[
            select(m.created_at.label("ts")) for m in _MODELS
        ]).subquery()
        day = cast(sub.c.ts, Date).label("day")
        stmt = select(day, func.count().label("n")).group_by(day).order_by(day)
        rows = (await self.session.execute(stmt)).all()
        return [{"date": str(r.day), "count": r.n} for r in rows]

    # ── 聚类 ────────────────────────────────────────────────────────────────
    async def _groups(self, col_name: str, min_size: int, limit: int) -> list[dict]:
        sub = union_all(*[
            select(
                getattr(m, col_name).label("key"),
                m.vote_id.label("vote_id"),
            )
            for m in _MODELS
        ]).subquery()
        cnt = func.count(func.distinct(sub.c.vote_id)).label("voter_count")
        stmt = (
            select(sub.c.key, cnt)
            .where(sub.c.key.isnot(None))
            .group_by(sub.c.key)
            .having(cnt >= min_size)
            .order_by(cnt.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [{"key": r.key, "voter_count": r.voter_count} for r in rows]

    async def ip_groups(self, min_size: int, limit: int) -> list[dict]:
        return await self._groups("user_ip", min_size, limit)

    async def device_groups(self, min_size: int, limit: int) -> list[dict]:
        return await self._groups("additional_fingreprint", min_size, limit)

    async def group_members(self, kind: str, key: str) -> list[str]:
        col = "user_ip" if kind == "ip" else "additional_fingreprint"
        sub = union_all(*[
            select(getattr(m, col).label("key"), m.vote_id.label("vote_id"))
            for m in _MODELS
        ]).subquery()
        stmt = select(func.distinct(sub.c.vote_id)).where(sub.c.key == key)
        return [r[0] for r in (await self.session.execute(stmt)).all()]

    # ── 投票浏览器(单类别过滤 + 分页)──────────────────────────────────────
    async def list_votes(
        self,
        category: str,
        vote_id: Optional[str],
        user_ip: Optional[str],
        device: Optional[str],
        invalidated: Optional[bool],
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int]:
        model = CATEGORY_MODELS[category]  # KeyError → 调用方(router)先校验
        conds = []
        if vote_id:
            conds.append(model.vote_id == vote_id)
        if user_ip:
            conds.append(model.user_ip == user_ip)
        if device:
            conds.append(model.additional_fingreprint == device)
        if invalidated is not None:
            conds.append(model.invalidated.is_(invalidated))

        total = (await self.session.execute(
            select(func.count()).select_from(model).where(*conds)
        )).scalar_one()

        stmt = (
            select(model)
            .where(*conds)
            .order_by(model.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        objs = (await self.session.execute(stmt)).scalars().all()
        rows = [{
            "id": o.id,
            "vote_id": o.vote_id,
            "user_ip": o.user_ip,
            "device": o.additional_fingreprint,
            "fill_duration_ms": o.fill_duration_ms,
            "client_env": o.client_env,
            "attempt": o.attempt,
            "invalidated": o.invalidated,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        } for o in objs]
        return rows, total

    # ── 单账号钻取 ─────────────────────────────────────────────────────────
    async def account_votes(self, vote_id: str) -> dict:
        out: dict[str, list] = {}
        for name, model in CATEGORY_MODELS.items():
            stmt = select(model).where(model.vote_id == vote_id).order_by(
                model.created_at.desc()
            )
            objs = (await self.session.execute(stmt)).scalars().all()
            out[name] = [self._row_full(name, o) for o in objs]
        return out

    @staticmethod
    def _row_full(category: str, o) -> dict:
        payload = o.papers_json if category == "paper" else o.payload
        return {
            "id": o.id,
            "user_ip": o.user_ip,
            "device": o.additional_fingreprint,
            "fill_duration_ms": o.fill_duration_ms,
            "client_env": o.client_env,
            "attempt": o.attempt,
            "invalidated": o.invalidated,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "payload": payload,
        }

    # ── 可疑打分:候选集 + 特征装配 ─────────────────────────────────────────
    async def candidate_vote_ids(
        self, cluster_min: int, fast_fill_ms: int, cap: int
    ) -> list[str]:
        """只挑已命中廉价 SQL 信号的账号(在大组里 / 首投过快 / 无 client_env),
        避免给全部投票人算分。结果去重、封顶(封顶记日志,见 service)。"""
        big_ips = [g["key"] for g in await self.ip_groups(cluster_min, cap)]
        big_devs = [g["key"] for g in await self.device_groups(cluster_min, cap)]
        vote_ids: set[str] = set()
        for m in _MODELS:
            conds = [
                (m.fill_duration_ms.isnot(None)) & (m.fill_duration_ms < fast_fill_ms),
                m.client_env.is_(None),
            ]
            if big_ips:
                conds.append(m.user_ip.in_(big_ips))
            if big_devs:
                conds.append(m.additional_fingreprint.in_(big_devs))
            stmt = select(func.distinct(m.vote_id)).where(or_(*conds)).limit(cap)
            vote_ids.update(r[0] for r in (await self.session.execute(stmt)).all())
            if len(vote_ids) >= cap:
                break
        return list(vote_ids)[:cap]

    async def account_features(self, vote_id: str) -> AccountFeatures:
        # 各类别最小首投耗时 + 是否有 client_env/ua + ua 是否脚本特征
        min_fill: Optional[int] = None
        has_env = False
        ua_scripted = False
        first_vote_ts: Optional[datetime] = None
        for m in _MODELS:
            stmt = select(
                m.fill_duration_ms, m.client_env, m.created_at
            ).where(m.vote_id == vote_id)
            for fill, env, ts in (await self.session.execute(stmt)).all():
                if fill is not None and (min_fill is None or fill < min_fill):
                    min_fill = fill
                if env:
                    ua = str((env or {}).get("ua", "")).lower()
                    if ua:
                        has_env = True  # 有 env 且有 ua 才算"像真人浏览器"
                        if any(k in ua for k in _SCRIPTED_UA_MARKERS):
                            ua_scripted = True
                if ts is not None and (first_vote_ts is None or ts < first_vote_ts):
                    first_vote_ts = ts

        seconds: Optional[float] = None
        reg = (await self.session.execute(
            select(User.register_date).where(User.id == vote_id)
        )).scalar_one_or_none()
        if reg is not None and first_vote_ts is not None:
            try:
                seconds = (first_vote_ts - reg).total_seconds()
            except (TypeError, ValueError):
                seconds = None

        ip_size = await self._max_group_size("user_ip", vote_id)
        dev_size = await self._max_group_size("additional_fingreprint", vote_id)

        return AccountFeatures(
            min_fill_duration_ms=min_fill,
            has_client_env=has_env,
            ua_is_scripted=ua_scripted,
            seconds_register_to_first_vote=seconds,
            max_ip_group_size=ip_size,
            max_device_group_size=dev_size,
            # 跨账号 payload 雷同检测较贵,初版不算(恒 False),留作后续信号。
            has_duplicate_payload=False,
        )

    async def _max_group_size(self, col: str, vote_id: str) -> int:
        """该账号所在的 IP/设备组里,最大有多少不同账号(取此账号出现的各 key 的最大组规模)。"""
        keys_sub = union_all(*[
            select(getattr(m, col).label("key")).where(m.vote_id == vote_id)
            for m in _MODELS
        ]).subquery()
        keys = [r[0] for r in (await self.session.execute(
            select(func.distinct(keys_sub.c.key)).where(keys_sub.c.key.isnot(None))
        )).all()]
        if not keys:
            return 0
        all_sub = union_all(*[
            select(getattr(m, col).label("key"), m.vote_id.label("vote_id"))
            for m in _MODELS
        ]).subquery()
        stmt = select(func.count(func.distinct(all_sub.c.vote_id))).where(
            all_sub.c.key.in_(keys)
        )
        return (await self.session.execute(stmt)).scalar_one()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=$PWD python3 -m pytest tests/integration/test_admin_monitor.py -v`
Expected: PASS (2 tests). If a sqlite UNION/`cast` quirk surfaces, fix the query and re-run — the intent (distinct-voter GROUP BY per key) must hold.

- [ ] **Step 5: Commit**

```bash
git add src/apps/admin/monitor/__init__.py src/apps/admin/monitor/dao.py tests/integration/test_admin_monitor.py
git commit -m "feat(admin): MonitorDAO read/aggregate queries over raw_* (B-049)"
```

---

## Task 4: Suspect scoring module (fixed-weight, pure)

**Files:**
- Create: `src/apps/admin/monitor/scoring.py`
- Test: `tests/unit/test_monitor_scoring.py`

**Interfaces:**
- Produces: `AccountFeatures` dataclass, `ScoreResult` (`.score: int`, `.reasons: list[str]`), `score_account(f) -> ScoreResult`, `SCORING_WEIGHTS: dict[str, int]`.
- Consumes: nothing (pure).

> **Ordering:** Task 3's `dao.py` imports `AccountFeatures` from this module. If executing strictly in order, create this module's `AccountFeatures`/`SCORING_WEIGHTS` before Task 3 Step 3, or accept that Task 3's import fails until this task lands. Recommended: do Task 4 immediately before Task 3, or together.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_monitor_scoring.py`:

```python
from src.apps.admin.monitor.scoring import (
    AccountFeatures, score_account, SCORING_WEIGHTS,
)


def _clean() -> AccountFeatures:
    return AccountFeatures(
        min_fill_duration_ms=8000, has_client_env=True, ua_is_scripted=False,
        seconds_register_to_first_vote=120, max_ip_group_size=1,
        max_device_group_size=1, has_duplicate_payload=False,
    )


def test_clean_account_scores_zero():
    result = score_account(_clean())
    assert result.score == 0
    assert result.reasons == []


def test_fast_fill_flags_and_weights():
    f = _clean()
    f.min_fill_duration_ms = 500
    result = score_account(f)
    assert result.score == SCORING_WEIGHTS["fast_fill"]
    assert any("fill" in r or "耗时" in r for r in result.reasons)


def test_signals_are_additive():
    f = _clean()
    f.min_fill_duration_ms = 500          # fast_fill
    f.ua_is_scripted = True               # scripted_ua
    f.max_ip_group_size = 6               # ip_cluster
    expected = (
        SCORING_WEIGHTS["fast_fill"]
        + SCORING_WEIGHTS["scripted_ua"]
        + SCORING_WEIGHTS["ip_cluster"]
    )
    assert score_account(f).score == expected
    assert len(score_account(f).reasons) == 3


def test_missing_client_env_flags():
    f = _clean()
    f.has_client_env = False
    assert score_account(f).score == SCORING_WEIGHTS["no_client_env"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$PWD python3 -m pytest tests/unit/test_monitor_scoring.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Create the scoring module**

Create `src/apps/admin/monitor/scoring.py`:

```python
"""固定加权可疑分(B-049)。权重集中此处便于迭代;纯函数,不碰 DB。

只排序供人工复核,不自动处置(延续"取证不拦截")。阈值/权重是初版,
按投票期实际数据调这里的常量即可,不改调用方。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 命中即加分。数值越大越可疑。调参只动这张表。
SCORING_WEIGHTS: dict[str, int] = {
    "fast_fill": 3,          # 首投填写耗时过短(瞎点)
    "no_client_env": 3,      # 无 client_env(纯 API 机器人)
    "scripted_ua": 3,        # ua 含 headless / 脚本特征
    "instant_vote": 2,       # 注册→首投过快
    "ip_cluster": 2,         # 所在 IP 组规模达阈值
    "device_cluster": 2,     # 所在设备组规模达阈值
    "duplicate_payload": 3,  # 与他人 payload 完全雷同(初版未启用,见 dao)
}

FAST_FILL_MS = 2000
INSTANT_VOTE_SECONDS = 5
CLUSTER_MIN_SIZE = 5


@dataclass
class AccountFeatures:
    """单账号聚合信号(由 MonitorDAO.account_features 装配)。"""

    min_fill_duration_ms: int | None
    has_client_env: bool
    ua_is_scripted: bool
    seconds_register_to_first_vote: float | None
    max_ip_group_size: int
    max_device_group_size: int
    has_duplicate_payload: bool


@dataclass
class ScoreResult:
    score: int = 0
    reasons: list[str] = field(default_factory=list)


def score_account(f: AccountFeatures) -> ScoreResult:
    result = ScoreResult()

    def hit(key: str, reason: str) -> None:
        result.score += SCORING_WEIGHTS[key]
        result.reasons.append(reason)

    if f.min_fill_duration_ms is not None and f.min_fill_duration_ms < FAST_FILL_MS:
        hit("fast_fill", f"首投耗时 {f.min_fill_duration_ms}ms < {FAST_FILL_MS}ms")
    if not f.has_client_env:
        hit("no_client_env", "缺 client_env / ua")
    if f.ua_is_scripted:
        hit("scripted_ua", "ua 含 headless/脚本特征")
    if (
        f.seconds_register_to_first_vote is not None
        and f.seconds_register_to_first_vote < INSTANT_VOTE_SECONDS
    ):
        hit("instant_vote", f"注册→首投 {f.seconds_register_to_first_vote:.0f}s")
    if f.max_ip_group_size >= CLUSTER_MIN_SIZE:
        hit("ip_cluster", f"IP 组规模 {f.max_ip_group_size}")
    if f.max_device_group_size >= CLUSTER_MIN_SIZE:
        hit("device_cluster", f"设备组规模 {f.max_device_group_size}")
    if f.has_duplicate_payload:
        hit("duplicate_payload", "payload 与他人完全雷同")

    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=$PWD python3 -m pytest tests/unit/test_monitor_scoring.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/apps/admin/monitor/scoring.py tests/unit/test_monitor_scoring.py
git commit -m "feat(admin): fixed-weight suspect scoring module (B-049)"
```

---

## Task 5: Schemas + MonitorService (orchestration + light cache)

**Files:**
- Create: `src/apps/admin/monitor/schemas.py`
- Create: `src/apps/admin/monitor/service.py`
- Test: `tests/integration/test_admin_monitor.py` (add service-level tests)

**Interfaces:**
- Produces: Pydantic models (`OverviewResponse`, `GroupItem`, `GroupsResponse`, `SuspectItem`, `SuspectsResponse`, `VoteRow`, `VotesPage`, `AccountDetail`, `ReviewRequest`, `ActionResult`); `MonitorService(session, redis, settings)` with `overview()`, `groups(kind, min_size, limit)`, `suspects(page, page_size)`, `list_votes(...)`, `account(vote_id)`.
- Consumes: `MonitorDAO` (Task 3), `score_account`/`AccountFeatures` (Task 4), `VoterReview` model (Task 2).

- [ ] **Step 1: Write the failing test (suspects scoring end-to-end via service)**

Add to `tests/integration/test_admin_monitor.py`:

```python
@pytest.mark.asyncio
async def test_service_suspects_ranks_fast_fill(db_session):
    import fakeredis
    from src.apps.admin.monitor.service import MonitorService
    from src.common.config import get_settings

    await _seed_char(db_session, "bot", "3.3.3.3", fill=200, env=None)   # suspicious
    await _seed_char(db_session, "human", "4.4.4.4", fill=9000,
                     env={"ua": "Mozilla/5.0"})                          # clean

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    svc = MonitorService(db_session, redis, get_settings())
    page = await svc.suspects(page=1, page_size=20)
    ids = [s.vote_id for s in page.items]
    assert "bot" in ids
    top = page.items[0]
    assert top.vote_id == "bot"
    assert top.score >= 3
    assert top.reasons
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$PWD python3 -m pytest tests/integration/test_admin_monitor.py::test_service_suspects_ranks_fast_fill -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.apps.admin.monitor.service'`

- [ ] **Step 3: Create the schemas**

Create `src/apps/admin/monitor/schemas.py`:

```python
"""管理端监控接口输入输出契约(B-049)。显式模型,不返回随意 JSON。"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class OverviewResponse(BaseModel):
    category_totals: dict[str, int]
    distinct_ips: int
    distinct_devices: int
    submissions_by_day: list[dict[str, Any]]


class GroupItem(BaseModel):
    key: str
    voter_count: int


class GroupsResponse(BaseModel):
    kind: str
    items: list[GroupItem]


class SuspectItem(BaseModel):
    vote_id: str
    score: int
    reasons: list[str]


class SuspectsResponse(BaseModel):
    items: list[SuspectItem]
    total: int
    page: int
    page_size: int
    truncated: bool = False


class VoteRow(BaseModel):
    id: int
    vote_id: str
    user_ip: str
    device: Optional[str]
    fill_duration_ms: Optional[int]
    client_env: Optional[dict[str, Any]]
    attempt: Optional[int]
    invalidated: bool
    created_at: Optional[str]


class VotesPage(BaseModel):
    items: list[VoteRow]
    total: int
    page: int
    page_size: int


class AccountDetail(BaseModel):
    vote_id: str
    votes: dict[str, list[dict[str, Any]]]
    review: Optional[dict[str, Any]] = None
    ip_groups: list[str] = []
    device_groups: list[str] = []


class ReviewRequest(BaseModel):
    status: str = ""
    note: str = ""


class ActionResult(BaseModel):
    ok: bool
    detail: str = ""
```

- [ ] **Step 4: Create the service**

Create `src/apps/admin/monitor/service.py`:

```python
"""监控编排 + 轻缓存(B-049)。贵的聚合(概览/分组/可疑名单)缓存 60s;
按需实时算,数据陈旧 60s 对监控可接受。可疑名单只给命中廉价信号的候选打分。
"""

from __future__ import annotations

import json
import logging

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.admin.monitor.dao import MonitorDAO
from src.apps.admin.monitor.schemas import (
    GroupItem,
    GroupsResponse,
    OverviewResponse,
    SuspectItem,
    SuspectsResponse,
    VotesPage,
)
from src.apps.admin.monitor.scoring import (
    CLUSTER_MIN_SIZE,
    FAST_FILL_MS,
    score_account,
)
from src.common.config import Settings

_logger = logging.getLogger(__name__)

_CACHE_TTL = 60
_SUSPECT_CAP = 2000  # 候选账号封顶,超出记日志(不静默截断)


class MonitorService:
    def __init__(self, session: AsyncSession, redis: aioredis.Redis,
                 settings: Settings):
        self.dao = MonitorDAO(session)
        self.redis = redis
        self.settings = settings

    async def _cached(self, key: str, compute):
        try:
            raw = await self.redis.get(key)
            if raw:
                return json.loads(raw)
        except Exception:  # 缓存不可用不该拖垮读接口
            _logger.warning("monitor cache read failed for %s", key)
        value = await compute()
        try:
            await self.redis.set(key, json.dumps(value), ex=_CACHE_TTL)
        except Exception:
            _logger.warning("monitor cache write failed for %s", key)
        return value

    async def overview(self) -> OverviewResponse:
        async def _compute():
            return {
                "category_totals": await self.dao.category_totals(),
                "distinct_ips": await self.dao.distinct_ip_count(),
                "distinct_devices": await self.dao.distinct_device_count(),
                "submissions_by_day": await self.dao.submissions_by_day(),
            }
        data = await self._cached("admin:monitor:overview", _compute)
        return OverviewResponse(**data)

    async def groups(self, kind: str, min_size: int, limit: int) -> GroupsResponse:
        async def _compute():
            if kind == "device":
                items = await self.dao.device_groups(min_size, limit)
            else:
                items = await self.dao.ip_groups(min_size, limit)
            return items
        key = f"admin:monitor:groups:{kind}:{min_size}:{limit}"
        items = await self._cached(key, _compute)
        return GroupsResponse(
            kind=kind, items=[GroupItem(**i) for i in items]
        )

    async def suspects(self, page: int, page_size: int) -> SuspectsResponse:
        async def _compute():
            candidates = await self.dao.candidate_vote_ids(
                CLUSTER_MIN_SIZE, FAST_FILL_MS, _SUSPECT_CAP
            )
            truncated = len(candidates) >= _SUSPECT_CAP
            if truncated:
                _logger.warning(
                    "suspect candidates hit cap %s; list truncated", _SUSPECT_CAP
                )
            scored = []
            for vid in candidates:
                features = await self.dao.account_features(vid)
                result = score_account(features)
                if result.score > 0:
                    scored.append(
                        {"vote_id": vid, "score": result.score,
                         "reasons": result.reasons}
                    )
            scored.sort(key=lambda s: s["score"], reverse=True)
            return {"scored": scored, "truncated": truncated}

        data = await self._cached("admin:monitor:suspects", _compute)
        scored = data["scored"]
        total = len(scored)
        start = (page - 1) * page_size
        window = scored[start:start + page_size]
        return SuspectsResponse(
            items=[SuspectItem(**s) for s in window],
            total=total, page=page, page_size=page_size,
            truncated=data["truncated"],
        )

    async def list_votes(self, category: str, vote_id, user_ip, device,
                         invalidated, page: int, page_size: int) -> VotesPage:
        rows, total = await self.dao.list_votes(
            category, vote_id, user_ip, device, invalidated, page, page_size
        )
        return VotesPage(items=rows, total=total, page=page, page_size=page_size)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `PYTHONPATH=$PWD python3 -m pytest tests/integration/test_admin_monitor.py::test_service_suspects_ranks_fast_fill -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/apps/admin/monitor/schemas.py src/apps/admin/monitor/service.py tests/integration/test_admin_monitor.py
git commit -m "feat(admin): monitor schemas + service (light cache + suspect scoring) (B-049)"
```

---

## Task 6: Monitor router — read endpoints + mount

**Files:**
- Create: `src/apps/admin/monitor/router.py`
- Modify: `src/api/rest/v1/__init__.py` (mount `monitor_router`)
- Test: `tests/integration/test_admin_monitor.py` (endpoint + auth tests)

**Interfaces:**
- Produces: `monitor_router: APIRouter` (prefix `/admin/monitor`), endpoints:
  - `GET /overview` → `OverviewResponse`
  - `GET /groups?kind=ip|device&min_size=&limit=` → `GroupsResponse`
  - `GET /groups/{kind}/{key}/members` → `list[str]`
  - `GET /suspects?page=&page_size=` → `SuspectsResponse`
  - `GET /votes?category=&vote_id=&user_ip=&device=&invalidated=&page=&page_size=` → `VotesPage`
  - `GET /account/{vote_id}` → `AccountDetail`
- Consumes: `MonitorService` (Task 5), `require_admin` (Task 1), `get_db_session`, `get_redis`, `get_settings`, `MonitorDAO`, `VoterReview`, `CATEGORY_MODELS`.

- [ ] **Step 1: Write the failing tests (endpoint happy path + auth)**

Add to `tests/integration/test_admin_monitor.py`:

```python
@pytest.mark.asyncio
async def test_overview_endpoint_requires_secret(app):
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        resp = await ac.get("/api/v1/admin/monitor/overview")   # no header
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_overview_endpoint_returns_totals(app, db_session, admin_secret):
    await _seed_char(db_session, "u1", "1.1.1.1")
    await _seed_char(db_session, "u2", "1.1.1.1")
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        resp = await ac.get("/api/v1/admin/monitor/overview",
                            headers={"X-Admin-Secret": admin_secret})
    assert resp.status_code == 200
    body = resp.json()
    assert body["category_totals"]["character"] == 2
    assert body["distinct_ips"] == 1


@pytest.mark.asyncio
async def test_votes_endpoint_filter(app, db_session, admin_secret):
    await _seed_char(db_session, "u1", "1.1.1.1", fill=500)
    await _seed_char(db_session, "u2", "9.9.9.9")
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/admin/monitor/votes?category=character&user_ip=1.1.1.1",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["vote_id"] == "u1"


@pytest.mark.asyncio
async def test_votes_endpoint_rejects_bad_category(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/admin/monitor/votes?category=bogus",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=$PWD python3 -m pytest tests/integration/test_admin_monitor.py -k endpoint -v`
Expected: FAIL — 404 (route not mounted) / ImportError.

- [ ] **Step 3: Create the monitor router**

Create `src/apps/admin/monitor/router.py`:

```python
"""管理端安全监控 REST 端点(B-049)。挂在 /api/v1/admin/monitor,require_admin 守卫。"""

from __future__ import annotations

from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.admin.deps import require_admin
from src.apps.admin.monitor.dao import CATEGORY_MODELS, MonitorDAO
from src.apps.admin.monitor.schemas import (
    AccountDetail,
    GroupsResponse,
    OverviewResponse,
    SuspectsResponse,
    VotesPage,
)
from src.apps.admin.monitor.service import MonitorService
from src.common.config import Settings, get_settings
from src.common.database import get_db_session
from src.common.redis import get_redis

monitor_router = APIRouter(
    prefix="/admin/monitor",
    tags=["admin-monitor"],
    dependencies=[Depends(require_admin)],
)


def _service(
    session: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> MonitorService:
    return MonitorService(session, redis, settings)


@monitor_router.get("/overview", response_model=OverviewResponse)
async def overview(svc: MonitorService = Depends(_service)) -> OverviewResponse:
    return await svc.overview()


@monitor_router.get("/groups", response_model=GroupsResponse)
async def groups(
    kind: str = Query("ip", pattern="^(ip|device)$"),
    min_size: int = Query(2, ge=1),
    limit: int = Query(100, ge=1, le=1000),
    svc: MonitorService = Depends(_service),
) -> GroupsResponse:
    return await svc.groups(kind, min_size, limit)


@monitor_router.get("/groups/{kind}/{key}/members", response_model=list[str])
async def group_members(
    kind: str, key: str, session: AsyncSession = Depends(get_db_session)
) -> list[str]:
    if kind not in ("ip", "device"):
        raise HTTPException(status_code=422, detail="kind must be ip|device")
    return await MonitorDAO(session).group_members(kind, key)


@monitor_router.get("/suspects", response_model=SuspectsResponse)
async def suspects(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    svc: MonitorService = Depends(_service),
) -> SuspectsResponse:
    return await svc.suspects(page, page_size)


@monitor_router.get("/votes", response_model=VotesPage)
async def votes(
    category: str = Query(...),
    vote_id: Optional[str] = None,
    user_ip: Optional[str] = None,
    device: Optional[str] = None,
    invalidated: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    svc: MonitorService = Depends(_service),
) -> VotesPage:
    if category not in CATEGORY_MODELS:
        raise HTTPException(
            status_code=422,
            detail=f"category must be one of {list(CATEGORY_MODELS)}",
        )
    return await svc.list_votes(
        category, vote_id, user_ip, device, invalidated, page, page_size
    )


@monitor_router.get("/account/{vote_id}", response_model=AccountDetail)
async def account(
    vote_id: str, session: AsyncSession = Depends(get_db_session)
) -> AccountDetail:
    from src.db_model.voter_review import VoterReview

    dao = MonitorDAO(session)
    votes_map = await dao.account_votes(vote_id)
    review_obj = await session.get(VoterReview, vote_id)
    review = (
        {"status": review_obj.status, "note": review_obj.note,
         "updated_at": review_obj.updated_at.isoformat()}
        if review_obj else None
    )
    return AccountDetail(
        vote_id=vote_id,
        votes=votes_map,
        review=review,
        ip_groups=await dao.group_members("ip", "") if False else [],
        device_groups=[],
    )
```

> The `ip_groups`/`device_groups` on the account detail list the *keys* this account belongs to. Compute them from the account's own rows (the account's distinct `user_ip` / device values). Replace the two placeholder lines above with:
> ```python
>     own_ips = sorted({r["user_ip"] for rows in votes_map.values() for r in rows})
>     own_devs = sorted({r["device"] for rows in votes_map.values()
>                        for r in rows if r["device"]})
> ```
> and pass `ip_groups=own_ips, device_groups=own_devs`.

- [ ] **Step 4: Fix the account endpoint to use own_ips/own_devs**

Edit the `account` endpoint body so it reads:

```python
    dao = MonitorDAO(session)
    votes_map = await dao.account_votes(vote_id)
    review_obj = await session.get(VoterReview, vote_id)
    review = (
        {"status": review_obj.status, "note": review_obj.note,
         "updated_at": review_obj.updated_at.isoformat()}
        if review_obj else None
    )
    own_ips = sorted({r["user_ip"] for rows in votes_map.values() for r in rows})
    own_devs = sorted({r["device"] for rows in votes_map.values()
                       for r in rows if r["device"]})
    return AccountDetail(
        vote_id=vote_id, votes=votes_map, review=review,
        ip_groups=own_ips, device_groups=own_devs,
    )
```

- [ ] **Step 5: Mount the router**

In `src/api/rest/v1/__init__.py`, add the import near the admin import (line ~5) and include it right after `api_router.include_router(admin_router)` (line ~27):

```python
from src.apps.admin.monitor.router import monitor_router
```
```python
api_router.include_router(monitor_router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `PYTHONPATH=$PWD python3 -m pytest tests/integration/test_admin_monitor.py -v`
Expected: PASS (all monitor tests incl. the 403-without-secret case).

- [ ] **Step 7: Commit**

```bash
git add src/apps/admin/monitor/router.py src/api/rest/v1/__init__.py tests/integration/test_admin_monitor.py
git commit -m "feat(admin): monitor read endpoints (overview/groups/suspects/votes/account) (B-049)"
```

---

## Task 7: Disposition actions — invalidate/restore + review upsert

**Files:**
- Modify: `src/apps/admin/monitor/dao.py` (add action methods)
- Modify: `src/apps/admin/monitor/router.py` (add action endpoints)
- Test: `tests/integration/test_admin_monitor.py` (action tests)

**Interfaces:**
- Produces (DAO): `set_invalidated(category, row_id, value) -> bool`; `upsert_review(user_id, status, note) -> None`.
- Produces (router): `PATCH /admin/monitor/vote/{category}/{row_id}/invalidate`, `.../restore`; `PATCH /admin/monitor/account/{vote_id}/review`.
- Consumes: `CATEGORY_MODELS`, `VoterReview` (Task 2), `ReviewRequest`/`ActionResult` schemas (Task 5).

> **Record-only (B-050 boundary):** these endpoints set flags/rows. They do **not** recompute or affect any ranking — that is the B-050 tally rewrite. The response `detail` says so, so the UI can tell the admin "recorded; effective on rankings after B-050".

- [ ] **Step 1: Write the failing tests**

Add to `tests/integration/test_admin_monitor.py`:

```python
@pytest.mark.asyncio
async def test_invalidate_and_restore_vote(app, db_session, admin_secret):
    from src.db_model.raw_submit import RawCharacterSubmit
    row = RawCharacterSubmit(vote_id="u1", user_ip="1.1.1.1", payload=[1], attempt=1)
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    rid = row.id

    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        h = {"X-Admin-Secret": admin_secret}
        r1 = await ac.patch(
            f"/api/v1/admin/monitor/vote/character/{rid}/invalidate", headers=h)
        assert r1.status_code == 200 and r1.json()["ok"] is True
        # verify flag via the votes listing
        r2 = await ac.get(
            "/api/v1/admin/monitor/votes?category=character&invalidated=true",
            headers=h)
        assert r2.json()["total"] == 1
        r3 = await ac.patch(
            f"/api/v1/admin/monitor/vote/character/{rid}/restore", headers=h)
        assert r3.status_code == 200
        r4 = await ac.get(
            "/api/v1/admin/monitor/votes?category=character&invalidated=true",
            headers=h)
        assert r4.json()["total"] == 0


@pytest.mark.asyncio
async def test_invalidate_unknown_row_404(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        r = await ac.patch(
            "/api/v1/admin/monitor/vote/character/999999/invalidate",
            headers={"X-Admin-Secret": admin_secret})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_review_upsert(app, db_session, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        h = {"X-Admin-Secret": admin_secret}
        r = await ac.patch(
            "/api/v1/admin/monitor/account/u1/review",
            headers=h, json={"status": "suspicious", "note": "shared IP"})
        assert r.status_code == 200 and r.json()["ok"] is True
        # second upsert overwrites, still one row, reflected in account detail
        await ac.patch(
            "/api/v1/admin/monitor/account/u1/review",
            headers=h, json={"status": "cleared", "note": ""})
        detail = await ac.get(
            "/api/v1/admin/monitor/account/u1", headers=h)
    assert detail.json()["review"]["status"] == "cleared"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=$PWD python3 -m pytest tests/integration/test_admin_monitor.py -k "invalidate or review" -v`
Expected: FAIL — 404 (action routes not defined).

- [ ] **Step 3: Add DAO action methods**

Append to `MonitorDAO` in `src/apps/admin/monitor/dao.py`:

```python
    # ── 处置动作(仅记录;影响排名属 B-050)──────────────────────────────────
    async def set_invalidated(
        self, category: str, row_id: int, value: bool
    ) -> bool:
        model = CATEGORY_MODELS[category]
        obj = await self.session.get(model, row_id)
        if obj is None:
            return False
        obj.invalidated = value
        await self.session.commit()
        return True

    async def upsert_review(self, user_id: str, status: str, note: str) -> None:
        from src.db_model.voter_review import VoterReview

        obj = await self.session.get(VoterReview, user_id)
        if obj is None:
            self.session.add(
                VoterReview(user_id=user_id, status=status, note=note)
            )
        else:
            obj.status = status
            obj.note = note
        await self.session.commit()
```

- [ ] **Step 4: Add action endpoints to the router**

Append to `src/apps/admin/monitor/router.py`. First extend the schema import to include `ActionResult` and `ReviewRequest`:

```python
from src.apps.admin.monitor.schemas import (
    AccountDetail,
    ActionResult,
    GroupsResponse,
    OverviewResponse,
    ReviewRequest,
    SuspectsResponse,
    VotesPage,
)
```

Then add the endpoints:

```python
_B050_NOTE = "已记录;影响排名需 B-050 计票重写落地后生效"


async def _set_invalidated(category: str, row_id: int, value: bool,
                           session: AsyncSession) -> ActionResult:
    if category not in CATEGORY_MODELS:
        raise HTTPException(status_code=422, detail="unknown category")
    ok = await MonitorDAO(session).set_invalidated(category, row_id, value)
    if not ok:
        raise HTTPException(status_code=404, detail="vote row not found")
    return ActionResult(ok=True, detail=_B050_NOTE)


@monitor_router.patch(
    "/vote/{category}/{row_id}/invalidate", response_model=ActionResult)
async def invalidate_vote(
    category: str, row_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> ActionResult:
    return await _set_invalidated(category, row_id, True, session)


@monitor_router.patch(
    "/vote/{category}/{row_id}/restore", response_model=ActionResult)
async def restore_vote(
    category: str, row_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> ActionResult:
    return await _set_invalidated(category, row_id, False, session)


@monitor_router.patch("/account/{vote_id}/review", response_model=ActionResult)
async def review_account(
    vote_id: str, body: ReviewRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ActionResult:
    await MonitorDAO(session).upsert_review(vote_id, body.status, body.note)
    return ActionResult(ok=True, detail="review recorded")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONPATH=$PWD python3 -m pytest tests/integration/test_admin_monitor.py -v`
Expected: PASS (all monitor tests).

- [ ] **Step 6: Full suite + lint**

Run:
```bash
PYTHONPATH=$PWD python3 -m pytest tests/ -q
python3 -m flake8 --max-line-length=88 src/apps/admin/monitor/ src/apps/admin/deps.py src/common/config.py
```
Expected: all tests pass; flake8 clean.

- [ ] **Step 7: Update docs + commit**

Update `docs/CHANGELOG.md` (new dated entry: B-049 backend — fail-closed admin auth + migration 0014 + monitoring API + record-only disposition; note ranking effect deferred to B-050) and flip the B-049 row in `docs/BACKLOG.md` to "后端 Plan 1 已实现". Then:

```bash
git add src/apps/admin/monitor/ src/apps/admin/router.py docs/CHANGELOG.md docs/BACKLOG.md
git commit -m "feat(admin): record-only disposition actions — invalidate/restore + review (B-049)"
```

---

## Self-Review (completed by plan author)

- **Spec coverage:** §4.1 overview → Task 3/5/6 `overview`; §4.2/4.3 IP·device clustering → `groups`/`group_members`; §4.4 suspect list → scoring (Task 4) + `suspects` (Task 5/6); §4.5 account drill-down → `account` (Task 6); vote explorer → `votes` (Task 3/5/6); §5 actions → Task 7 (record-only, B-050 boundary honored); §6 migration → Task 2; §auth (fail-closed + IP) → Task 1; §7 perf (indexes, cache, candidate-capping, single-category explorer) → Tasks 2/3/5. Frontend (§8) → Plan 2 (separate).
- **Placeholder scan:** the only intentional "deferred" is `has_duplicate_payload=False` (documented as a future signal, scoring supports it) and the account-endpoint `own_ips/own_devs` fix (Task 6 Step 4 replaces the marked lines with real code). No TBD/TODO.
- **Type consistency:** `AccountFeatures` fields match between `scoring.py` (Task 4) and `dao.account_features` (Task 3); `CATEGORY_MODELS` keys (`character/music/cp/paper/dojin`) are the same set used by router validation, explorer, and actions; schema field names (`voter_count`, `vote_id`, `invalidated`) are consistent across DAO dicts → Pydantic models.

---

## Plan 2 (frontend) — separate plan, written next

The Vue rewrite + StaticFiles serving + Docker multi-stage build is an independent subsystem that consumes this API. It gets its own plan (`docs/superpowers/plans/2026-07-17-admin-console-vue-frontend.md`), written after this backend plan lands so the frontend builds against real, running endpoints. The design doc §8 defines its page set and phased rollout (skeleton + login + monitoring pages first, then migrate the existing HTML tools into Vue).
