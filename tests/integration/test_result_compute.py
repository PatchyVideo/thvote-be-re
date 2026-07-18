"""Integration tests: full compute pipeline using SQLite + fakeredis."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pytest
import pytest_asyncio

try:
    import fakeredis.aioredis as fakeredis_aioredis
    FakeRedis = fakeredis_aioredis.FakeRedis
except ImportError:
    import fakeredis
    FakeRedis = fakeredis.aioredis.FakeRedis

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.apps.result.compute_dao import ComputeDAO
from src.apps.result.compute_service import ComputeService
from src.apps.result.dao import ResultDAO, ResultNotComputedError
from src.apps.result.whitelist import load_whitelist
from src.common.config import Settings
from src.db_model.base import Base
from src.db_model.questionnaire import Questionnaire
from src.db_model.raw_submit import RawCharacterSubmit

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("JWT_SECRET_KEY", "test-key")
os.environ.setdefault("VOTE_START_ISO", "2026-01-01T00:00:00Z")
os.environ.setdefault("VOTE_END_ISO", "2026-12-31T23:59:59Z")


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncSession:
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s


@pytest_asyncio.fixture
def fake_redis():
    return FakeRedis(decode_responses=True)


@pytest_asyncio.fixture
def settings():
    s = Settings()
    s.__dict__["vote_year"] = 2026
    s.__dict__["vote_start_iso"] = "2026-01-01T00:00:00Z"
    s.__dict__["vote_end_iso"] = "2026-12-31T23:59:59Z"
    s.__dict__["gender_question_id"] = "q11011"
    s.__dict__["gender_male_value"] = "male"
    s.__dict__["gender_female_value"] = "female"
    return s


async def _seed_data(session: AsyncSession) -> None:
    """Insert raw_* votes using real whitelist ids + a questionnaire row for gender."""
    wl = load_whitelist("character")
    id1 = sorted(wl.ids)[0]
    session.add_all([
        RawCharacterSubmit(vote_id="user-1", attempt=1,
                           created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                           user_ip="", payload=[{"id": id1, "first": True, "reason": "love"}]),
        RawCharacterSubmit(vote_id="user-2", attempt=1,
                           created_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
                           user_ip="", payload=[{"id": id1, "first": False, "reason": None}]),
    ])
    # load_questionnaire_votes still reads the Questionnaire table (unchanged) → drives gender
    session.add(Questionnaire(
        id="user-1", submit_datetime=datetime(2026, 1, 2, tzinfo=timezone.utc),
        questionnaire_list=[{"id": "q11011", "answer": ["male"], "answer_str": None}],
    ))
    await session.commit()


@pytest.mark.asyncio
async def test_compute_and_read_ranking(session, fake_redis, settings):
    await _seed_data(session)
    wl = load_whitelist("character")
    id1 = sorted(wl.ids)[0]
    dao = ComputeDAO(session)
    svc = ComputeService(dao, fake_redis, settings)
    result = await svc.compute_all(2026)
    assert result["ok"] is True
    assert result["counts"]["chars"] == 1  # only id1 (both users voted it)

    result_dao = ResultDAO(fake_redis, settings)
    ranking, global_stats = await result_dao.get_ranking("character", [], 2026)
    assert len(ranking) == 1
    assert ranking[0]["id"] == id1
    assert ranking[0]["name"] == wl.name_of(id1)
    assert ranking[0]["rank"][0]["vote_count"] == 2
    assert ranking[0]["rank"][0]["favorite_vote_count"] == 1


@pytest.mark.asyncio
async def test_result_not_computed_error(fake_redis, settings):
    result_dao = ResultDAO(fake_redis, settings)
    with pytest.raises(ResultNotComputedError):
        await result_dao.get_ranking("character", [], 2026)


@pytest.mark.asyncio
async def test_compute_global_stats(session, fake_redis, settings):
    await _seed_data(session)
    dao = ComputeDAO(session)
    svc = ComputeService(dao, fake_redis, settings)
    await svc.compute_all(2026)
    result_dao = ResultDAO(fake_redis, settings)
    stats = await result_dao.get_global_stats(2026)
    assert stats["num_char"] == 2   # user-1, user-2
    assert stats["num_male"] == 1   # user-1 answered questionnaire male
