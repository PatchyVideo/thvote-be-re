"""Shared fixtures for contract tests."""
from __future__ import annotations

import os

import pytest
import pytest_asyncio

try:
    import fakeredis.aioredis as fakeredis_aioredis
    FakeRedis = fakeredis_aioredis.FakeRedis
except ImportError:
    import fakeredis
    FakeRedis = fakeredis.aioredis.FakeRedis


@pytest_asyncio.fixture
async def app():
    """FastAPI app with in-memory SQLite + fakeredis dependency overrides."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from src.db_model.base import Base
    from src.common.database import get_db_session
    from src.common.redis import get_redis
    from src.main import create_app

    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(bind=eng, class_=AsyncSession, expire_on_commit=False)

    fake_redis_instance = FakeRedis(decode_responses=True)

    async def _override_get_db():
        async with maker() as session:
            yield session

    async def _override_get_redis():
        return fake_redis_instance

    a = create_app()
    a.dependency_overrides[get_db_session] = _override_get_db
    a.dependency_overrides[get_redis] = _override_get_redis

    yield a

    await eng.dispose()


@pytest.fixture
def admin_secret():
    """Set ADMIN_SECRET env var and reset cached settings so the value is picked up."""
    import src.common.config as cfg

    original = os.environ.get("ADMIN_SECRET")
    secret = original or "test-admin-secret"
    os.environ["ADMIN_SECRET"] = secret
    cfg._settings_instance = None
    yield secret
    # Restore original state so later tests that don't use this fixture
    # are not affected by a lingering ADMIN_SECRET in the environment.
    if original is None:
        del os.environ["ADMIN_SECRET"]
    else:
        os.environ["ADMIN_SECRET"] = original
    cfg._settings_instance = None
