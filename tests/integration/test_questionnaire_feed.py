"""Integration test: questionnaire feed reads ``paper_answer`` (B-039).

Covers Task 2 of the result-graphql-compat plan: ``load_questionnaire_votes``
switches off the dead ``Questionnaire`` table (nothing in src/ writes it) and
reads the real structured ``paper_answer`` table instead, mapping
``active_question_id`` / ``selected_option_ids`` to the semantic ``code``
values added on ``QuestionDef`` / ``OptionDef`` in Task 1.
"""
from __future__ import annotations

import logging

import pytest

from src.apps.result.compute_dao import ComputeDAO
from src.db_model.questionnaire_def import OptionDef, PaperAnswer, QuestionDef


async def _seed(session) -> None:
    # Single question "性别" code=11011 with two options.
    gender_q = QuestionDef(group_id=1, type="Single", content="性别", code="11011")
    session.add(gender_q)
    await session.flush()
    opt_male = OptionDef(question_id=gender_q.id, content="男", code="1101101")
    opt_female = OptionDef(question_id=gender_q.id, content="女", code="1101102")
    session.add_all([opt_male, opt_female])

    # Input question code=11021 (free-text, no options).
    input_q = QuestionDef(group_id=1, type="Input", content="你喜欢什么", code="11021")
    session.add(input_q)
    await session.flush()

    session.add_all([
        PaperAnswer(
            vote_id="vote-1", vote_year=2026, questionnaire_id=1, group_id=1,
            active_question_id=gender_q.id, selected_option_ids=[opt_male.id],
        ),
        PaperAnswer(
            vote_id="vote-2", vote_year=2026, questionnaire_id=1, group_id=1,
            active_question_id=gender_q.id, selected_option_ids=[opt_female.id],
        ),
        PaperAnswer(
            vote_id="vote-1", vote_year=2026, questionnaire_id=1, group_id=2,
            active_question_id=input_q.id, selected_option_ids=[],
            input_text="喜欢",
        ),
        # active_question_id is None → should be skipped.
        PaperAnswer(
            vote_id="vote-3", vote_year=2026, questionnaire_id=1, group_id=3,
            active_question_id=None, selected_option_ids=[],
        ),
        # Different vote_year → should be filtered out.
        PaperAnswer(
            vote_id="vote-4", vote_year=2025, questionnaire_id=1, group_id=1,
            active_question_id=gender_q.id, selected_option_ids=[opt_male.id],
        ),
    ])
    await session.commit()


@pytest.mark.asyncio
async def test_load_questionnaire_votes_from_paper_answer(session):
    from datetime import datetime
    await _seed(session)
    dao = ComputeDAO(session)
    votes = await dao.load_questionnaire_votes(2026)
    by_vote = {vid: items for vid, items in votes}

    assert set(by_vote) == {"vote-1", "vote-2"}  # 空 active/别年被排除
    # 验证 vote-1 的两个回答包含预期字段和时间戳
    vote1_items = by_vote["vote-1"]
    assert len(vote1_items) == 2
    # 找到性别回答和输入回答(顺序不固定)
    gender_item = next((i for i in vote1_items if i["id"] == "11011"), None)
    input_item = next((i for i in vote1_items if i["id"] == "11021"), None)
    assert gender_item is not None
    assert gender_item["answer"] == ["1101101"]
    assert gender_item["answer_str"] is None
    assert isinstance(gender_item["ts"], datetime)
    assert input_item is not None
    assert input_item["answer"] == []
    assert input_item["answer_str"] == "喜欢"
    assert isinstance(input_item["ts"], datetime)
    # 验证 vote-2
    assert by_vote["vote-2"][0]["answer"] == ["1101102"]
    assert isinstance(by_vote["vote-2"][0]["ts"], datetime)


