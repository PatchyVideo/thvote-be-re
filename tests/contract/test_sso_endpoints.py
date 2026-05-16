"""Contract tests: SSO endpoints return correct status codes."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

try:
    import fakeredis.aioredis as fakeredis_aioredis
    FakeRedis = fakeredis_aioredis.FakeRedis
except ImportError:
    import fakeredis
    FakeRedis = fakeredis.aioredis.FakeRedis


@pytest_asyncio.fixture
async def async_client():
    """Create an ASGI test client with fakeredis and in-memory SQLite."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from src.db_model.base import Base
    from src.common.database import get_db_session
    from src.common.redis import get_redis
    from src.main import create_app

    # In-memory SQLite engine
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(bind=eng, class_=AsyncSession, expire_on_commit=False)

    # Fakeredis instance
    fake_redis_instance = FakeRedis(decode_responses=True)

    async def _override_get_db():
        async with maker() as session:
            yield session

    async def _override_get_redis():
        return fake_redis_instance

    app = create_app()
    app.dependency_overrides[get_db_session] = _override_get_db
    app.dependency_overrides[get_redis] = _override_get_redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    await eng.dispose()


@pytest.mark.asyncio
async def test_qq_authorize_503_when_not_configured(async_client):
    """GET /user/sso/qq/authorize must return 503 when QQ_APP_ID is unset."""
    resp = await async_client.get(
        "/api/v1/user/sso/qq/authorize", follow_redirects=False
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_thbwiki_authorize_503_when_not_configured(async_client):
    resp = await async_client.get(
        "/api/v1/user/sso/thbwiki/authorize", follow_redirects=False
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_qq_bind_requires_session_token(async_client):
    """POST /user/sso/qq/bind must return 401 without a valid session token."""
    resp = await async_client.post(
        "/api/v1/user/sso/qq/bind",
        json={"code": "test_code", "user_token": ""},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_thbwiki_bind_requires_session_token(async_client):
    resp = await async_client.post(
        "/api/v1/user/sso/thbwiki/bind",
        json={"code": "test_code", "user_token": ""},
    )
    assert resp.status_code == 401
