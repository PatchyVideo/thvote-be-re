"""Integration tests for questionnaire domain (year-less structure + flat answers)."""
import pytest

from src.db_model.questionnaire_def import (
    OptionDef, QuestionDef, QuestionGroupDef, QuestionnaireDef,
)


async def _seed(session):
    session.add(QuestionnaireDef(
        id=1, key="main_required", title="必填", introduction="",
        category="main", required=True, order=1,
    ))
    session.add(QuestionGroupDef(
        id=10, questionnaire_id=1, order=1, hidden_by_default=False,
    ))
    session.add(QuestionDef(id=100, group_id=10, type="Single", content="q1", order=1))
    session.add(OptionDef(
        id=1000, question_id=100, content="o1",
        related_question_ids=[], mutex_option_ids=[], option_group=0, order=1,
    ))
    session.add(QuestionnaireDef(
        id=2, key="extra", title="选填", category="extra", required=False, order=2,
    ))
    session.add(QuestionGroupDef(id=20, questionnaire_id=2, order=1))
    session.add(QuestionDef(id=200, group_id=20, type="Input", content="选填题"))
    await session.commit()


@pytest.mark.asyncio
async def test_get_structure_array(session):
    from src.apps.questionnaire.dao import QuestionnaireDAO
    from src.apps.questionnaire.service import QuestionnaireService
    await _seed(session)
    svc = QuestionnaireService(QuestionnaireDAO(session))
    structure = await svc.get_structure()
    qs = structure["questionnaires"]
    assert qs[0]["key"] == "main_required"
    assert qs[0]["required"] is True
    assert qs[0]["questionGroups"][0]["questions"][0]["options"][0]["id"] == 1000


@pytest.mark.asyncio
async def test_submit_and_get_flat_answers(session):
    from src.apps.questionnaire.dao import QuestionnaireDAO
    from src.apps.questionnaire.service import QuestionnaireService
    await _seed(session)
    svc = QuestionnaireService(QuestionnaireDAO(session))
    answers = [{"questionnaireId": 1, "groupId": 10, "activeQuestionId": 100,
                "selectedOptionIds": [1000], "input": ""}]
    n = await svc.submit_answers("u1", 2026, answers)
    assert n == 1
    got = await svc.get_answers("u1", 2026)
    assert got[0]["group_id"] == 10
    assert got[0]["selected_option_ids"] == [1000]


@pytest.mark.asyncio
async def test_is_complete_gate(session):
    from src.apps.questionnaire.dao import QuestionnaireDAO
    from src.apps.questionnaire.service import QuestionnaireService
    await _seed(session)
    svc = QuestionnaireService(QuestionnaireDAO(session))
    assert await svc.is_complete("u2", 2026) is False
    await svc.submit_answers("u2", 2026, [
        {"questionnaireId": 1, "groupId": 10, "activeQuestionId": 100,
         "selectedOptionIds": [1000], "input": ""}])
    assert await svc.is_complete("u2", 2026) is False
    await svc.submit_answers("u2", 2026, [
        {"questionnaireId": 1, "groupId": 10, "activeQuestionId": 100,
         "selectedOptionIds": [1000], "input": ""},
        {"questionnaireId": 2, "groupId": 20, "activeQuestionId": 200,
         "selectedOptionIds": [], "input": "选填回答"},
    ])
    assert await svc.is_complete("u2", 2026) is True


