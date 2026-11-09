"""V2 administration reads submission snapshots, never individual answer rows."""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.apps.questionnaire.dao import QuestionnaireDAO
from src.db_model.questionnaire_def import (
    OptionDef, PaperAnswer, QuestionDef, QuestionGroupDef, QuestionnaireDef,
)


@pytest_asyncio.fixture
async def client(session_maker):
    from src.common.config import Settings, get_settings
    from src.common.database import get_db_session
    from src.main import create_app

    app = create_app()

    async def db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db_session] = db
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, admin_secret="test-admin-secret", vote_year=12,
        admin_allowed_ips=[],
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


HEADERS = {"X-Admin-Secret": "test-admin-secret"}
BASE = "/api/v1/admin/questionnaire-submissions"


async def seed(session):
    session.add_all([
        QuestionnaireDef(id=1, key="main", title="必填问卷", required=True),
        QuestionnaireDef(id=2, key="extra", title="额外问卷", category="extra"),
        QuestionGroupDef(id=10, questionnaire_id=1),
        QuestionGroupDef(id=20, questionnaire_id=2),
        QuestionDef(id=100, group_id=10, type="Single", content="喜欢的季节"),
        QuestionDef(id=200, group_id=20, type="Input", content="留言"),
        OptionDef(id=1000, question_id=100, content="春天"),
    ])
    await session.commit()
    return [
        {"questionnaire_id": 1, "group_id": 10, "active_question_id": 100,
         "selected_option_ids": [1000]},
        {"questionnaire_id": 2, "group_id": 20, "active_question_id": 200,
         "selected_option_ids": [], "input_text": "原始留言"},
    ]


@pytest.mark.asyncio
async def test_latest_list_filter_detail_and_whole_batch_toggle(client, session):
    rows = await seed(session)
    dao = QuestionnaireDAO(session)
    await dao.replace_answers("u1", 12, rows)
    await dao.replace_answers("u1", 12, rows)
    await dao.replace_answers("u1", 11, rows)
    await dao.replace_answers("u2", 12, rows)

    response = await client.get(BASE + "?page_size=1", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert len(response.json()["items"]) == 1
    detail = (await client.get(BASE + "/12/u1", headers=HEADERS)).json()
    assert [b["attempt"] for b in detail["batches"]] == [2, 1]
    assert detail["batches"][0]["eligible"] is True
    answer = detail["batches"][0]["questionnaires"][0]["answers"][0]
    assert answer["question_content"] == "喜欢的季节"
    assert answer["selected_options"] == [{"id": 1000, "content": "春天"}]

    changed = await client.patch(BASE + "/12/u1/2", headers=HEADERS, json={"invalidated": True})
    assert changed.status_code == 200
    assert changed.json()["affected_rows"] == 2
    valid = (await client.get(BASE + "?invalidated=false", headers=HEADERS)).json()
    assert [r["vote_id"] for r in valid["items"]] == ["u2"]
    invalid = (await client.get(BASE + "?invalidated=true", headers=HEADERS)).json()
    assert [r["vote_id"] for r in invalid["items"]] == ["u1"]
    assert invalid["items"][0]["attempt"] == 2
    assert invalid["items"][0]["completed"] is True
    assert invalid["items"][0]["eligible"] is False
    async with session.bind.connect() as connection:
        flags = (await connection.execute(select(
            PaperAnswer.vote_year, PaperAnswer.attempt, PaperAnswer.invalidated,
        ).where(PaperAnswer.vote_id == "u1"))).all()
    assert sum(bool(r.invalidated) for r in flags) == 2
    assert all(not r.invalidated for r in flags if r.vote_year == 11 or r.attempt == 1)
    restored = await client.patch(BASE + "/12/u1/2", headers=HEADERS, json={"invalidated": False})
    assert restored.status_code == 200
    assert (await client.get(BASE + "?vote_id=u1", headers=HEADERS)).json()["items"][0]["eligible"] is True


@pytest.mark.asyncio
async def test_orphaned_answers_and_legacy_batch_are_manageable(client, session):
    session.add(PaperAnswer(
        vote_id="legacy", vote_year=12, questionnaire_id=999, group_id=998,
        active_question_id=997, selected_option_ids=[996], input_text="保留原文",
    ))
    await session.commit()
    detail = (await client.get(BASE + "/12/legacy", headers=HEADERS)).json()
    batch = detail["batches"][0]
    assert batch["attempt"] == 0
    answer = batch["questionnaires"][0]["answers"][0]
    assert answer["active_question_id"] == 997
    assert answer["selected_options"] == [{"id": 996, "content": None}]
    assert answer["input_text"] == "保留原文"
    assert answer["missing_references"]
    assert (await client.patch(BASE + "/12/legacy/0", headers=HEADERS,
                               json={"invalidated": True})).status_code == 200
    assert (await client.get(BASE + "/12/missing", headers=HEADERS)).status_code == 404
    assert (await client.patch(BASE + "/12/legacy/3", headers=HEADERS,
                               json={"invalidated": True})).status_code == 404


@pytest.mark.asyncio
async def test_answer_admin_requires_admin(client):
    assert (await client.get(BASE)).status_code == 403
    assert (await client.get(BASE + "/12/u1")).status_code == 403
    assert (await client.patch(BASE + "/12/u1/1", json={"invalidated": True})).status_code == 403
