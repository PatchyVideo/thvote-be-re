"""Integration tests for the admin security-monitoring API (B-049)."""
import os

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport  # noqa: F401 (used by later B-049 tasks)
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
async def db_session(engine) -> AsyncSession:
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s


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


async def _seed_char(session, vote_id, user_ip, device=None, fill=None, env=None):
    from src.db_model.raw_submit import RawCharacterSubmit
    session.add(RawCharacterSubmit(
        vote_id=vote_id, user_ip=user_ip, additional_fingreprint=device,
        fill_duration_ms=fill, client_env=env, payload=[1, 2], attempt=1,
    ))
    await session.commit()


@pytest.mark.asyncio
async def test_category_totals_and_ip_groups(db_session):
    from src.apps.admin.monitor.dao import MonitorDAO
    # two accounts share one IP, a third is alone
    await _seed_char(db_session, "u1", "1.1.1.1")
    await _seed_char(db_session, "u2", "1.1.1.1")
    await _seed_char(db_session, "u3", "2.2.2.2")

    dao = MonitorDAO(db_session)
    totals = await dao.category_totals()
    assert totals["character"] == 3

    groups = await dao.ip_groups(min_size=2, limit=10)
    assert groups == [{"key": "1.1.1.1", "voter_count": 2}]

    members = await dao.group_members("ip", "1.1.1.1")
    assert sorted(members) == ["u1", "u2"]


@pytest.mark.asyncio
async def test_list_votes_filters_and_pagination(db_session):
    from src.apps.admin.monitor.dao import MonitorDAO
    await _seed_char(db_session, "u1", "1.1.1.1", fill=500)
    await _seed_char(db_session, "u2", "9.9.9.9", fill=8000)

    dao = MonitorDAO(db_session)
    rows, total = await dao.list_votes(
        category="character", vote_id=None, user_ip="1.1.1.1",
        device=None, invalidated=None, page=1, page_size=20,
    )
    assert total == 1
    assert rows[0]["vote_id"] == "u1"
    assert rows[0]["fill_duration_ms"] == 500
