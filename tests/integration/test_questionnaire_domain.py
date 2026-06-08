"""Integration tests for questionnaire domain (structure + answers + completion)."""
import pytest

from src.db_model.questionnaire_def import (
    OptionDef,
    QuestionDef,
    QuestionGroupDef,
    QuestionnaireDef,
)


async def _seed_minimal(session, vote_year=2026):
    session.add(QuestionnaireDef(
        id=11, vote_year=vote_year, slot="required", category="main",
        name="必填问卷", introduction="intro", order=1,
    ))
    session.add(QuestionGroupDef(
        id=1101, questionnaire_id=11, order=1, initial_question_id=11011,
    ))
    session.add(QuestionDef(
        id=11011, group_id=1101, type="Single", content="q1", order=1,
    ))
    session.add(OptionDef(
        id=1101101, question_id=11011, content="opt1",
        related_question_ids=[], mutex_option_ids=[], option_group=0, order=1,
    ))
    await session.commit()


@pytest.mark.asyncio
async def test_get_structure_shape(session):
    from src.apps.questionnaire.dao import QuestionnaireDAO
    from src.apps.questionnaire.service import QuestionnaireService

    await _seed_minimal(session)
    svc = QuestionnaireService(QuestionnaireDAO(session))
    structure = await svc.get_structure(2026)
    req = structure["mainQuestionnaire"]["requiredQuestionnaire"]
    assert req["id"] == 11
    assert req["questionGroups"][0]["questions"][0]["options"][0]["id"] == 1101101


@pytest.mark.asyncio
async def test_submit_and_get_answers(session):
    from src.apps.questionnaire.dao import QuestionnaireDAO
    from src.apps.questionnaire.service import QuestionnaireService

    await _seed_minimal(session)
    svc = QuestionnaireService(QuestionnaireDAO(session))
    answer_state = {
        "mainQuestionnaire": {
            "requiredQuestionnaire": {
                "questionnaireId": 11,
                "groups": [
                    {
                        "groupId": 1101, "activeQuestionId": 11011,
                        "selectedOptionIds": [1101101], "input": "",
                    }
                ],
            }
        },
        "extraQuestionnaire": {},
    }
    n = await svc.submit_answers("u1", 2026, answer_state)
    assert n == 1
    answers = await svc.get_answers("u1", 2026)
    assert answers[0]["group_id"] == 1101
    assert answers[0]["selected_option_ids"] == [1101101]


@pytest.mark.asyncio
async def test_is_complete_gate(session):
    from src.apps.questionnaire.dao import QuestionnaireDAO
    from src.apps.questionnaire.service import QuestionnaireService

    await _seed_minimal(session)
    svc = QuestionnaireService(QuestionnaireDAO(session))
    assert await svc.is_complete("u2", 2026) is False
    await svc.submit_answers("u2", 2026, {
        "mainQuestionnaire": {
            "requiredQuestionnaire": {
                "questionnaireId": 11,
                "groups": [{
                    "groupId": 1101, "activeQuestionId": 11011,
                    "selectedOptionIds": [1101101], "input": "",
                }],
            }
        },
        "extraQuestionnaire": {},
    })
    assert await svc.is_complete("u2", 2026) is True
