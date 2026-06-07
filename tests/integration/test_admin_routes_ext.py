"""Integration tests for admin panel extensions."""
import os

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
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
    """Create FastAPI app with in-memory SQLite overriding DB + Redis deps."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

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
    # Reset cached settings so our env var is picked up
    import src.common.config as cfg
    cfg._settings_instance = None
    yield secret
    cfg._settings_instance = None


@pytest.mark.asyncio
async def test_search_users_by_email(app, db_session, admin_secret):
    await db_session.execute(
        text(
            "INSERT INTO \"user\" (id, email, email_verified, phone_verified, removed, register_ip_address) "
            "VALUES ('aaa', 'find@example.com', 1, 0, 0, '')"
        )
    )
    await db_session.commit()

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
    await db_session.execute(
        text(
            "INSERT INTO \"user\" (id, email, email_verified, phone_verified, removed, register_ip_address) "
            "VALUES ('bbb', 'ban@example.com', 1, 0, 0, '')"
        )
    )
    await db_session.commit()

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
    await db_session.execute(
        text(
            "INSERT INTO \"user\" (id, email, email_verified, phone_verified, removed, register_ip_address) "
            "VALUES ('ccc', 'detail@example.com', 1, 0, 0, '')"
        )
    )
    await db_session.commit()

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
async def test_export_votes_csv(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/admin/export/votes?vote_year=2024&category=character",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert resp.text.startswith("vote_id,attempt,")
