"""Vote gate upgrade: structured questionnaire completion (B-039)."""
import pytest

from src.apps.submit.dao import SubmitDAO
from src.apps.submit.schemas import (
    CharacterSubmit,
    CharacterSubmitRest,
    SubmitMetadata,
)
from src.apps.submit.service import QuestionnaireNotCompletedError, SubmitService
from src.db_model.questionnaire_def import (
    OptionDef,
    QuestionDef,
    QuestionGroupDef,
    QuestionnaireDef,
)


async def _seed_required(session, vote_year=2026):
    session.add(QuestionnaireDef(
        id=11, vote_year=vote_year, slot="required", category="main",
        name="必填", introduction="", order=1,
    ))
    session.add(QuestionGroupDef(
        id=1101, questionnaire_id=11, order=1, initial_question_id=11011,
    ))
    session.add(QuestionDef(id=11011, group_id=1101, type="Single", order=1))
    session.add(OptionDef(
        id=1101101, question_id=11011, related_question_ids=[],
        mutex_option_ids=[], option_group=0, order=1,
    ))
    await session.commit()


def _char(vote_id):
    return CharacterSubmitRest(
        characters=[CharacterSubmit(id="c1")],
        meta=SubmitMetadata(vote_id=vote_id),
    )


@pytest.mark.asyncio
async def test_gate_blocks_when_structured_incomplete(session):
    await _seed_required(session)
    svc = SubmitService(SubmitDAO(session))
    with pytest.raises(QuestionnaireNotCompletedError):
        await svc.submit_character(_char("u-incomplete"))


@pytest.mark.asyncio
async def test_gate_passes_when_structured_complete(session):
    from src.apps.questionnaire.dao import QuestionnaireDAO
    from src.apps.questionnaire.service import QuestionnaireService

    await _seed_required(session)
    qsvc = QuestionnaireService(QuestionnaireDAO(session))
    await qsvc.submit_answers("u-complete", 2026, {
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
    svc = SubmitService(SubmitDAO(session))
    assert await svc.submit_character(_char("u-complete")) > 0
