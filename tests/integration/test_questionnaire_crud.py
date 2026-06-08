"""Integration tests for questionnaire admin CRUD + cascade (B-041)."""
import pytest

from src.apps.questionnaire.admin_dao import QuestionnaireAdminDAO
from src.apps.questionnaire.admin_service import (
    KeyConflictError,
    ParentNotFoundError,
    QuestionnaireAdminService,
)


def _svc(session):
    return QuestionnaireAdminService(QuestionnaireAdminDAO(session))


@pytest.mark.asyncio
async def test_full_crud_and_cascade(session):
    svc = _svc(session)
    qid = await svc.create_questionnaire(
        {"key": "a", "title": "必填", "category": "main", "required": True, "order": 1}
    )
    gid = await svc.create_group({"questionnaire_id": qid, "order": 1})
    quid = await svc.create_question(
        {"group_id": gid, "type": "Single", "content": "q"}
    )
    oid = await svc.create_option({"question_id": quid, "content": "o"})

    tree = await svc.get_questionnaire(qid)
    assert tree["key"] == "a"
    assert tree["questionGroups"][0]["questions"][0]["options"][0]["id"] == oid

    assert await svc.update_question(quid, {"content": "q2"}) is True
    upd = await svc.get_questionnaire(qid)
    assert upd["questionGroups"][0]["questions"][0]["content"] == "q2"

    assert await svc.delete_questionnaire(qid) is True
    assert await svc.get_questionnaire(qid) is None
    assert await svc.get_question(quid) is None  # cascade removed descendants


@pytest.mark.asyncio
async def test_list_questionnaires_with_group_count(session):
    svc = _svc(session)
    qid = await svc.create_questionnaire({"key": "k1", "title": "t1"})
    await svc.create_group({"questionnaire_id": qid, "order": 1})
    await svc.create_group({"questionnaire_id": qid, "order": 2})
    items = await svc.list_questionnaires()
    row = next(i for i in items if i["id"] == qid)
    assert row["key"] == "k1"
    assert row["group_count"] == 2


@pytest.mark.asyncio
async def test_key_conflict(session):
    svc = _svc(session)
    await svc.create_questionnaire({"key": "dup", "title": "x"})
    with pytest.raises(KeyConflictError):
        await svc.create_questionnaire({"key": "dup", "title": "y"})


@pytest.mark.asyncio
async def test_update_questionnaire_key_conflict(session):
    svc = _svc(session)
    await svc.create_questionnaire({"key": "k_a", "title": "a"})
    bid = await svc.create_questionnaire({"key": "k_b", "title": "b"})
    with pytest.raises(KeyConflictError):
        await svc.update_questionnaire(bid, {"key": "k_a"})


@pytest.mark.asyncio
async def test_parent_not_found(session):
    svc = _svc(session)
    with pytest.raises(ParentNotFoundError):
        await svc.create_group({"questionnaire_id": 999999, "order": 1})
    with pytest.raises(ParentNotFoundError):
        await svc.create_question({"group_id": 999999, "type": "Single"})
    with pytest.raises(ParentNotFoundError):
        await svc.create_option({"question_id": 999999, "content": "o"})


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_false(session):
    svc = _svc(session)
    assert await svc.delete_questionnaire(999999) is False
    assert await svc.get_questionnaire(999999) is None