@pytest.mark.asyncio
async def test_load_questionnaire_votes_skips_rows_without_code(session):
    """Question/option rows lacking a ``code`` can't be addressed semantically."""
    uncoded_q = QuestionDef(group_id=1, type="Single", content="旧题", code=None)
    session.add(uncoded_q)
    await session.flush()
    session.add(
        PaperAnswer(
            vote_id="vote-5", vote_year=2026, questionnaire_id=1, group_id=1,
            active_question_id=uncoded_q.id, selected_option_ids=[],
        )
    )
    await session.commit()

    dao = ComputeDAO(session)
    votes = await dao.load_questionnaire_votes(2026)
    by_vote = {vid: items for vid, items in votes}
    assert "vote-5" not in by_vote


@pytest.mark.asyncio
async def test_load_questionnaire_votes_skips_options_without_code(session, caplog):
    """An option missing ``code`` is dropped from ``answer``, not kept as a
    raw id and not allowed to crash the row — same "can't address without
    code" rule as the question-level skip, and it must show up in the
    summary log too (migration observability: partial option-code backfill
    in prod would otherwise silently truncate answers with no trace).
    """
    q = QuestionDef(group_id=1, type="Single", content="口味", code="11031")
    session.add(q)
    await session.flush()
    coded_opt = OptionDef(question_id=q.id, content="甜", code="1103101")
    uncoded_opt = OptionDef(question_id=q.id, content="咸", code=None)
    session.add_all([coded_opt, uncoded_opt])
    await session.flush()
    session.add(
        PaperAnswer(
            vote_id="vote-6", vote_year=2026, questionnaire_id=1, group_id=1,
            active_question_id=q.id,
            selected_option_ids=[coded_opt.id, uncoded_opt.id],
        )
    )
    await session.commit()

    dao = ComputeDAO(session)
    with caplog.at_level(logging.DEBUG, logger="src.apps.result.compute_dao"):
        votes = await dao.load_questionnaire_votes(2026)
    by_vote = {vid: items for vid, items in votes}

    # 咸(缺 code)被排除,甜(有 code)保留,没有崩、也没有把裸 id 混进 answer。
    assert by_vote["vote-6"][0]["answer"] == ["1103101"]
    assert "1 options without code" in caplog.text


@pytest.mark.asyncio
async def test_load_questionnaire_votes_uses_latest_batch(session):
    """改票后(批次 attempt 递增)只计最新批,撤答的组不再出现在 items 里。"""
    gender_q = QuestionDef(group_id=1, type="Single", content="性别", code="11011")
    session.add(gender_q)
    await session.flush()
    opt_male = OptionDef(question_id=gender_q.id, content="男", code="1101101")
    session.add(opt_male)
    await session.flush()

    input_q = QuestionDef(group_id=1, type="Input", content="你喜欢什么", code="11021")
    session.add(input_q)
    await session.flush()

    session.add_all([
        # 批次 1:性别 + 输入
        PaperAnswer(
            vote_id="vote-batch", vote_year=2026, questionnaire_id=1, group_id=1,
            active_question_id=gender_q.id, selected_option_ids=[opt_male.id],
            attempt=1,
        ),
        PaperAnswer(
            vote_id="vote-batch", vote_year=2026, questionnaire_id=1, group_id=2,
            active_question_id=input_q.id, selected_option_ids=[],
            input_text="喜欢", attempt=1,
        ),
        # 批次 2(改票):撤掉输入题,只留性别
        PaperAnswer(
            vote_id="vote-batch", vote_year=2026, questionnaire_id=1, group_id=1,
            active_question_id=gender_q.id, selected_option_ids=[opt_male.id],
            attempt=2,
        ),
    ])
    await session.commit()

    dao = ComputeDAO(session)
    votes = await dao.load_questionnaire_votes(2026)
    by_vote = {vid: items for vid, items in votes}

    items = by_vote["vote-batch"]
    assert len(items) == 1              # 批次1的输入题不再出现
    assert items[0]["id"] == "11011"
