"""SubmitDAO: server-computed attempt counter + fill_duration_ms persistence (B-045)."""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.apps.submit.dao import SubmitDAO
from src.db_model.base import Base
from src.db_model.raw_submit import RawCharacterSubmit


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


def _row(vote_id: str, duration: int | None) -> dict:
    return {
        "vote_id": vote_id,
        "attempt": None,  # ignored — DAO computes it
        "user_ip": "1.2.3.4",
        "additional_fingreprint": "dev-x",
        "fill_duration_ms": duration,
        "payload": [{"id": "reimu", "first": True, "reason": "好"}],
    }


async def _current(session, vote_id: str) -> RawCharacterSubmit:
    stmt = select(RawCharacterSubmit).where(RawCharacterSubmit.vote_id == vote_id)
    return (await session.execute(stmt)).scalars().one()


@pytest.mark.asyncio
async def test_attempt_increments_and_first_fill_is_preserved(session):
    dao = SubmitDAO(session)

    await dao.create_character_submit(_row("v1", duration=45000))
    row = await _current(session, "v1")
    assert row.attempt == 1  # first submit
    assert row.fill_duration_ms == 45000

    # re-submit (edit): only one row, attempt bumped, but the FIRST fill is
    # PRESERVED — a fast re-submit cannot launder the first-fill signal.
    await dao.create_character_submit(_row("v1", duration=800))
    rows = (
        await session.execute(
            select(RawCharacterSubmit).where(RawCharacterSubmit.vote_id == "v1")
        )
    ).scalars().all()
    assert len(rows) == 1  # delete-then-insert keeps a single row
    assert rows[0].attempt == 2
    assert rows[0].fill_duration_ms == 45000  # preserved, NOT overwritten with 800

    # a later null-duration re-submit still keeps the original first fill
    await dao.create_character_submit(_row("v1", duration=None))
    final = await _current(session, "v1")
    assert final.attempt == 3
    assert final.fill_duration_ms == 45000


@pytest.mark.asyncio
async def test_null_first_fill_stays_null_across_resubmits(session):
    """A bot whose first submit reports no duration (null) stays null — the
    absence itself is the signal and a later valued edit can't erase it."""
    dao = SubmitDAO(session)
    await dao.create_character_submit(_row("vn", duration=None))
    assert (await _current(session, "vn")).fill_duration_ms is None
    await dao.create_character_submit(_row("vn", duration=5000))
    row = await _current(session, "vn")
    assert row.attempt == 2
    assert row.fill_duration_ms is None  # first was null → preserved null


@pytest.mark.asyncio
async def test_attempt_is_per_vote_id(session):
    dao = SubmitDAO(session)
    await dao.create_character_submit(_row("a", 1000))
    await dao.create_character_submit(_row("b", 2000))
    assert (await _current(session, "a")).attempt == 1
    assert (await _current(session, "b")).attempt == 1
