"""Integration + contract tests for /vote-objects/* (B-040)."""
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
    yield a, maker


async def _seed_work_and_voteable(session):
    """Helper: create work + voteable_character + candidate in new schema."""
    await session.execute(text("INSERT INTO work (id, name, type) VALUES (1, '红魔乡', 'new')"))
    await session.execute(text(
        "INSERT INTO voteable_character (id, name, work_id) VALUES (10, '灵梦', 1)"
    ))
    await session.execute(text(
        "INSERT INTO voteable_character (id, name, work_id) VALUES (11, '魔理沙', 1)"
    ))
    await session.execute(text(
        "INSERT INTO voteable_character (id, name, work_id) VALUES (12, '博丽灵梦', 1)"
    ))
    await session.execute(text(
        "INSERT INTO voteable_music (id, name, work_id) VALUES (20, '曲A', 1)"
    ))
    await session.commit()


@pytest.mark.asyncio
async def test_characters_grouped_by_work(app):
    a, maker = app
    async with maker() as s:
        await _seed_work_and_voteable(s)
        # candidate rows reference voteable
        await s.execute(text(
            "INSERT INTO candidate_character (vote_year, voteable_id) VALUES (2026, 10)"
        ))
        await s.execute(text(
            "INSERT INTO candidate_character (vote_year, voteable_id) VALUES (2026, 11)"
        ))
        # merged variant (has voteable_id but shouldn't be duplicated by voteable query)
        await s.execute(text(
            "INSERT INTO candidate_character (vote_year, voteable_id) VALUES (2026, 12)"
        ))
        await s.commit()

    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/vote-objects/characters?vote_year=2026")
    assert resp.status_code == 200
    data = resp.json()
    assert data["voteYear"] == 2026

    # Check groups by work name
    names = [i["name"] for g in data["groups"] for i in g["items"]]
    assert "灵梦" in names and "魔理沙" in names

    # Check filterMeta is present
    assert "filterMeta" in data
    assert len(data["filterMeta"]["kinds"]) > 0
    assert len(data["filterMeta"]["works"]) > 0

    # Check workIds in items
    for g in data["groups"]:
        for it in g["items"]:
            assert "workIds" in it
            assert "workTypes" in it
            assert "origin" not in it  # old field removed


@pytest.mark.asyncio
async def test_music_grouped_by_work(app):
    a, maker = app
    async with maker() as s:
        await _seed_work_and_voteable(s)
        await s.execute(text(
            "INSERT INTO candidate_music (vote_year, voteable_id) VALUES (2026, 20)"
        ))
        await s.commit()

    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/vote-objects/music?vote_year=2026")
    assert resp.status_code == 200
    data = resp.json()
    names = [i["name"] for g in data["groups"] for i in g["items"]]
    assert "曲A" in names


@pytest.mark.asyncio
async def test_detail_and_404(app):
    a, maker = app
    async with maker() as s:
        await _seed_work_and_voteable(s)
        await s.execute(text(
            "INSERT INTO candidate_character (vote_year, voteable_id) VALUES (2026, 10)"
        ))
        await s.commit()
        cid = (await s.execute(
            text("SELECT id FROM candidate_character WHERE voteable_id=10")
        )).scalar_one()

    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as ac:
        ok = await ac.get(f"/api/v1/vote-objects/character/{cid}")
        assert ok.status_code == 200
        assert ok.json()["name"] == "灵梦"
        nf = await ac.get("/api/v1/vote-objects/character/999999")
        assert nf.status_code == 404
