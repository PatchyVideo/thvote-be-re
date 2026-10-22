"""Integration tests for admin panel extensions."""
import os

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.common.redis import get_redis as _ORIGINAL_GET_REDIS
from src.db_model.base import Base
from tests.helpers.users import make_user


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
async def app(engine, patch_redis):
    """Create FastAPI app with in-memory SQLite overriding DB + Redis deps."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from src.common.database import get_db_session
    from src.common.redis import get_redis
    from src.main import create_app

    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db():
        async with maker() as s:
            yield s

    # 复用 conftest autouse patch_redis 的 FakeRedis（同一次测试内共享）。
    async def _override_get_redis():
        return patch_redis

    a = create_app()
    a.dependency_overrides[get_db_session] = _override_get_db
    # 覆盖所有 router 在 import 时捕获的 get_redis 函数对象。
    # conftest 的 autouse patch_redis 只 monkeypatch 模块属性，而
    # `Depends(get_redis)` 在 import 时已绑定对象，故必须逐个覆盖。
    import importlib

    import src.common.redis as redis_module

    override_targets = {redis_module.get_redis, _ORIGINAL_GET_REDIS}
    for modname in (
        "src.apps.vote_objects.router",
        "src.apps.admin.router",
        "src.apps.admin.monitor.router",
        "src.apps.autocomplete.router",
        "src.apps.questionnaire.router",
        "src.apps.questionnaire.admin_router",
        "src.apps.result.router",
        "src.apps.submit.router",
        "src.apps.user.router",
        "src.apps.user.deps",
        "src.common.middleware.rate_limit",
    ):
        try:
            mod = importlib.import_module(modname)
        except Exception:
            continue
        dep = getattr(mod, "get_redis", None)
        if dep is not None:
            override_targets.add(dep)
    for dep in override_targets:
        a.dependency_overrides[dep] = _override_get_redis
    yield a


@pytest.fixture
def admin_secret():
    secret = os.environ.get("ADMIN_SECRET", "test-admin-secret")
    os.environ["ADMIN_SECRET"] = secret
    # Reset cached settings so our env var is picked up
    import src.common.config as cfg
    cfg._settings_instance = None
    yield secret
    cfg._settings_instance = None


@pytest.mark.asyncio
async def test_search_users_by_email(app, db_session, admin_secret):
    await make_user(db_session, user_id="aaa", email="find@example.com", register_ip="")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/admin/users?email=find@example.com",
            headers={"X-Admin-Secret": admin_secret},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] >= 1
    assert any(u["email"] == "find@example.com" for u in data["items"])


@pytest.mark.asyncio
async def test_ban_and_unban_user(app, db_session, admin_secret):
    await make_user(db_session, user_id="bbb", email="ban@example.com", register_ip="")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            "/api/v1/admin/users/bbb/ban",
            headers={"X-Admin-Secret": admin_secret},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["removed"] is True

        resp = await ac.patch(
            "/api/v1/admin/users/bbb/unban",
            headers={"X-Admin-Secret": admin_secret},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["removed"] is False


@pytest.mark.asyncio
async def test_get_user_detail(app, db_session, admin_secret):
    await make_user(db_session, user_id="ccc", email="detail@example.com", register_ip="")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/admin/users/ccc",
            headers={"X-Admin-Secret": admin_secret},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["user"]["id"] == "ccc"
    assert "vote_submitted" in data


@pytest.mark.asyncio
async def test_stats_shape(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/admin/stats", headers={"X-Admin-Secret": admin_secret})
    assert resp.status_code == 200
    data = resp.json()
    assert "total_users" in data
    assert "submissions" in data
    assert "character" in data["submissions"]
    assert data["vote_window"]["status"] in ("open", "closed", "upcoming")


@pytest.mark.asyncio
async def test_list_candidates_empty(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/admin/candidates?category=character&vote_year=2024",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_activity_logs_empty(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/admin/activity-logs",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_activity_logs_bad_since_returns_400(app, admin_secret):
    """Regression: an unparsable `since` used to blow up datetime.fromisoformat
    into an unhandled 500; it must now be a clean 400 (INVALID_SINCE_FORMAT)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/admin/activity-logs?since=not-a-date",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_export_votes_csv(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/admin/export/votes?vote_year=2024&category=character",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert resp.text.startswith("vote_id,attempt,")
