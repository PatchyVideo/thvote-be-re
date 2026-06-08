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
    assert await svc.is_complete("u2", 2026) is True
