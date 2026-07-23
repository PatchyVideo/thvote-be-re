"""Integration tests for AutocompleteDAO using SQLite."""

import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.apps.autocomplete.dao import AutocompleteDAO
from src.db_model.base import Base

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("JWT_SECRET_KEY", "test-key")
os.environ.setdefault("VOTE_START_ISO", "2026-01-01T00:00:00Z")
os.environ.setdefault("VOTE_END_ISO", "2026-12-31T23:59:59Z")

VOTE_YEAR = 2026


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        # Create work entries
        await s.execute(text(
            "INSERT INTO work (id, name, type) VALUES (1, '东方红魔乡', 'new')"
        ))
        await s.execute(text(
            "INSERT INTO work (id, name, type) VALUES (2, "
            "'Akyu''s Untouched Score vol.5', 'CD')"
        ))
        # Create voteable_character entries
        await s.execute(text(
            "INSERT INTO voteable_character (id, name, name_jp, type, work_id) "
            "VALUES (100, '博丽灵梦', '博麗霊夢', '旧作', 1)"
        ))
        await s.execute(text(
            "INSERT INTO voteable_character (id, name, name_jp, type, work_id) "
            "VALUES (101, '雾雨魔理沙', '霧雨魔理沙', '旧作', 1)"
        ))
        await s.execute(text(
            "INSERT INTO voteable_character (id, name, name_jp, type, work_id) "
            "VALUES (102, '十六夜咲夜', '十六夜咲夜', '旧作', 1)"
        ))
        # Create voteable_music entries
        await s.execute(text(
            "INSERT INTO voteable_music (id, name, name_jp, type, work_id) "
            "VALUES (200, 'Bad Apple!!', 'Bad Apple!!', '旧作', 2)"
        ))
        await s.execute(text(
            "INSERT INTO voteable_music (id, name, name_jp, type, work_id) "
            "VALUES (201, 'U.N.オーエンは彼女なのか？', "
            "'U.N.オーエンは彼女なのか？', '旧作', NULL)"
        ))
        # Create candidate entries
        await s.execute(text(
            "INSERT INTO candidate_character (vote_year, voteable_id) "
            "VALUES (2026, 100)"
        ))
        await s.execute(text(
            "INSERT INTO candidate_character (vote_year, voteable_id) "
            "VALUES (2026, 101)"
        ))
        await s.execute(text(
            "INSERT INTO candidate_character (vote_year, voteable_id) "
            "VALUES (2026, 102)"
        ))
        await s.execute(text(
            "INSERT INTO candidate_music (vote_year, voteable_id) "
            "VALUES (2026, 200)"
        ))
        await s.execute(text(
            "INSERT INTO candidate_music (vote_year, voteable_id) "
            "VALUES (2026, 201)"
        ))
        await s.commit()
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_search_characters_by_name(session):
    dao = AutocompleteDAO(session, VOTE_YEAR)
    results = await dao.search_characters("灵梦", 10)
    assert len(results) == 1
    assert results[0]["name"] == "博丽灵梦"
    assert results[0]["origin"] == "东方红魔乡"


@pytest.mark.asyncio
async def test_search_characters_by_name_jp(session):
    dao = AutocompleteDAO(session, VOTE_YEAR)
    results = await dao.search_characters("霊夢", 10)
    assert len(results) == 1
    assert results[0]["name"] == "博丽灵梦"


@pytest.mark.asyncio
async def test_search_characters_no_match(session):
    dao = AutocompleteDAO(session, VOTE_YEAR)
    results = await dao.search_characters("不存在的名字xyz", 10)
    assert results == []


@pytest.mark.asyncio
async def test_search_characters_limit(session):
    dao = AutocompleteDAO(session, VOTE_YEAR)
    results = await dao.search_characters("夜", 1)
    assert len(results) <= 1


@pytest.mark.asyncio
async def test_search_music_by_name(session):
    dao = AutocompleteDAO(session, VOTE_YEAR)
    results = await dao.search_music("Bad", 10)
    assert len(results) == 1
    assert results[0]["name"] == "Bad Apple!!"
    assert results[0]["origin"] == "Akyu's Untouched Score vol.5"


@pytest.mark.asyncio
async def test_search_music_no_album_returns_none_origin(session):
    dao = AutocompleteDAO(session, VOTE_YEAR)
    results = await dao.search_music("U.N", 10)
    assert len(results) == 1
    assert results[0]["origin"] is None


@pytest.mark.asyncio
async def test_search_cps_returns_empty(session):
    dao = AutocompleteDAO(session, VOTE_YEAR)
    results = await dao.search_cps("anything", 10)
    assert results == []


@pytest.mark.asyncio
async def test_wrong_year_returns_nothing(session):
    dao = AutocompleteDAO(session, vote_year=9999)
    results = await dao.search_characters("灵梦", 10)
    assert results == []
