"""R-01 / D-08: structured questionnaire answers must reference the structure.

Covers the exploit chain reported by backend testing: forged answer rows were
stored verbatim and then counted as "questionnaire completed", unlocking voting.
Both layers are asserted here — the write path (``submitPaperV2`` →
``QuestionnaireService.submit_answers``) and the read-side gate
(``SubmitService._require_questionnaire``).
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from src.apps.submit.dao import SubmitDAO
from src.apps.submit.schemas import (
    CharacterSubmit,
    CharacterSubmitRest,
    SubmitMetadata,
)
from src.apps.submit.service import QuestionnaireNotCompletedError, SubmitService
from src.common.exceptions import ValidationError
from src.common.security.jwt import create_vote_token
from src.db_model.questionnaire_def import (
    OptionDef,
    QuestionDef,
    QuestionGroupDef,
    QuestionnaireDef,
)

REQUIRED_QN = 11          # 必填问卷
REQUIRED_GROUP = 1101     # 题组(order 1, 默认可见)
REQUIRED_QUESTION = 11011  # Single 题
OPTION_A = 1101101
OPTION_B = 1101102
OTHER_QN = 12             # 非必填问卷(用于跨问卷越权用例)
OTHER_GROUP = 1201
OTHER_QUESTION = 12011
OTHER_OPTION = 1201101

VOTE_YEAR = 2026


@pytest.fixture(autouse=True)
def fixed_vote_year(monkeypatch):
    """Pin the gate's year so the test does not depend on the local .env (T-01)."""
    from src.common.config import get_settings

    monkeypatch.setattr(get_settings(), "vote_year", VOTE_YEAR)


async def seed_structure(session):
    session.add(QuestionnaireDef(
        id=REQUIRED_QN, key="main_required", category="main",
        title="必填", introduction="", required=True, order=1,
    ))
    session.add(QuestionGroupDef(
        id=REQUIRED_GROUP, questionnaire_id=REQUIRED_QN, order=1,
        hidden_by_default=False,
    ))
    session.add(QuestionDef(
        id=REQUIRED_QUESTION, group_id=REQUIRED_GROUP, type="Single", order=1,
        max_input_len=100,
    ))
    for order, option_id in enumerate((OPTION_A, OPTION_B), start=1):
        session.add(OptionDef(
            id=option_id, question_id=REQUIRED_QUESTION, content=f"o{order}",
            related_question_ids=[], mutex_option_ids=[], option_group=0,
            order=order,
        ))
    session.add(QuestionnaireDef(
        id=OTHER_QN, key="sub_optional", category="main",
        title="分问卷", introduction="", required=False, order=2,
    ))
    session.add(QuestionGroupDef(
        id=OTHER_GROUP, questionnaire_id=OTHER_QN, order=1,
        hidden_by_default=False,
    ))
    session.add(QuestionDef(
        id=OTHER_QUESTION, group_id=OTHER_GROUP, type="Single", order=1,
        max_input_len=100,
    ))
    session.add(OptionDef(
        id=OTHER_OPTION, question_id=OTHER_QUESTION, content="o1",
        related_question_ids=[], mutex_option_ids=[], option_group=0, order=1,
    ))
    await session.commit()


def answer(
    questionnaire_id=REQUIRED_QN,
    group_id=REQUIRED_GROUP,
    active_question_id=REQUIRED_QUESTION,
    selected_option_ids=(OPTION_A,),
    text="",
):
    return {
        "questionnaireId": questionnaire_id,
        "groupId": group_id,
        "activeQuestionId": active_question_id,
        "selectedOptionIds": list(selected_option_ids),
        "input": text,
    }


def _char(vote_id: str) -> CharacterSubmitRest:
    return CharacterSubmitRest(
        characters=[CharacterSubmit(id="c1")],
        meta=SubmitMetadata(vote_id=vote_id),
    )


def _qsvc(session):
    from src.apps.questionnaire.dao import QuestionnaireDAO
    from src.apps.questionnaire.service import QuestionnaireService

    return QuestionnaireService(QuestionnaireDAO(session))


# ── write path: reference validation ──────────────────────────────────────

@pytest.mark.asyncio
async def test_forged_questionnaire_id_rejected(session):
    await seed_structure(session)
    with pytest.raises(ValidationError) as ei:
        await _qsvc(session).submit_answers(
            "u-forged", 2026, [answer(questionnaire_id=999999)]
        )
    assert ei.value.message == "INVALID_PAPER_ANSWER"
    assert await _qsvc(session).get_answers("u-forged", 2026) == []


@pytest.mark.asyncio
async def test_cross_questionnaire_group_rejected(session):
    """(OTHER_QN, group of REQUIRED_QN) must not alias into the required paper."""
    await seed_structure(session)
    with pytest.raises(ValidationError) as ei:
        await _qsvc(session).submit_answers(
            "u-cross", 2026, [answer(questionnaire_id=OTHER_QN)]
        )
    assert ei.value.message == "INVALID_PAPER_ANSWER"


@pytest.mark.asyncio
async def test_group_of_other_questionnaire_rejected(session):
    """A real group id used under the wrong questionnaire is still rejected."""
    await seed_structure(session)
    with pytest.raises(ValidationError):
        await _qsvc(session).submit_answers(
            "u-cross2", 2026,
            [answer(group_id=OTHER_GROUP, active_question_id=OTHER_QUESTION,
                    selected_option_ids=[OTHER_OPTION])],
        )


