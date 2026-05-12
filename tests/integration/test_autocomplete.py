"""Integration tests for AutocompleteDAO using SQLite."""

import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.apps.autocomplete.dao import AutocompleteDAO
from src.db_model.base import Base
from src.db_model.candidate import CandidateCharacter, CandidateMusic

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
        s.add(CandidateCharacter(vote_year=VOTE_YEAR, name="博丽灵梦", name_jp="博麗霊夢",
                                  origin="东方红魔乡", type="旧作", first_appearance="1996"))
        s.add(CandidateCharacter(vote_year=VOTE_YEAR, name="雾雨魔理沙", name_jp="霧雨魔理沙",
                                  origin="东方红魔乡", type="旧作", first_appearance="1996"))
        s.add(CandidateCharacter(vote_year=VOTE_YEAR, name="十六夜咲夜", name_jp="十六夜咲夜",
                                  origin="东方红魔乡", type="旧作", first_appearance="2002"))
        s.add(CandidateMusic(vote_year=VOTE_YEAR, name="Bad Apple!!", name_jp="Bad Apple!!",
                              type="旧作", album="Akyu's Untouched Score vol.5"))
        s.add(CandidateMusic(vote_year=VOTE_YEAR, name="U.N.オーエンは彼女なのか？",
                              name_jp="U.N.オーエンは彼女なのか？", type="旧作", album=None))
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
