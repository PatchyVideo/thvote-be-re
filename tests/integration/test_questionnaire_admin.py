"""Integration tests for admin questionnaire config import (B-039)."""
import os

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
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


_TREE = {
    "mainQuestionnaire": {
        "requiredQuestionnaire": {
            "id": 11, "name": "必填", "introduction": "",
            "questionGroups": [{
                "id": 1101, "questionnaireId": 11, "order": 1,
                "initialQuestionId": 11011,
                "questions": [{
                    "id": 11011, "type": "Single", "content": "q1",
                    "introduction": "",
                    "options": [{
                        "id": 1101101, "content": "o1",
                        "relatedQuestionIds": [], "mutexOptionIds": [],
                        "optionGroup": 0,
                    }],
                }],
            }],
        },
        "optionalQuestionnaire1": {"id": 12, "questionGroups": []},
        "optionalQuestionnaire2": {"id": 13, "questionGroups": []},
    },
    "extraQuestionnaire": {},
}


@pytest.mark.asyncio
async def test_import_403_without_secret(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/admin/questionnaire/import?vote_year=2026", json=_TREE)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_import_then_structure(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r1 = await ac.post(
            "/api/v1/admin/questionnaire/import?vote_year=2026",
            json=_TREE, headers={"X-Admin-Secret": admin_secret},
        )
        assert r1.status_code == 200
        assert r1.json()["imported_questionnaires"] == 3

        # public structure endpoint reflects the import
        r2 = await ac.get("/api/v1/questionnaire/structure?vote_year=2026")
        assert r2.status_code == 200
        req = r2.json()["mainQuestionnaire"]["requiredQuestionnaire"]
        assert req["id"] == 11
        assert req["questionGroups"][0]["questions"][0]["id"] == 11011


@pytest.mark.asyncio
async def test_reimport_replaces(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post(
            "/api/v1/admin/questionnaire/import?vote_year=2027",
            json=_TREE, headers={"X-Admin-Secret": admin_secret},
        )
        # re-import a smaller tree: only required
        smaller = {
            "mainQuestionnaire": {
                "requiredQuestionnaire": {"id": 11, "name": "x", "questionGroups": []},
            },
            "extraQuestionnaire": {},
        }
        r = await ac.post(
            "/api/v1/admin/questionnaire/import?vote_year=2027",
            json=smaller, headers={"X-Admin-Secret": admin_secret},
        )
        assert r.json()["imported_questionnaires"] == 1
