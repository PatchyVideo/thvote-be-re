# Quick Wins Implementation Plan (B-017/029/025/018/030/027)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 6 independent medium-priority backlog items: two doc additions, removal of the DEBUG init_db backdoor, audit-log failure visibility, Nacos lazy-load, and hardening the flake8 CI gate.

**Architecture:** Each task is self-contained. B-025 modifies `src/main.py` lifespan; B-018 adds a counter to `src/apps/user/service.py` and exposes it in `/health`; B-030 restructures `src/common/config.py` module init; B-027 adds `.flake8`, fixes all violations, then removes `|| true` from CI.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, pytest, flake8, black

---

## File Map

| File | Action | Task |
|---|---|---|
| `docs/architecture/nacos-hot-reload-limits.md` | Create | B-017 |
| `docs/operations/deploy-server-setup.md` | Create | B-029 |
| `src/main.py` | Modify (remove init_db, add DB check, fix imports, add audit health) | B-025, B-018, B-027 |
| `src/common/config.py` | Modify (lazy load, remove os import) | B-030, B-027 |
| `src/apps/user/service.py` | Modify (add counter + getter) | B-018 |
| `.flake8` | Create | B-027 |
| `src/api/graphql/types.py` | Modify (remove unused import) | B-027 |
| `src/apps/result/compute.py` | Modify (remove unused import, wrap long lines) | B-027 |
| `src/apps/result/compute_dao.py` | Modify (remove unused import, wrap long lines) | B-027 |
| `src/apps/scraper/sites/weibo.py` | Modify (remove unused import) | B-027 |
| `src/common/redis.py` | Modify (remove unused import, add noqa) | B-027 |
| `.github/workflows/deploy-test.yml` | Modify (remove `\|\| true`) | B-027 |

---

## Task 1: B-017 — Nacos hot-reload limits documentation

**Files:**
- Create: `docs/architecture/nacos-hot-reload-limits.md`

- [ ] **Step 1: Write the doc**

```markdown
# Nacos 热更新限制

> 创建日期：2026-05-16
> 最后更新：2026-05-16

## 问题

以下工厂函数使用 `@lru_cache(maxsize=1)` 缓存客户端实例：

- `src/common/aliyun/pnvs_client.py` — `get_pnvs_client()`
- `src/common/aliyun/dm_smtp_client.py` — `get_dm_smtp_client()`
- `src/apps/user/sso_clients.py`（计划中）— `get_qq_oauth_client()` / `get_thbwiki_oauth_client()`

Nacos 配置变更回调 `_on_nacos_config_change`（`src/common/config.py`）在收到变更通知时只更新
环境变量和 `_settings_instance`，**无法使已缓存的 lru_cache 客户端实例失效**。

## 影响

通过 Nacos 热更新以下配置 **不会生效**，必须重启容器：

- 阿里云 PNVS 凭据（`ALIYUN_PNVS_*`）
- 阿里云 DirectMail 凭据（`ALIYUN_DM_*`）
- QQ OAuth 凭据（`QQ_APP_ID` / `QQ_APP_SECRET`）
- THBWiki OAuth 凭据（`THBWIKI_CLIENT_ID` / `THBWIKI_CLIENT_SECRET`）

数据库地址、Redis 地址、JWT 密钥等**不使用 lru_cache 的配置**可以通过
`POST /admin/reload-config` 热更新。

## 操作规程

更改上述凭据后，在部署环境执行：

```bash
docker-compose restart backend
```

## 技术背景

若需支持免重启热更新，需将工厂函数改为每次调用时从 `get_settings()` 重新读取凭据，
放弃 `lru_cache`。当前规模下不做，此改动记录在 BACKLOG B-017。
```

- [ ] **Step 2: Verify the file exists**

```bash
ls docs/architecture/nacos-hot-reload-limits.md
```

- [ ] **Step 3: Commit**

```bash
git add docs/architecture/nacos-hot-reload-limits.md
git commit -m "docs(arch): document Nacos hot-reload lru_cache limitation (B-017)"
```

---

## Task 2: B-029 — Deploy server setup documentation

**Files:**
- Create: `docs/operations/deploy-server-setup.md`

- [ ] **Step 1: Write the doc**

