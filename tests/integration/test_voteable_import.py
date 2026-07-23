"""Integration tests: VoteableImportService + POST /admin/voteables/import.

Fixture layout copied from the top of test_candidate_admin.py (app override +
sqlite in-memory session), per task-4-brief Step 1.
"""
from __future__ import annotations

import json
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


ROWS = [
    {"name": "博丽灵梦", "name_jp": "博麗　霊夢", "type": "old",
     "old_id": "4068b1c2", "work": "东方红魔乡", "sort_order": 0},
    {"name": "新角色", "type": "new", "work": "新作品X", "work_type": "new",
     "sort_order": 1},
]


def _body(rows, dry_run=True, vote_year=12):
    return {"category": "character", "vote_year": vote_year,
            "format": "json", "content": json.dumps(rows), "dry_run": dry_run}


async def _post(app, admin_secret, body):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        return await ac.post(
            "/api/v1/admin/voteables/import", json=body,
            headers={"X-Admin-Secret": admin_secret},
        )


@pytest.mark.asyncio
async def test_dry_run_reports_create_without_writing(app, db_session, admin_secret):
    resp = await _post(app, admin_secret, _body(ROWS, dry_run=True))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["create"]) == 2
    work_names = {w["name"] for w in data["work_created"]}
    assert work_names == {"东方红魔乡", "新作品X"}

    count = (await db_session.execute(
        text("SELECT COUNT(*) FROM voteable_character")
    )).scalar_one()
    assert count == 0
    work_count = (await db_session.execute(
        text("SELECT COUNT(*) FROM work")
    )).scalar_one()
    assert work_count == 0


@pytest.mark.asyncio
async def test_execute_creates_and_is_idempotent(app, db_session, admin_secret):
    resp = await _post(app, admin_secret, _body(ROWS, dry_run=False))
    assert resp.status_code == 200
    first = resp.json()
    assert len(first["create"]) == 2
    assert first["candidate_upserts"] == 2

    resp2 = await _post(app, admin_secret, _body(ROWS, dry_run=True))
    assert resp2.status_code == 200
    second = resp2.json()
    assert second["create"] == []
    assert second["update"] == []

    old_id = (await db_session.execute(
        text("SELECT old_id FROM voteable_character WHERE name='博丽灵梦'")
    )).scalar_one()
    assert old_id == "4068b1c2"

    sort_order = (await db_session.execute(
        text(
            "SELECT sort_order FROM candidate_character cc "
            "JOIN voteable_character vc ON vc.id = cc.voteable_id "
            "WHERE vc.name = '博丽灵梦' AND cc.vote_year = 12"
        )
    )).scalar_one()
    assert sort_order == 0


@pytest.mark.asyncio
async def test_match_priority_old_id_then_name(app, admin_secret):
    first_row = [{"name": "A", "old_id": "abc123", "sort_order": 0}]
    resp = await _post(app, admin_secret, _body(first_row, dry_run=False))
    assert resp.status_code == 200

    renamed_row = [{"name": "B", "old_id": "abc123", "sort_order": 0}]
    resp2 = await _post(app, admin_secret, _body(renamed_row, dry_run=True))
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["totals"]["matched_by_old_id"] == 1
    assert data["update"], "expected an update entry"
    assert "name" in data["update"][0]["diff"]
    assert data["update"][0]["diff"]["name"] == "B"


@pytest.mark.asyncio
async def test_conflict_batch_rejected(app, db_session, admin_secret):
    seed_row = [{"name": "X", "old_id": "seed-old-id", "sort_order": 0}]
    resp = await _post(app, admin_secret, _body(seed_row, dry_run=False))
    assert resp.status_code == 200

    conflicting_row = [{"name": "X", "old_id": "different-old-id", "sort_order": 0}]
    dry_resp = await _post(app, admin_secret, _body(conflicting_row, dry_run=True))
    assert dry_resp.status_code == 200
    assert dry_resp.json()["conflicts"]

    exec_resp = await _post(app, admin_secret, _body(conflicting_row, dry_run=False))
    assert exec_resp.status_code in (400, 409)

    old_id = (await db_session.execute(
        text("SELECT old_id FROM voteable_character WHERE name='X'")
    )).scalar_one()
    assert old_id == "seed-old-id"
    count = (await db_session.execute(
        text("SELECT COUNT(*) FROM voteable_character")
    )).scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_vote_year_none_skips_candidate(app, db_session, admin_secret):
    body = _body(ROWS, dry_run=False, vote_year=None)
    resp = await _post(app, admin_secret, body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["candidate_upserts"] == 0

    voteable_count = (await db_session.execute(
        text("SELECT COUNT(*) FROM voteable_character")
    )).scalar_one()
    assert voteable_count == 2
    candidate_count = (await db_session.execute(
        text("SELECT COUNT(*) FROM candidate_character")
    )).scalar_one()
    assert candidate_count == 0


@pytest.mark.asyncio
async def test_duplicate_name_within_batch_is_conflict(app, admin_secret):
    dup_rows = [{"name": "重复名"}, {"name": "重复名"}]
    resp = await _post(app, admin_secret, _body(dup_rows, dry_run=True))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["conflicts"]) >= 1


@pytest.mark.asyncio
async def test_csv_format_parses_aliases_and_creates(app, db_session, admin_secret):
    csv_content = (
        "name,aliases,work\n"
        "咲夜,十六夜咲夜;完美管家\n"
        "帕秋莉,,红魔乡\n"
    )
    body = {"category": "character", "vote_year": None, "format": "csv",
            "content": csv_content, "dry_run": False}
    resp = await _post(app, admin_secret, body)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["create"]) == 2

    aliases = (await db_session.execute(
        text("SELECT aliases FROM voteable_character WHERE name='咲夜'")
    )).scalar_one()
    assert json.loads(aliases) == ["十六夜咲夜", "完美管家"]


@pytest.mark.asyncio
async def test_json_parse_error_returns_400(app, admin_secret):
    body = {"category": "character", "vote_year": None, "format": "json",
            "content": "{\"not\": \"a list\"}", "dry_run": True}
    resp = await _post(app, admin_secret, body)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_non_integer_voteable_id_returns_400(app, admin_secret):
    rows = [{"name": "X", "voteable_id": "not-a-number"}]
    resp = await _post(app, admin_secret, _body(rows, dry_run=True))
    assert resp.status_code == 400
