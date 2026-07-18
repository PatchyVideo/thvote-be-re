"""Integration tests: ComputeDAO.load_*_votes reading raw_* submission tables.

B-050 Task 2: load_char_votes/load_music_votes/load_cp_votes must read the
real submission tables (raw_character/raw_music/raw_cp) instead of the dead
path-B tables (character/music/cp): take the latest submission per vote_id,
exclude invalidated rows, and normalize the JSON payload.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.apps.result.compute_dao import ComputeDAO
from src.db_model.base import Base
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


@pytest.mark.asyncio
async def test_load_char_votes_latest_only_and_excludes_invalidated(session):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    session.add_all([
        # voteA 旧提交
        RawCharacterSubmit(vote_id="voteA", attempt=1, created_at=base,
                           user_ip="x", payload=[{"id": "aaaa1111", "first": False}]),
        # voteA 新提交（同 vote_id，更晚）→ 应只取这条
        RawCharacterSubmit(vote_id="voteA", attempt=2, created_at=base + timedelta(hours=1),
                           user_ip="x", payload=[{"id": "bbbb2222", "first": True}]),
        # voteB 被作废 → 应排除
        RawCharacterSubmit(vote_id="voteB", attempt=1, created_at=base,
                           user_ip="x", invalidated=True,
                           payload=[{"id": "aaaa1111", "first": False}]),
        # voteC legacy list[str] payload → 归一化
        RawCharacterSubmit(vote_id="voteC", attempt=1, created_at=base,
                           user_ip="x", payload=["aaaa1111"]),
    ])
    await session.commit()

    dao = ComputeDAO(session)
    votes = await dao.load_char_votes()
    by_vote = {vid: items for vid, _, items in votes}

    assert "voteB" not in by_vote  # invalidated 排除
    assert by_vote["voteA"] == [{"id": "bbbb2222", "first": True}]  # 只取最新
    assert by_vote["voteC"] == [{"id": "aaaa1111", "first": False, "reason": None}]  # 归一化
