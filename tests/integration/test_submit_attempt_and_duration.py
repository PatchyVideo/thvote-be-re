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

    # re-submit (edit): append-only keeps multiple rows, attempt bumped, but the
    # FIRST fill is PRESERVED — a fast re-submit cannot launder the first-fill signal.
    submit2 = _row("v1", duration=800)
    submit2["payload"] = [{"id": "cirno", "first": False, "reason": "changed"}]
    await dao.create_character_submit(submit2)
    rows = (
        await session.execute(
            select(RawCharacterSubmit).where(RawCharacterSubmit.vote_id == "v1")
            .order_by(RawCharacterSubmit.attempt)
        )
    ).scalars().all()
    assert [r.attempt for r in rows] == [1, 2]  # history preserved
    assert rows[0].payload != rows[1].payload  # both payloads present
    assert rows[1].fill_duration_ms == rows[0].fill_duration_ms  # first fill frozen

    # a later null-duration re-submit still keeps the original first fill
    submit3 = _row("v1", duration=None)
    submit3["payload"] = [{"id": "daiyousei", "first": True, "reason": "third"}]
    await dao.create_character_submit(submit3)
    rows = (
        await session.execute(
            select(RawCharacterSubmit).where(RawCharacterSubmit.vote_id == "v1")
            .order_by(RawCharacterSubmit.attempt)
        )
    ).scalars().all()
    assert [r.attempt for r in rows] == [1, 2, 3]  # three rows kept
    assert rows[2].fill_duration_ms == 45000  # original first fill preserved


@pytest.mark.asyncio
async def test_null_first_fill_stays_null_across_resubmits(session):
    """A bot whose first submit reports no duration (null) stays null — the
    absence itself is the signal and a later valued edit can't erase it."""
    dao = SubmitDAO(session)
    await dao.create_character_submit(_row("vn", duration=None))
    rows = (
        await session.execute(
            select(RawCharacterSubmit).where(RawCharacterSubmit.vote_id == "vn")
            .order_by(RawCharacterSubmit.attempt)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].fill_duration_ms is None

    await dao.create_character_submit(_row("vn", duration=5000))
    rows = (
        await session.execute(
            select(RawCharacterSubmit).where(RawCharacterSubmit.vote_id == "vn")
            .order_by(RawCharacterSubmit.attempt)
        )
    ).scalars().all()
    assert [r.attempt for r in rows] == [1, 2]  # history preserved
    assert rows[1].fill_duration_ms is None  # first was null → preserved null


@pytest.mark.asyncio
async def test_attempt_is_per_vote_id(session):
    dao = SubmitDAO(session)
    await dao.create_character_submit(_row("a", 1000))
    await dao.create_character_submit(_row("b", 2000))
    assert (await _current(session, "a")).attempt == 1
    assert (await _current(session, "b")).attempt == 1


@pytest.mark.asyncio
async def test_compute_dao_latest_per_vote_after_three_submits(session):
    """After three submits, ComputeDAO._latest_per_vote should yield only the
    newest payload per vote_id, even though multiple rows exist."""
    from src.apps.result.compute_dao import ComputeDAO

    dao = SubmitDAO(session)

    # Create three submits with different payloads
    await dao.create_character_submit({
        **_row("vmulti", duration=1000),
        "payload": [{"id": "char1", "first": True, "reason": "first"}],
    })
    await dao.create_character_submit({
        **_row("vmulti", duration=2000),
        "payload": [{"id": "char2", "first": False, "reason": "second"}],
    })
    await dao.create_character_submit({
        **_row("vmulti", duration=3000),
        "payload": [{"id": "char3", "first": True, "reason": "third"}],
    })

    # Verify three rows exist
    all_rows = (
        await session.execute(
            select(RawCharacterSubmit).where(RawCharacterSubmit.vote_id == "vmulti")
        )
    ).scalars().all()
    assert len(all_rows) == 3

    # ComputeDAO should return only the newest payload
    compute_dao = ComputeDAO(session)
    votes = await compute_dao.load_char_votes()
    by_vote = {vid: items for vid, _, items in votes}

    assert "vmulti" in by_vote
    # Should only have the newest (third) submit's payload
    assert by_vote["vmulti"] == [{"id": "char3", "first": True, "reason": "third"}]


@pytest.mark.asyncio
async def test_get_submit_ties_on_created_at_broken_by_attempt(session):
    """created_at 同刻(sqlite 秒级精度可复现)时 get_*_submit 按 attempt 取最新
    (append-only 后同 vote_id 多行,仅按 created_at 排序会取错)。"""
    from datetime import datetime, timezone
    ts = datetime(2026, 1, 5, tzinfo=timezone.utc)
    session.add_all([
        RawCharacterSubmit(vote_id="v-tie", attempt=1, created_at=ts, user_ip="",
                           payload=[{"id": "old", "first": True}]),
        RawCharacterSubmit(vote_id="v-tie", attempt=2, created_at=ts, user_ip="",
                           payload=[{"id": "new", "first": True}]),
    ])
    await session.commit()
    dao = SubmitDAO(session)
    got = await dao.get_character_submit("v-tie")
    assert got is not None and got["payload"][0]["id"] == "new"
