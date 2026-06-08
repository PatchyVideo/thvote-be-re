"""Integration tests for questionnaire admin import + CRUD endpoints (B-041)."""
import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db_model.base import Base


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def app(engine):
    from src.common.database import get_db_session
    from src.common.redis import get_redis
    from src.main import create_app

    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db():
        async with maker() as s:
            yield s

    async def _override_get_redis():
        import fakeredis
        return fakeredis.aioredis.FakeRedis(decode_responses=True)

    a = create_app()
    a.dependency_overrides[get_db_session] = _override_get_db
    a.dependency_overrides[get_redis] = _override_get_redis
    yield a


@pytest.fixture
def admin_secret():
    secret = os.environ.get("ADMIN_SECRET", "test-admin-secret")
    os.environ["ADMIN_SECRET"] = secret
    import src.common.config as cfg
    cfg._settings_instance = None
    yield secret
    cfg._settings_instance = None


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


_TREE = {"questionnaires": [
    {"id": 1, "key": "main_required", "title": "必填", "category": "main",
     "required": True, "order": 1, "questionGroups": [
        {"id": 10, "order": 1, "hiddenByDefault": False, "questions": [
            {"id": 100, "type": "Single", "content": "q1", "introduction": "",
             "maxInputLen": 1000, "options": [
                {"id": 1000, "content": "o1", "relatedQuestionIds": [],
                 "mutexOptionIds": [], "optionGroup": 0}]}]}]},
    {"id": 2, "key": "extra_1", "title": "额外", "category": "extra",
     "required": False, "order": 2, "questionGroups": []},
]}


@pytest.mark.asyncio
async def test_import_403_without_secret(app, admin_secret):
    async with _client(app) as ac:
        resp = await ac.post("/api/v1/admin/questionnaire/import", json=_TREE)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_import_then_public_structure(app, admin_secret):
    async with _client(app) as ac:
        r1 = await ac.post("/api/v1/admin/questionnaire/import", json=_TREE,
                           headers={"X-Admin-Secret": admin_secret})
        assert r1.status_code == 200
        assert r1.json()["imported_questionnaires"] == 2
        r2 = await ac.get("/api/v1/questionnaire/structure")
        assert r2.status_code == 200
        qs = r2.json()["questionnaires"]
        assert {q["key"] for q in qs} == {"main_required", "extra_1"}


@pytest.mark.asyncio
async def test_crud_flow(app, admin_secret):
    h = {"X-Admin-Secret": admin_secret}
    async with _client(app) as ac:
        r = await ac.post("/api/v1/admin/questionnaires",
                          json={"key": "k1", "title": "t1", "category": "main",
                                "required": True, "order": 1}, headers=h)
        assert r.status_code == 200
        qid = r.json()["id"]
        # list
        lst = await ac.get("/api/v1/admin/questionnaires", headers=h)
        assert any(i["id"] == qid for i in lst.json()["items"])
        # add group/question/option
        g = await ac.post("/api/v1/admin/question-groups",
                          json={"questionnaire_id": qid, "order": 1}, headers=h)
        gid = g.json()["id"]
        qn = await ac.post("/api/v1/admin/questions",
                           json={"group_id": gid, "type": "Single", "content": "q"},
                           headers=h)
        quid = qn.json()["id"]
        o = await ac.post("/api/v1/admin/options",
                          json={"question_id": quid, "content": "o"}, headers=h)
        assert o.status_code == 200
        # get tree
        tree = await ac.get(f"/api/v1/admin/questionnaires/{qid}", headers=h)
        groups = tree.json()["questionGroups"]
        first_option = groups[0]["questions"][0]["options"][0]
        assert first_option["id"] == o.json()["id"]
        # delete
        d = await ac.delete(f"/api/v1/admin/questionnaires/{qid}", headers=h)
        assert d.status_code == 200
        nf = await ac.get(f"/api/v1/admin/questionnaires/{qid}", headers=h)
        assert nf.status_code == 404


@pytest.mark.asyncio
async def test_key_conflict_409(app, admin_secret):
    h = {"X-Admin-Secret": admin_secret}
    async with _client(app) as ac:
        await ac.post("/api/v1/admin/questionnaires",
                      json={"key": "dup", "title": "a"}, headers=h)
        r = await ac.post("/api/v1/admin/questionnaires",
                          json={"key": "dup", "title": "b"}, headers=h)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_create_group_parent_404(app, admin_secret):
    h = {"X-Admin-Secret": admin_secret}
    async with _client(app) as ac:
        r = await ac.post("/api/v1/admin/question-groups",
                          json={"questionnaire_id": 999999, "order": 1}, headers=h)
    assert r.status_code == 404