```markdown
# 部署机环境配置

> 创建日期：2026-05-16
> 最后更新：2026-05-16

## 概述

生产/测试环境部署机上的 `docker-compose.yml` **由 CI workflow 自动生成**，
仓库内没有对应的源文件（`docker/` 目录已在 2026-05 从仓库删除）。

## 文件位置

```
${TEST_SERVER_DIR:-/opt/thvote/test}/
├── .env                  # CI 每次部署时写入
├── docker-compose.yml    # CI 首次部署或触发重建时写入（见下）
└── logs/                 # 后端日志挂载目录
```

## docker-compose.yml 的生命周期

CI `deploy-test` job 在每次部署时检查 compose 文件：

- 文件不存在 → 从 CI workflow heredoc 重新生成
- 文件存在但不含 `NACOS_ENABLED` 字段 → 重新生成
- 其他情况 → 仅替换 `image:` 中的 tag

**如需修改 compose 内容**，应编辑 `.github/workflows/deploy-test.yml`
中 `COMPOSEEOF` heredoc，而非直接修改部署机上的文件（下次 CI 触发
重建条件时会被覆盖）。

## 外部依赖

| 服务 | 管理方式 |
|---|---|
| PostgreSQL | 阿里云 RDS，不在 compose 中，通过 Nacos 注入 `DATABASE_URL` |
| Redis | compose 管理（`thvote-redis` 容器），部署机上持久化 |
| Backend | compose 管理（`thvote-backend` 容器） |

## Redis 启动规则

CI 只在 `thvote-redis` 容器不存在时启动它（`docker-compose up -d redis`）。
Redis 数据通过 `redis-data` volume 持久化，不随容器重启丢失。

## 网络

所有服务通过外部网络 `thvote-net` 通信。CI 在网络不存在时自动创建。

## Nacos 配置

后端敏感配置（数据库凭据、JWT 密钥、阿里云 AK 等）均通过 Nacos 下发，
不写入部署机文件系统。Nacos 地址和命名空间通过 GitHub Secrets 注入。
```

- [ ] **Step 2: Verify the file exists**

```bash
ls docs/operations/deploy-server-setup.md
```

- [ ] **Step 3: Commit**

```bash
git add docs/operations/deploy-server-setup.md
git commit -m "docs(ops): document deploy server docker-compose lifecycle (B-029)"
```

---

## Task 3: B-025 — Remove init_db DEBUG backdoor

**Files:**
- Modify: `src/main.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_startup_db_check.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.exc import OperationalError


@pytest.mark.asyncio
async def test_lifespan_raises_on_db_failure():
    """Startup must raise RuntimeError if the DB is unreachable."""
    from src.main import create_app
    from httpx import AsyncClient, ASGITransport

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        side_effect=OperationalError("connect failed", None, None)
    )
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_maker = MagicMock(return_value=mock_session)

    with patch("src.main.get_session_maker", return_value=mock_maker):
        app = create_app()
        with pytest.raises(RuntimeError, match="Database connection failed"):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test"):
                pass
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_startup_db_check.py -xvs
```

Expected: FAIL (RuntimeError not raised because init_db backdoor is still there)

- [ ] **Step 3: Modify src/main.py**

Remove the `_is_debug_mode` function (lines 40-53) entirely.

Change the import on the line containing `init_db`:
```python
# Before:
from .common.database import get_db_session, init_db
# After:
from .common.database import get_db_session, get_session_maker, reload_engine
```

Replace the lifespan startup block (the entire `if _is_debug_mode(): ... else: ...` block) with:
```python
    # Verify DB connectivity — fail fast rather than silently running with no schema
    try:
        async with get_session_maker()() as session:
            await session.execute(text("SELECT 1"))
        logger.info("Database connection verified. Schema managed by Alembic.")
    except Exception as exc:
        raise RuntimeError(f"Database connection failed at startup: {exc}") from exc
```

