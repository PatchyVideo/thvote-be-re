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


@pytest.mark.asyncio
async def test_characters_grouped_by_origin(app):
    a, maker = app
    async with maker() as s:
        await s.execute(text(
            "INSERT INTO candidate_character (vote_year, name, origin) "
            "VALUES (2026, '灵梦', '红魔乡')"
        ))
        await s.execute(text(
            "INSERT INTO candidate_character (vote_year, name, origin) "
            "VALUES (2026, '魔理沙', '红魔乡')"
        ))
        await s.execute(text(
            "INSERT INTO candidate_character (vote_year, name, origin, merged_into) "
            "VALUES (2026, '博丽灵梦', '红魔乡', 1)"
        ))
        await s.commit()

    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/vote-objects/characters?vote_year=2026")
    assert resp.status_code == 200
    data = resp.json()
    assert data["vote_year"] == 2026
    names = [i["name"] for g in data["groups"] for i in g["items"]]
    assert "灵梦" in names and "魔理沙" in names
    assert "博丽灵梦" not in names  # merged variant excluded


@pytest.mark.asyncio
async def test_music_grouped_by_album(app):
    a, maker = app
    async with maker() as s:
        await s.execute(text(
            "INSERT INTO candidate_music (vote_year, name, album) "
            "VALUES (2026, '曲A', '专辑1')"
        ))
        await s.commit()

    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/vote-objects/music?vote_year=2026")
    assert resp.status_code == 200
    assert resp.json()["groups"][0]["group"] == "专辑1"


@pytest.mark.asyncio
async def test_detail_and_404(app):
    a, maker = app
    async with maker() as s:
        await s.execute(text(
            "INSERT INTO candidate_character (vote_year, name) VALUES (2026, 'X')"
        ))
        await s.commit()
        cid = (await s.execute(
            text("SELECT id FROM candidate_character WHERE name='X'")
        )).scalar_one()

    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as ac:
        ok = await ac.get(f"/api/v1/vote-objects/character/{cid}")
        assert ok.status_code == 200
        assert ok.json()["name"] == "X"
        nf = await ac.get("/api/v1/vote-objects/character/999999")
        assert nf.status_code == 404
