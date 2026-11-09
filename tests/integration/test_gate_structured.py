"""Vote gate upgrade: structured questionnaire completion (B-039)."""
import pytest

from src.apps.submit.dao import SubmitDAO
from src.apps.submit.schemas import (
    CharacterSubmit,
    CharacterSubmitRest,
    SubmitMetadata,
)
from src.apps.submit.service import QuestionnaireNotCompletedError, SubmitService
from tests.integration.test_paper_v2_validation import (
    OTHER_GROUP, OTHER_OPTION, OTHER_QN, OTHER_QUESTION, answer,
    fixed_vote_year,  # noqa: F401 — reuse the gate's current-year fixture
    seed_structure as _seed_required,
)


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
    await qsvc.submit_answers("u-complete", 2026, [
        answer(), answer(
            questionnaire_id=OTHER_QN, group_id=OTHER_GROUP,
            active_question_id=OTHER_QUESTION, selected_option_ids=[OTHER_OPTION],
        ),
    ])
    svc = SubmitService(SubmitDAO(session))
    assert await svc.submit_character(_char("u-complete")) > 0