@pytest.mark.asyncio
async def test_invalidated_batches_gate_feed_history_and_resubmit(session):
    from sqlalchemy import update
    from src.apps.questionnaire.dao import QuestionnaireDAO
    from src.apps.questionnaire.service import QuestionnaireService
    from src.apps.result.compute_dao import ComputeDAO
    from src.db_model.questionnaire_def import PaperAnswer

    await _seed(session)
    await session.execute(update(QuestionDef).where(QuestionDef.id == 100).values(code="11011"))
    await session.execute(update(OptionDef).where(OptionDef.id == 1000).values(code="1101101"))
    await session.commit()
    svc = QuestionnaireService(QuestionnaireDAO(session))
    compute = ComputeDAO(session)
    answers = [
        {"questionnaireId": 1, "groupId": 10, "activeQuestionId": 100,
         "selectedOptionIds": [1000]},
        {"questionnaireId": 2, "groupId": 20, "activeQuestionId": 200,
         "input": "回答"},
    ]
    await svc.submit_answers("u1", 12, answers)
    await svc.submit_answers("u1", 12, answers)
    await svc.submit_answers("u1", 11, answers)
    await session.execute(update(PaperAnswer).where(
        PaperAnswer.vote_id == "u1", PaperAnswer.vote_year == 12,
        PaperAnswer.attempt == 2,
    ).values(invalidated=True))
    await session.commit()

    # Raw readback still permits editing, but cannot satisfy the voting gate.
    raw = await svc.get_answers("u1", 12)
    assert len(raw) == 2
    assert await svc.is_complete("u1", 12) is False
    assert await svc.is_complete("u1", 12, answers=raw) is False
    assert await svc.is_complete("u1", 11) is True
    assert await compute.load_questionnaire_votes(12) == []
    assert await compute.load_questionnaire_history(12) == []
    assert await compute.load_questionnaire_completion(12) == {"main_required": set(), "extra": set()}

    await session.execute(update(PaperAnswer).where(
        PaperAnswer.vote_year == 12, PaperAnswer.attempt == 2,
    ).values(invalidated=False))
    await session.execute(update(PaperAnswer).where(
        PaperAnswer.vote_year == 12, PaperAnswer.attempt == 1,
    ).values(invalidated=True))
    await session.commit()
    assert await svc.is_complete("u1", 12) is True
    assert [row[2] for row in await compute.load_questionnaire_history(12)] == [2]
    assert dict(await compute.load_questionnaire_votes(12))["u1"][0]["answer"] == ["1101101"]
    assert (await compute.load_questionnaire_completion(12))["extra"] == {"u1"}

    # A new legal submission is effective even after the previous latest was voided.
    await session.execute(update(PaperAnswer).where(
        PaperAnswer.vote_year == 12, PaperAnswer.attempt == 2,
    ).values(invalidated=True))
    await session.commit()
    await svc.submit_answers("u1", 12, answers)
    assert await svc.is_complete("u1", 12) is True
    assert [row[2] for row in await compute.load_questionnaire_history(12)] == [3]


def _row(group_id: int, opts: list[int]) -> dict:
    """paper_answer 行字典(与 replace_answers 期望的形状一致)。"""
    return {
        "questionnaire_id": 1,
        "group_id": group_id,
        "active_question_id": 100,
        "selected_option_ids": opts,
        "input_text": None,
    }


@pytest.mark.asyncio
async def test_resubmit_appends_batch_and_reads_latest(session):
    """整卷重提交底层为追加新批次(attempt+1),历史批次保留,读方只见最新批。"""
    from sqlalchemy import select
    from src.apps.questionnaire.dao import QuestionnaireDAO
    from src.db_model.questionnaire_def import PaperAnswer

    dao = QuestionnaireDAO(session)
    await dao.replace_answers(
        "v1", 12, [_row(group_id=1, opts=[11]), _row(group_id=2, opts=[21])]
    )
    await dao.replace_answers("v1", 12, [_row(group_id=1, opts=[12])])  # 撤掉组2

    all_rows = (await session.execute(select(PaperAnswer))).scalars().all()
    assert len(all_rows) == 3                      # 历史批次保留
    current = await dao.get_answers("v1", 12)
    assert len(current) == 1                        # 只见最新批
    assert current[0]["selected_option_ids"] == [12]


@pytest.mark.asyncio
async def test_get_answers_null_attempt_legacy_rows_readable(session):
    """0017 迁移前存量行 attempt=NULL,latest_batch 应把整组当作单批返回。"""
    from src.apps.questionnaire.dao import QuestionnaireDAO
    from src.db_model.questionnaire_def import PaperAnswer

    session.add_all([
        PaperAnswer(
            vote_id="v-legacy", vote_year=12, questionnaire_id=1, group_id=1,
            active_question_id=100, selected_option_ids=[11], attempt=None,
        ),
        PaperAnswer(
            vote_id="v-legacy", vote_year=12, questionnaire_id=1, group_id=2,
            active_question_id=101, selected_option_ids=[21], attempt=None,
        ),
    ])
    await session.commit()

    dao = QuestionnaireDAO(session)
    got = await dao.get_answers("v-legacy", 12)
    assert len(got) == 2


@pytest.mark.asyncio
async def test_empty_paper_submit_rejected_not_silent_leak(session):
    """append-only 下空提交无法表达"清空整卷"——必须显式拒绝,
    否则旧批次会静默保持可见(终审修复)。

    R-01 起作答行必须指向已存结构,故这里先 seed 结构再提交合法作答:
    旧版本用例依赖「无结构也能写入」这一缺陷行为。
    """
    from src.apps.questionnaire.dao import QuestionnaireDAO
    from src.apps.questionnaire.service import QuestionnaireService
    from src.common.exceptions import ValidationError

    await _seed(session)
    svc = QuestionnaireService(QuestionnaireDAO(session))
    await svc.submit_answers("v-empty", 12, [{
        "questionnaireId": 1, "groupId": 10, "activeQuestionId": 100,
        "selectedOptionIds": [1000], "input": "",
    }])
    with pytest.raises(ValidationError):
        await svc.submit_answers("v-empty", 12, [])
    # 旧批次仍是"当前答案"(拒绝而非清空),且未新增空批次。
    assert len(await svc.get_answers("v-empty", 12)) == 1
