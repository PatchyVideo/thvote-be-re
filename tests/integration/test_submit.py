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
    # vote gate: must complete questionnaire first
    await client.post("/api/v1/paper/", json={
        "papers_json": "{}",
        "meta": {"vote_token": token}
    })
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
    # vote gate: complete questionnaire first
    await client.post("/api/v1/paper/", json={
        "papers_json": "{}",
        "meta": {"vote_token": token}
    })
    # Submit character
    await client.post("/api/v1/character/", json={
        "characters": [{"id": "博丽灵梦"}],
        "meta": {"vote_token": token}
    })
    # Check status: read-back is scoped by the vote_token, never by a raw vote_id
    resp = await client.post("/api/v1/voting-status/", json={"vote_token": token})
    assert resp.status_code == 200
    data = resp.json()
    assert data["characters"] is True
    assert data["musics"] is False


READBACK_ROUTES = [
    "/api/v1/get-character/",
    "/api/v1/get-music/",
    "/api/v1/get-cp/",
    "/api/v1/get-paper/",
    "/api/v1/get-dojin/",
    "/api/v1/voting-status/",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("route", READBACK_ROUTES)
async def test_readback_rejects_raw_vote_id_without_token(client, route):
    """A bare vote_id must never be enough to read someone's submission."""
    resp = await client.post(route, json={"vote_id": "user-test-001"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "VOTE_TOKEN_REQUIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize("route", READBACK_ROUTES)
async def test_readback_rejects_invalid_token(client, route):
    resp = await client.post(route, json={"vote_token": "totally.invalid.token"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_readback_is_scoped_to_token_user(client):
    """Another user's token cannot read my submission, even if it names my vote_id."""
    owner = _make_vote_token("user-owner-001")
    other = _make_vote_token("user-other-001")
    await client.post("/api/v1/paper/", json={
        "papers_json": "{}", "meta": {"vote_token": owner}
    })
    await client.post("/api/v1/character/", json={
        "characters": [{"id": "博丽灵梦"}], "meta": {"vote_token": owner}
    })

    mine = await client.post("/api/v1/get-character/", json={"vote_token": owner})
    assert mine.status_code == 200
    assert [c["id"] for c in mine.json()["characters"]] == ["博丽灵梦"]

    theirs = await client.post(
        "/api/v1/get-character/",
        json={"vote_token": other, "vote_id": "user-owner-001"},
    )
    assert theirs.status_code == 200
    assert theirs.json()["characters"] == []

    status = await client.post(
        "/api/v1/voting-status/",
        json={"vote_token": other, "vote_id": "user-owner-001"},
    )
    assert status.json()["characters"] is False


@pytest.mark.asyncio
async def test_submit_binds_vote_id_to_token_not_client_value(client):
    """A client-supplied meta.vote_id must not let a token holder write as someone else."""
    attacker = _make_vote_token("user-attacker-001")
    victim = _make_vote_token("user-victim-001")
    await client.post("/api/v1/paper/", json={
        "papers_json": "{}",
        "meta": {"vote_token": attacker, "vote_id": "user-victim-001"},
    })
    resp = await client.post("/api/v1/character/", json={
        "characters": [{"id": "雾雨魔理沙"}],
        "meta": {"vote_token": attacker, "vote_id": "user-victim-001"},
    })
    assert resp.status_code == 200

    as_victim = await client.post("/api/v1/voting-status/", json={"vote_token": victim})
    assert as_victim.json() == {
        "characters": False, "musics": False, "cps": False, "papers": False, "dojin": False
    }
    as_attacker = await client.post("/api/v1/get-character/", json={"vote_token": attacker})
    assert [c["id"] for c in as_attacker.json()["characters"]] == ["雾雨魔理沙"]


@pytest.mark.asyncio
async def test_statistics_num_finished_paper(client):
    token = _make_vote_token("user-stat-paper-001")
    papers = json.dumps([{"id": 1, "answer": [1]}])
    await client.post("/api/v1/paper/", json={
        "papers_json": papers,
        "meta": {"vote_token": token}
    })
    resp = await client.post("/api/v1/voting-statistics/", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["num_finished_paper"] >= 1