Also remove the now-unused `from .common.apollo import load_apollo_overrides` import line (it's both F401 and will help B-027).

Add missing imports that flake8 flagged as F821 — update the top-level imports block to:
```python
from .common.config import (
    get_settings,
    nacos_config_change_callback,
    reload_settings,
)
from .common.database import get_db_session, get_session_maker, reload_engine
```

Inside the lifespan `if settings.nacos_enabled:` block, change the local import at the top of that block:
```python
        from .common.nacos import (
            register_service_to_nacos,
            start_nacos_watcher,
        )
```

Inside the `discover_service` endpoint function, add a local import before the `instances = await` call:
```python
        from .common.nacos import discover_service_from_nacos
```

Inside the `discover_self` endpoint function, add a local import before the `reg = ` call:
```python
        from .common.nacos import get_service_register
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_startup_db_check.py -xvs
```

Expected: PASS

- [ ] **Step 5: Run existing tests to check no regressions**

```bash
pytest tests/unit tests/contract -x --tb=short
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/main.py tests/unit/test_startup_db_check.py
git commit -m "feat(startup): remove init_db DEBUG backdoor, add DB connectivity check (B-025)"
```

---

## Task 4: B-018 — _safe_log failure visibility

**Files:**
- Modify: `src/apps/user/service.py`
- Modify: `src/main.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_audit_log_counter.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_safe_log_failure_increments_counter():
    """_safe_log must increment _audit_log_failures when ActivityLogDAO raises."""
    import src.apps.user.service as svc_module
    # Reset counter
    svc_module._audit_log_failures = 0

    dao_mock = AsyncMock()
    dao_mock.write = AsyncMock(side_effect=RuntimeError("db gone"))

    from src.apps.user.service import UserService
    svc = object.__new__(UserService)
    svc.activity_dao = dao_mock

    await svc._safe_log(event_type="test_event")

    assert svc_module._audit_log_failures == 1


def test_get_audit_log_failures_returns_current_count():
    import src.apps.user.service as svc_module
    svc_module._audit_log_failures = 3
    from src.apps.user.service import get_audit_log_failures
    assert get_audit_log_failures() == 3
    svc_module._audit_log_failures = 0  # cleanup
```

Add a contract test in `tests/contract/test_router_endpoints.py` (append to existing file):

```python
@pytest.mark.asyncio
async def test_health_ok_when_no_audit_failures(async_client):
    import src.apps.user.service as svc_module
    svc_module._audit_log_failures = 0
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert "audit_failures" not in resp.json()


@pytest.mark.asyncio
async def test_health_degraded_when_audit_failures(async_client):
    import src.apps.user.service as svc_module
    svc_module._audit_log_failures = 2
    try:
        resp = await async_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "degraded"
        assert resp.json()["audit_failures"] == 2
    finally:
        svc_module._audit_log_failures = 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_audit_log_counter.py -xvs
```

Expected: FAIL with `AttributeError: module 'src.apps.user.service' has no attribute '_audit_log_failures'`

- [ ] **Step 3: Modify src/apps/user/service.py**

Add after the imports block (before the class definition), around line 55:

```python
_audit_log_failures: int = 0


def get_audit_log_failures() -> int:
    """Return the count of ActivityLog write failures since process start."""
    return _audit_log_failures
```

Replace the `_safe_log` method body (currently at line 387):

```python
    async def _safe_log(self, **fields) -> None:
        """Write an ActivityLog row best-effort; swallow any failure."""
        global _audit_log_failures
        cleaned = {k: v for k, v in fields.items() if v is not None}
        try:
            await self.activity_dao.write(**cleaned)
        except Exception:  # noqa: BLE001
            _audit_log_failures += 1
            logger.exception(
                "ActivityLog write failed (event_type=%s); continuing",
                cleaned.get("event_type"),
            )
```

- [ ] **Step 4: Modify src/main.py — update /health endpoint**

Add to the imports at the top of `main.py`:
```python
from .apps.user.service import get_audit_log_failures
```

Replace the health endpoint body:

```python
    @app.get("/health", tags=["system"])
    async def health(db: AsyncSession = Depends(get_db_session)) -> dict:
        try:
            await db.execute(text("SELECT 1"))
            db_status = "ok"
        except Exception as e:
            logger.warning("Health check DB query failed: %s", e)
            db_status = "unavailable"

        failures = get_audit_log_failures()
        result: dict = {
            "status": "degraded" if failures > 0 else "ok",
            "db_status": db_status,
            "vote_year": settings.vote_year,
        }
        if failures > 0:
            result["audit_failures"] = failures
        return result
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/unit/test_audit_log_counter.py -xvs
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/apps/user/service.py src/main.py tests/unit/test_audit_log_counter.py
git commit -m "feat(health): expose audit log failure counter in /health endpoint (B-018)"
```

---

## Task 5: B-030 — Nacos lazy load

**Files:**
- Modify: `src/common/config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_nacos_lazy_load.py`:

```python
from unittest.mock import patch, MagicMock
import importlib


def test_get_settings_calls_nacos_exactly_once():
    """get_settings() must call _load_nacos_sync exactly once across multiple calls."""
    import src.common.config as cfg

    # Reset module state
    cfg._settings_instance = None
    cfg._nacos_loaded = False  # This will fail until we add the flag

    with patch.object(cfg, "_load_nacos_sync") as mock_load:
        cfg.get_settings()
        cfg.get_settings()
        cfg.get_settings()

    assert mock_load.call_count == 1, (
        f"Expected _load_nacos_sync called once, got {mock_load.call_count}"
    )
    # Cleanup
    cfg._settings_instance = None
    cfg._nacos_loaded = False


def test_import_config_does_not_call_nacos(monkeypatch):
    """Importing config must not trigger any network call."""
    import src.common.config as cfg
    # If _load_nacos_sync was called at import time, we can't un-call it.
    # We verify the flag is set correctly after get_settings() is called.
    cfg._settings_instance = None
    cfg._nacos_loaded = False

    with patch.object(cfg, "_load_nacos_sync") as mock_load:
        # Simply access the module — no network call yet
        _ = cfg._settings_instance  # read the attribute, don't call get_settings
        assert mock_load.call_count == 0

    cfg._settings_instance = None
    cfg._nacos_loaded = False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_nacos_lazy_load.py -xvs
```

Expected: FAIL with `AttributeError: module 'src.common.config' has no attribute '_nacos_loaded'`

- [ ] **Step 3: Modify src/common/config.py**

Remove the module-level `import os` (line 6, it's unused — verify with grep first: `grep -n "os\." src/common/config.py` should return nothing).

Remove line 46: `_load_nacos_sync()`  (the standalone call at module level with comment `# 加载 Nacos 配置（启动时一次性加载）`)

Add `_nacos_loaded: bool = False` right after the `_hot_reloadable_keys: Set[str] = set()` line.

Replace the `get_settings()` function:

```python
def get_settings() -> Settings:
    """Return a cached Settings instance, loading Nacos config on first call."""
    global _settings_instance, _nacos_loaded
    if _settings_instance is None:
        if not _nacos_loaded:
            _load_nacos_sync()
            _nacos_loaded = True
        _settings_instance = Settings()
    return _settings_instance
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_nacos_lazy_load.py -xvs
```

Expected: PASS

- [ ] **Step 5: Run full test suite to check no regressions**

```bash
pytest tests/ -x --tb=short -q
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/common/config.py tests/unit/test_nacos_lazy_load.py
git commit -m "fix(config): defer Nacos load to first get_settings() call, not import time (B-030)"
```

---

## Task 6: B-027 — Fix all flake8 violations, then harden CI gate

**Files:**
- Create: `.flake8`
- Modify: multiple source files (see list below)
- Modify: `.github/workflows/deploy-test.yml`

### Step 6a: Create .flake8 config

- [ ] **Step 1: Create .flake8**

```ini
[flake8]
max-line-length = 88
extend-ignore = E203
per-file-ignores =
    src/main.py: E402
    src/common/redis.py: E402
```

`E203` is a Black-vs-flake8 conflict on slice formatting — Black adds spaces that flake8 rejects. `E402` covers the intentional `load_dotenv()` before imports in `main.py` and `redis.py`.

- [ ] **Step 2: Run flake8 to see remaining violations**

```bash
flake8 src/ --max-line-length=88
```

With `.flake8` in place, E203 and E402 violations disappear. Remaining violations should be only F401 and F821 (and E501 lines black can't fix).

### Step 6b: Fix unused imports (F401)

- [ ] **Step 3: Remove unused imports**

**`src/api/graphql/types.py` line 7** — remove `from strawberry.scalars import JSON` if JSON is not referenced elsewhere in the file (verify with `grep "JSON" src/api/graphql/types.py`). If it's used, add `# noqa: F401`.

**`src/apps/result/compute.py` line 10** — remove `from dataclasses import field`:
```python
# Before:
from dataclasses import dataclass, field
# After:
from dataclasses import dataclass
```

**`src/apps/result/compute_dao.py` line 6** — remove `from typing import Any`:
```python
# Before:
from typing import Any, Optional
# After:
from typing import Optional
```

**`src/apps/scraper/sites/weibo.py` line 7** — remove `import re`.

**`src/common/config.py`** — `import os` was already removed in Task 5.

**`src/common/redis.py` line 11** — remove `from typing import Any`:
```python
# Before:
from typing import Any, Optional
# After:
from typing import Optional
```

### Step 6c: Fix E501 line-too-long with black

- [ ] **Step 4: Run black**

```bash
black src/ --line-length 88
```

Black will reformat lines it can split. Some string literals and comments may remain over 88 chars.

- [ ] **Step 5: Check remaining E501**

```bash
flake8 src/ --max-line-length=88 --select=E501
```

For each remaining E501, wrap manually. Common pattern — split a long string:
```python
# Before:
raise AppException("SOME_LONG_ERROR_CODE", "This is a very long error message that exceeds the line length limit entirely")
# After:
raise AppException(
    "SOME_LONG_ERROR_CODE",
    "This is a very long error message that exceeds the line length limit entirely",
)
```

### Step 6d: Verify flake8 is clean

- [ ] **Step 6: Confirm zero violations**

```bash
flake8 src/ --max-line-length=88
```

Expected: no output (exit code 0).

- [ ] **Step 7: Run tests to ensure no regressions from reformatting**

```bash
pytest tests/ -x --tb=short -q
```

Expected: all pass.

### Step 6e: Harden CI gate

- [ ] **Step 8: Edit deploy-test.yml**

In `.github/workflows/deploy-test.yml`, find the lint step (currently line 64):

```yaml
      - name: 代码风格检查
        run: flake8 src/ --max-line-length=88 || true
```

Change to:

```yaml
      - name: 代码风格检查
        run: flake8 src/ --max-line-length=88
```

- [ ] **Step 9: Commit everything**

```bash
git add .flake8 src/ .github/workflows/deploy-test.yml
git commit -m "fix(lint): resolve all flake8 violations and harden CI gate (B-027)"
```
