"""mock 投票生成器 DB 编排集成测:写入/幂等/code 回填/wipe 只动 mock 行。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from scripts.generate_mock_votes import (
    MOCK_PREFIX,
    run_generation,
    wipe_mock_rows,
)
from src.db_model.questionnaire_def import (
    OptionDef,
    PaperAnswer,
    QuestionDef,
    QuestionGroupDef,
    QuestionnaireDef,
)
from src.db_model.raw_submit import (
    RawCharacterSubmit,
    RawCPSubmit,
    RawMusicSubmit,
)
from tests.integration.conftest import seed_voteables_from_snapshot

VOTE_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
VOTE_END = datetime(2026, 3, 1, tzinfo=timezone.utc)


async def _seed_structure(session) -> tuple[int, int]:
    """种子:白名单 + 占位问卷(1 单选 2 选项 + 1 多选 3 选项,code 全空)。

    返回 (单选题 id, 多选题 id)。
    """
    await seed_voteables_from_snapshot(session, "character", 2026)
    await seed_voteables_from_snapshot(session, "music", 2026)
    paper = QuestionnaireDef(key="main", title="占位问卷")
    session.add(paper)
    await session.flush()
    # 一题一组:paper_answer 每票每组唯一,共组只会答其中一题
    group_a = QuestionGroupDef(questionnaire_id=paper.id)
    group_b = QuestionGroupDef(questionnaire_id=paper.id, order=1)
    session.add_all([group_a, group_b])
    await session.flush()
    q_single = QuestionDef(group_id=group_a.id, type="Single", content="性别?")
    q_multi = QuestionDef(group_id=group_b.id, type="Multiple", content="爱好?")
    session.add_all([q_single, q_multi])
    await session.flush()
    session.add_all(
        [OptionDef(question_id=q_single.id, content=c) for c in ("男", "女")]
        + [OptionDef(question_id=q_multi.id, content=c) for c in ("A", "B", "C")]
    )
    await session.commit()
    return q_single.id, q_multi.id


async def _count(session, model, mock_only: bool = True) -> int:
    stmt = select(func.count()).select_from(model)
    if mock_only:
        stmt = stmt.where(model.vote_id.like(f"{MOCK_PREFIX}%"))
    return (await session.execute(stmt)).scalar_one()


def _run_kwargs(voters: int = 40, seed: int = 1) -> dict:
    return {
        "voters": voters,
        "vote_year": 2026,
        "seed": seed,
        "vote_start": VOTE_START,
        "vote_end": VOTE_END,
        "gender_question_code": "11011",
        "male_code": "1101101",
        "female_code": "1101102",
    }


@pytest.mark.asyncio
async def test_generation_inserts_and_backfills(session):
    q_single_id, q_multi_id = await _seed_structure(session)
    summary = await run_generation(session, **_run_kwargs())

    for model in (RawCharacterSubmit, RawMusicSubmit, RawCPSubmit, PaperAnswer):
        assert await _count(session, model) > 0
    assert summary["inserted"]["char"] == await _count(session, RawCharacterSubmit)

    # code 回填:单选题成为性别题,多选题拿 9 系测试 code
    q_single = (await session.execute(
        select(QuestionDef).where(QuestionDef.id == q_single_id)
    )).scalar_one()
    q_multi = (await session.execute(
        select(QuestionDef).where(QuestionDef.id == q_multi_id)
    )).scalar_one()
    assert q_single.code == "11011"
    assert q_multi.code and q_multi.code.startswith("9")
    opt_codes = {
        o.code
        for o in (await session.execute(
            select(OptionDef).where(OptionDef.question_id == q_single_id)
        )).scalars()
    }
    assert {"1101101", "1101102"} <= opt_codes


@pytest.mark.asyncio
async def test_rerun_is_idempotent_and_spares_human_rows(session):
    await _seed_structure(session)
    await run_generation(session, **_run_kwargs())
    first_count = await _count(session, RawCharacterSubmit)

    session.add(RawCharacterSubmit(
        vote_id="human-1", attempt=1,
        created_at=datetime(2026, 1, 5, tzinfo=timezone.utc), user_ip="",
        payload=[{"id": "1", "first": False, "reason": None}],
    ))
    await session.commit()

    await run_generation(session, **_run_kwargs())  # 同参数重跑
    assert await _count(session, RawCharacterSubmit) == first_count  # 幂等
    human = (await session.execute(
        select(RawCharacterSubmit).where(RawCharacterSubmit.vote_id == "human-1")
    )).scalar_one_or_none()
    assert human is not None  # 真人行不受影响


@pytest.mark.asyncio
async def test_wipe_removes_only_mock_rows(session):
    await _seed_structure(session)
    await run_generation(session, **_run_kwargs())
    session.add(RawMusicSubmit(
        vote_id="human-2", attempt=1,
        created_at=datetime(2026, 1, 5, tzinfo=timezone.utc), user_ip="",
        payload=[{"id": "1", "first": False, "reason": None}],
    ))
    await session.commit()

    wiped = await wipe_mock_rows(session)
    assert wiped["music"] > 0
    for model in (RawCharacterSubmit, RawMusicSubmit, RawCPSubmit, PaperAnswer):
        assert await _count(session, model) == 0  # mock 全清
    assert await _count(session, RawMusicSubmit, mock_only=False) == 1  # 真人行还在
