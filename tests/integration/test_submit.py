"""Integration tests for submit endpoints using SQLite + fakeredis."""

import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-do-not-use-in-prod")
os.environ.setdefault("VOTE_START_ISO", "2020-01-01T00:00:00+00:00")
os.environ.setdefault("VOTE_END_ISO", "2099-12-31T23:59:59+00:00")

from src.common.security.jwt import create_vote_token
from src.db_model.base import Base
from src.main import create_app


def _make_vote_token(user_id: str = "user-test-001") -> str:
    now = datetime.now(timezone.utc)
    return create_vote_token(user_id, now - timedelta(hours=1), now + timedelta(days=30))


@pytest_asyncio.fixture
async def client():
    app = create_app()

    # Use in-memory SQLite
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_db():
        async with maker() as s:
            yield s

    from src.common.database import get_db_session
    app.dependency_overrides[get_db_session] = _override_db

    # Patch Redis with fakeredis
    try:
        import fakeredis.aioredis as fakeredis
        fake_redis = fakeredis.FakeRedis(decode_responses=True)
    except ImportError:
        import fakeredis
        fake_redis = fakeredis.FakeRedis(decode_responses=True)

    with patch("src.common.middleware.rate_limit.get_redis_client", return_value=fake_redis), \
         patch("src.apps.submit.router.get_redis_client", return_value=fake_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c

    await engine.dispose()


@pytest.mark.asyncio
async def test_submit_character_no_token(client):
    resp = await client.post("/api/v1/character/", json={
        "characters": [{"id": "博丽灵梦"}],
        "meta": {}
    })
    assert resp.status_code == 401
    assert resp.json()["detail"] == "VOTE_TOKEN_REQUIRED"


@pytest.mark.asyncio
async def test_submit_character_invalid_token(client):
    resp = await client.post("/api/v1/character/", json={
        "characters": [{"id": "博丽灵梦"}],
        "meta": {"vote_token": "totally.invalid.token"}
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_submit_character_ok(client):
    token = _make_vote_token()
    resp = await client.post("/api/v1/character/", json={
        "characters": [{"id": "博丽灵梦", "first": True, "reason": "最喜欢"}],
        "meta": {"vote_token": token}
    })
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_submit_paper_ok(client):
    token = _make_vote_token("user-paper-001")
    papers = json.dumps([{"id": 1, "answer": [1]}, {"id": 2, "answer_str": "男"}])
    resp = await client.post("/api/v1/paper/", json={
        "papers_json": papers,
        "meta": {"vote_token": token}
    })
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_submit_paper_invalid_json(client):
    token = _make_vote_token("user-paper-002")
    resp = await client.post("/api/v1/paper/", json={
        "papers_json": "{not valid}",
        "meta": {"vote_token": token}
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_voting_status_after_submit(client):
    token = _make_vote_token("user-status-001")
    vote_id = "thvote-2026-test-status-001"
    # Submit character
    await client.post("/api/v1/character/", json={
        "characters": [{"id": "博丽灵梦"}],
        "meta": {"vote_token": token, "vote_id": vote_id}
    })
    # Check status
    resp = await client.post("/api/v1/voting-status/", json={"vote_id": vote_id})
    assert resp.status_code == 200
    data = resp.json()
    assert data["characters"] is True
    assert data["musics"] is False


@pytest.mark.asyncio
async def test_statistics_num_finished_paper(client):
    token = _make_vote_token("user-stat-paper-001")
    papers = json.dumps([{"id": 1, "answer": [1]}])
    vote_id = "thvote-2026-stat-paper-001"
    await client.post("/api/v1/paper/", json={
        "papers_json": papers,
        "meta": {"vote_token": token, "vote_id": vote_id}
    })
    resp = await client.post("/api/v1/voting-statistics/", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["num_finished_paper"] >= 1