@pytest.mark.asyncio
async def test_unknown_option_rejected(session):
    await seed_structure(session)
    with pytest.raises(ValidationError) as ei:
        await _qsvc(session).submit_answers(
            "u-option", 2026, [answer(selected_option_ids=[999999])]
        )
    assert ei.value.message == "INVALID_PAPER_ANSWER"


@pytest.mark.asyncio
async def test_duplicate_rows_rejected(session):
    await seed_structure(session)
    with pytest.raises(ValidationError):
        await _qsvc(session).submit_answers(
            "u-dup", 2026, [answer(), answer(selected_option_ids=[OPTION_B])]
        )


@pytest.mark.asyncio
async def test_unknown_active_question_rejected(session):
    await seed_structure(session)
    with pytest.raises(ValidationError):
        await _qsvc(session).submit_answers(
            "u-question", 2026,
            [answer(active_question_id=OTHER_QUESTION)],
        )


# ── read path: the gate ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_answer_rows_do_not_unlock_voting(session):
    """Valid ids + no content = stored, but the gate stays closed (R-01)."""
    await seed_structure(session)
    await _qsvc(session).submit_answers(
        "u-empty", 2026, [answer(active_question_id=None, selected_option_ids=[])]
    )
    assert await _qsvc(session).is_complete("u-empty", 2026) is False
    with pytest.raises(QuestionnaireNotCompletedError):
        await SubmitService(SubmitDAO(session)).submit_character(_char("u-empty"))


@pytest.mark.asyncio
async def test_valid_answers_unlock_voting(session):
    await seed_structure(session)
    await _qsvc(session).submit_answers("u-ok", 2026, [answer()])
    assert await _qsvc(session).is_complete("u-ok", 2026) is True
    assert await SubmitService(SubmitDAO(session)).submit_character(_char("u-ok")) > 0


# ── GraphQL resolver: submitPaperV2 ──────────────────────────────────────

SUBMIT_PAPER_V2 = """
mutation($voteToken: String!, $answers: JSON!) {
  submitPaperV2(voteToken: $voteToken, answers: $answers)
}
"""

GET_PAPER_V2 = """
query($voteToken: String!) { getPaperV2(voteToken: $voteToken) }
"""


def _vote_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    return create_vote_token(user_id, now - timedelta(hours=1), now + timedelta(days=1))


@pytest_asyncio.fixture
async def gql(monkeypatch, session, patch_redis):
    """Real schema; resolver's db + redis swapped for the test fixtures."""
    import src.api.graphql.resolvers.questionnaire_v2 as q2

    async def _fake_db():
        yield session

    async def _fake_redis():
        return patch_redis

    monkeypatch.setattr(q2, "get_db_session", _fake_db)
    monkeypatch.setattr(q2, "get_redis_client", _fake_redis)

    from src.api.graphql.schema import schema

    return schema


@pytest.mark.asyncio
async def test_graphql_forged_answers_return_invalid_paper_answer(gql, session):
    await seed_structure(session)
    token = _vote_token("gql-forged")
    result = await gql.execute(
        SUBMIT_PAPER_V2,
        variable_values={
            "voteToken": token,
            "answers": [answer(selected_option_ids=[999999])],
        },
        context_value={},
    )
    assert result.errors, "forged answers must not be accepted"
    ext = result.errors[0].extensions
    assert ext["error_kind"] == "INVALID_PAPER_ANSWER"
    assert ext["human_readable_message"]
    read = await gql.execute(
        GET_PAPER_V2, variable_values={"voteToken": token}, context_value={}
    )
    assert read.data["getPaperV2"] == []


@pytest.mark.asyncio
async def test_graphql_empty_answers_rejected(gql, session):
    await seed_structure(session)
    token = _vote_token("gql-empty")
    result = await gql.execute(
        SUBMIT_PAPER_V2,
        variable_values={"voteToken": token, "answers": []},
        context_value={},
    )
    assert result.errors
    assert result.errors[0].extensions["error_kind"] == "EMPTY_PAPER_SUBMIT"


@pytest.mark.asyncio
async def test_graphql_valid_answers_persist_and_unlock(gql, session):
    await seed_structure(session)
    token = _vote_token("gql-ok")
    result = await gql.execute(
        SUBMIT_PAPER_V2,
        variable_values={"voteToken": token, "answers": [answer()]},
        context_value={},
    )
    assert result.errors is None, result.errors
    assert result.data["submitPaperV2"] is True

    read = await gql.execute(
        GET_PAPER_V2, variable_values={"voteToken": token}, context_value={}
    )
    rows = read.data["getPaperV2"]
    assert [r["selected_option_ids"] for r in rows] == [[OPTION_A]]

    with_db = SubmitService(SubmitDAO(session))
    assert await with_db.submit_character(_char("gql-ok")) > 0


@pytest.mark.asyncio
async def test_graphql_fake_json_shape_rejected(gql, session):
    """A non-list payload must be a validation error, never INTERNAL_ERROR."""
    await seed_structure(session)
    result = await gql.execute(
        SUBMIT_PAPER_V2,
        variable_values={
            "voteToken": _vote_token("gql-shape"),
            "answers": json.loads('{"questionnaireId": 11}'),
        },
        context_value={},
    )
    assert result.errors
    assert result.errors[0].extensions["error_kind"] == "INVALID_PAPER_ANSWER"
