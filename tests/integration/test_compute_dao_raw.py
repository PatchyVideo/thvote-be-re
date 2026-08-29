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
from src.db_model.questionnaire_def import (
    OptionDef,
    PaperAnswer,
    QuestionDef,
    QuestionnaireDef,
)
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
        RawCharacterSubmit(vote_id="voteA", attempt=2,
                           created_at=base + timedelta(hours=1),
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
    # voteC: legacy list[str] 已归一化
    assert by_vote["voteC"] == [{"id": "aaaa1111", "first": False, "reason": None}]


@pytest.mark.asyncio
async def test_invalidated_latest_row_drops_vote_no_fallback(session):
    """legacy 选民多行:最新行被作废 → 整个 vote_id 丢弃,不回退到更旧的合法行。"""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    session.add_all([
        RawCharacterSubmit(vote_id="legacy", attempt=1, created_at=base,
                           user_ip="x", payload=[{"id": "old_id", "first": False}]),
        RawCharacterSubmit(vote_id="legacy", attempt=2,
                           created_at=base + timedelta(hours=1),
                           user_ip="x", invalidated=True,
                           payload=[{"id": "new_id", "first": False}]),
    ])
    await session.commit()
    dao = ComputeDAO(session)
    votes = await dao.load_char_votes()
    # 最新行作废 → 整票丢弃,不回退到 old_id
    assert all(vid != "legacy" for vid, _, _ in votes)


@pytest.mark.asyncio
async def test_char_history_returns_all_rows_excluding_invalidated_voter(session):
    """load_char_history 返回全部提交行(非仅最新),选民排除口径与
    _latest_per_vote 完全一致:v1 两次有效提交全部保留;v2 唯一一次提交的
    (也是最新)行被作废 → 整个 vote_id 出局。"""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    session.add_all([
        RawCharacterSubmit(vote_id="v1", attempt=1, created_at=base,
                           user_ip="x", payload=[{"id": "aaaa1111", "first": False}]),
        RawCharacterSubmit(vote_id="v1", attempt=2,
                           created_at=base + timedelta(hours=1),
                           user_ip="x", payload=[{"id": "bbbb2222", "first": True}]),
        RawCharacterSubmit(vote_id="v2", attempt=1, created_at=base,
                           user_ip="x", invalidated=True,
                           payload=[{"id": "cccc3333", "first": False}]),
    ])
    await session.commit()

    dao = ComputeDAO(session)
    hist = await dao.load_char_history()
    ids = {(vid, att) for vid, _, att, _ in hist}
    assert ids == {("v1", 1), ("v1", 2)}  # v2 整体出局(与 _latest_per_vote 同口径)


@pytest.mark.asyncio
async def test_questionnaire_votes_carry_row_timestamp(session):
    """问卷数据加载时每项应携带 created_at 时间戳用于趋势数据分组。"""
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    vote_year = 12

    # 创建问卷定义
    qdef = QuestionnaireDef(key="test_q", title="Test Questionnaire")
    session.add(qdef)
    await session.flush()

    qgroup_id = 1
    qid = 1
    oid = 1

    # 创建题目与选项(均带 code)
    qdef_row = QuestionDef(
        id=qid, group_id=qgroup_id, code="Q0001",
        content="Test Question", type="Single"
    )
    option_row = OptionDef(
        id=oid, question_id=qid, code="O0001", content="Option A"
    )
    session.add_all([qdef_row, option_row])
    await session.flush()

    # 创建问卷回答(来自两个不同投票者,不同时间)
    pa1 = PaperAnswer(
        vote_id="voter1", vote_year=vote_year,
        questionnaire_id=qdef.id, group_id=qgroup_id,
        active_question_id=qid,
        selected_option_ids=[oid],
        input_text=None,
        created_at=base
    )
    pa2 = PaperAnswer(
        vote_id="voter2", vote_year=vote_year,
        questionnaire_id=qdef.id, group_id=qgroup_id,
        active_question_id=qid,
        selected_option_ids=[oid],
        input_text=None,
        created_at=base + timedelta(hours=1)
    )
    session.add_all([pa1, pa2])
    await session.commit()

    # 加载问卷投票数据
    dao = ComputeDAO(session)
    votes = await dao.load_questionnaire_votes(vote_year=vote_year)

    # 验证返回格式: list[tuple[str, list[dict]]]
    assert len(votes) == 2
    for vote_id, items in votes:
        assert isinstance(vote_id, str)
        assert isinstance(items, list)
        # 每项应包含 ts 字段,值为 datetime 类型
        assert all(isinstance(i, dict) for i in items)
        assert all("ts" in i for i in items)
        assert all(isinstance(i["ts"], datetime) for i in items)
