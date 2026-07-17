"""HTTP-level regression tests for require_admin's fail-closed behavior (B-049).

Covers the core gap the review flagged: unset ADMIN_SECRET must 403 (fail-closed),
wrong secret must 403, an IP not in a non-empty ADMIN_ALLOWED_IPS must 403, and an
empty allowlist must not block a request that already carries the right secret.
Also covers the second router gated by require_admin (questionnaire admin CRUD).
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
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
async def app(engine):
    """Create FastAPI app with in-memory SQLite overriding DB + Redis deps."""
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


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_admin_403_when_secret_unset(app, monkeypatch):
    monkeypatch.delenv("ADMIN_SECRET", raising=False)
    import src.common.config as cfg
    monkeypatch.setattr(cfg, "_settings_instance", None)

    async with _client(app) as ac:
        resp = await ac.get("/api/v1/admin/users")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_403_wrong_secret(app, monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET", "right")
    import src.common.config as cfg
    monkeypatch.setattr(cfg, "_settings_instance", None)

    async with _client(app) as ac:
        resp = await ac.get(
            "/api/v1/admin/users",
            headers={"X-Admin-Secret": "wrong"},
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_403_ip_not_in_allowlist(app, monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET", "s")
    monkeypatch.setenv("ADMIN_ALLOWED_IPS", '["9.9.9.9"]')
    import src.common.config as cfg
    monkeypatch.setattr(cfg, "_settings_instance", None)

    async with _client(app) as ac:
        resp = await ac.get(
            "/api/v1/admin/users",
            headers={"X-Admin-Secret": "s"},
        )

    # httpx's ASGITransport client IP is 127.0.0.1, which is not in the allowlist.
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_200ish_with_secret_empty_allowlist(app, monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET", "s")
    monkeypatch.delenv("ADMIN_ALLOWED_IPS", raising=False)
    import src.common.config as cfg
    monkeypatch.setattr(cfg, "_settings_instance", None)

    async with _client(app) as ac:
        resp = await ac.get(
            "/api/v1/admin/users",
            headers={"X-Admin-Secret": "s"},
        )

    # Empty allowlist -> IP check skipped; correct secret -> clean 200 from a
    # fresh in-memory DB (empty user list), not blocked by auth.
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_questionnaire_admin_403_when_secret_unset(app, monkeypatch):
    monkeypatch.delenv("ADMIN_SECRET", raising=False)
    import src.common.config as cfg
    monkeypatch.setattr(cfg, "_settings_instance", None)

    async with _client(app) as ac:
        resp = await ac.get("/api/v1/admin/questionnaires")

    assert resp.status_code == 403
