"""GraphQL schema smoke tests -- verify field names and types exist."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

try:
    import fakeredis.aioredis as fakeredis_aioredis
    FakeRedis = fakeredis_aioredis.FakeRedis
except ImportError:
    import fakeredis
    FakeRedis = fakeredis.aioredis.FakeRedis


@pytest_asyncio.fixture
async def async_client():
    """Create an ASGI test client with fakeredis and in-memory SQLite."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from src.db_model.base import Base
    from src.common.database import get_db_session
    from src.common.redis import get_redis
    from src.main import create_app

    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(bind=eng, class_=AsyncSession, expire_on_commit=False)

    fake_redis_instance = FakeRedis(decode_responses=True)

    async def _override_get_db():
        async with maker() as session:
            yield session

    async def _override_get_redis():
        return fake_redis_instance

    app = create_app()
    app.dependency_overrides[get_db_session] = _override_get_db
    app.dependency_overrides[get_redis] = _override_get_redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    await eng.dispose()


@pytest.mark.asyncio
async def test_datetimeutc_scalar_registered(async_client):
    """DateTimeUtc scalar must be registered in the schema."""
    resp = await async_client.post(
        "/graphql",
        json={"query": '{ __type(name: "DateTimeUtc") { name kind } }'},
    )
    assert resp.status_code == 200
    data = resp.json()
    t = data["data"]["__type"]
    assert t is not None
    assert t["name"] == "DateTimeUtc"


@pytest.mark.asyncio
async def test_query_character_ranking_field_exists(async_client):
    """queryCharacterRanking must exist in the schema."""
    resp = await async_client.post(
        "/graphql",
        json={
            "query": """
            {
              __type(name: "Query") {
                fields { name }
              }
            }
            """
        },
    )
    assert resp.status_code == 200
    names = {f["name"] for f in resp.json()["data"]["__type"]["fields"]}
    assert "queryCharacterRanking" in names
    assert "queryMusicRanking" in names
    assert "queryCPRanking" in names
    assert "queryCharacterTrend" in names
    assert "queryMusicTrend" in names
    assert "queryCharacterSingle" in names
    assert "queryMusicSingle" in names
    assert "queryCPSingle" in names
    assert "queryGlobalStats" in names
    assert "queryCompletionRates" in names
    assert "queryQuestionnaire" in names
    assert "queryQuestionnaireTrend" in names
    assert "queryCharsCovote" in names
    assert "queryMusicsCovote" in names


@pytest.mark.asyncio
async def test_mutation_login_email_exists(async_client):
    """loginEmail mutation must exist in the schema."""
    resp = await async_client.post(
        "/graphql",
        json={
            "query": """
            {
              __type(name: "Mutation") {
                fields { name }
              }
            }
            """
        },
    )
    assert resp.status_code == 200
    names = {f["name"] for f in resp.json()["data"]["__type"]["fields"]}
    assert "loginEmail" in names
    assert "loginPhone" in names
    assert "loginEmailPassword" in names
    assert "requestEmailCode" in names
    assert "requestPhoneCode" in names
    assert "updateEmail" in names
    assert "updatePhone" in names
    assert "updateNickname" in names
    assert "updatePassword" in names
