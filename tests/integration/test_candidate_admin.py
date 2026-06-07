"""Integration tests for candidate admin: DAO update + endpoints."""
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


# ── DAO: update_candidate ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_candidate_ok(db_session):
    from src.apps.result.compute_dao import ComputeDAO

    await db_session.execute(text(
        "INSERT INTO candidate_character (vote_year, name, name_jp, origin, type) "
        "VALUES (2026, '灵梦', '霊夢', '红魔乡', 'human')"
    ))
    await db_session.commit()
    row_id = (await db_session.execute(
        text("SELECT id FROM candidate_character WHERE name='灵梦'")
    )).scalar_one()

    dao = ComputeDAO(db_session)
    result = await dao.update_candidate(
        row_id, "character", {"name_jp": "博麗霊夢", "type": "shrine"}
    )
    assert result == "ok"

    name_jp = (await db_session.execute(
        text("SELECT name_jp FROM candidate_character WHERE id=:i"), {"i": row_id}
    )).scalar_one()
    assert name_jp == "博麗霊夢"


@pytest.mark.asyncio
async def test_update_candidate_not_found(db_session):
    from src.apps.result.compute_dao import ComputeDAO

    dao = ComputeDAO(db_session)
    assert await dao.update_candidate(999999, "character", {"name": "x"}) == "not_found"


@pytest.mark.asyncio
async def test_update_candidate_name_conflict(db_session):
    from src.apps.result.compute_dao import ComputeDAO

    await db_session.execute(text(
        "INSERT INTO candidate_character (vote_year, name) VALUES (2026, '灵梦')"
    ))
    await db_session.execute(text(
        "INSERT INTO candidate_character (vote_year, name) VALUES (2026, '魔理沙')"
    ))
    await db_session.commit()
    rid = (await db_session.execute(
        text("SELECT id FROM candidate_character WHERE name='魔理沙'")
    )).scalar_one()

    dao = ComputeDAO(db_session)
    assert await dao.update_candidate(rid, "character", {"name": "灵梦"}) == "conflict"


# ── Endpoints ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fields_endpoint(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/admin/candidates/fields?category=character",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 200
    data = resp.json()
    names = {f["name"]: f["required"] for f in data["fields"]}
    assert names["name"] is True
    assert names["name_jp"] is False


@pytest.mark.asyncio
async def test_import_dry_run_then_commit(app, admin_secret):
    payload = {
        "vote_year": 2030, "category": "character", "format": "auto",
        "content": '[{"name":"灵梦","name_jp":"霊夢"},{"type":"human"}]',
        "dry_run": True,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r1 = await ac.post("/api/v1/admin/candidates/import", json=payload,
                           headers={"X-Admin-Secret": admin_secret})
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["valid_count"] == 1
        assert d1["imported"] == 0
        assert len(d1["rejected"]) == 1

        payload["dry_run"] = False
        r2 = await ac.post("/api/v1/admin/candidates/import", json=payload,
                           headers={"X-Admin-Secret": admin_secret})
        assert r2.status_code == 200
        assert r2.json()["imported"] == 1

        r3 = await ac.get(
            "/api/v1/admin/candidates?category=character&vote_year=2030",
            headers={"X-Admin-Secret": admin_secret},
        )
        assert r3.json()["total"] == 1


@pytest.mark.asyncio
async def test_import_parse_error(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/admin/candidates/import", json={
            "vote_year": 2030, "category": "character",
            "format": "json", "content": '{"not":"array"}', "dry_run": True,
        }, headers={"X-Admin-Secret": admin_secret})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_edit_endpoint_conflict(app, db_session, admin_secret):
    await db_session.execute(text(
        "INSERT INTO candidate_character (vote_year, name) VALUES (2031, 'A')"
    ))
    await db_session.execute(text(
        "INSERT INTO candidate_character (vote_year, name) VALUES (2031, 'B')"
    ))
    await db_session.commit()
    rid = (await db_session.execute(
        text("SELECT id FROM candidate_character WHERE name='B' AND vote_year=2031")
    )).scalar_one()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.put(f"/api/v1/admin/candidates/{rid}",
                            json={"category": "character", "fields": {"name": "A"}},
                            headers={"X-Admin-Secret": admin_secret})
    assert resp.status_code == 409
