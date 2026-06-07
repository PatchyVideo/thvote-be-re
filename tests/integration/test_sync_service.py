"""Integration tests for the sync runner (mock MongoDB, real sqlite)."""
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock
import fakeredis.aioredis as fakeredis_mod
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db_model import Base


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_maker(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
def redis():
    return fakeredis_mod.FakeRedis()


def _oid(hex_str: str):
    # Try real ObjectId for sort to work; fall back to mock
    try:
        from bson import ObjectId
        return ObjectId(hex_str)
    except Exception:
        m = MagicMock()
        m.__str__ = MagicMock(return_value=hex_str)
        return m


@pytest.mark.asyncio
async def test_run_collection_voters(engine, session_maker, redis):
    from src.apps.admin.sync.runner import run_collection, map_voter
    from sqlalchemy import text

    oid = _oid("507f1f77bcf86cd799439011")
    docs = [{
        "_id": oid, "phone": "138", "phone_verified": True,
        "email": "a@a.com", "email_verified": True,
        "password_hashed": "hash", "salt": None,
        "created_at": datetime(2023, 1, 1, tzinfo=timezone.utc),
        "nickname": "Alice", "signup_ip": "1.1.1.1",
    }]

    mock_coll = MagicMock()
    mock_coll.count_documents.return_value = 1
    mock_coll.find.return_value.sort.return_value = iter(docs)
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_coll)

    ins, skip, err = await run_collection(
        mongo_db=mock_db, collection_name="voters", pg_table="user",
        mapper=map_voter, run_id="test-run-1", batch_size=100,
        redis=redis, session_maker=session_maker,
        error_path="/tmp/test_errors.jsonl",
    )

    assert ins == 1
    assert skip == 0
    assert err == 0

    async with session_maker() as session:
        result = await session.execute(text('SELECT email FROM "user" LIMIT 1'))
        row = result.fetchone()
    assert row is not None
    assert row[0] == "a@a.com"


@pytest.mark.asyncio
async def test_run_collection_idempotent(engine, session_maker, redis):
    """Running same data twice inserts once, skips the second time."""
    bson = pytest.importorskip("bson", reason="requires pymongo[bson]")
    ObjectId = bson.ObjectId

    from src.apps.admin.sync.runner import run_collection, map_voter

    docs = [{
        "_id": ObjectId("507f1f77bcf86cd799439011"),
        "phone": "139",  # must satisfy at_least_one_identifier CHECK constraint
        "phone_verified": False,
        "email": None, "email_verified": False,
        "password_hashed": None, "salt": None,
        "created_at": datetime(2023, 1, 1, tzinfo=timezone.utc),
        "nickname": None, "signup_ip": None,
    }]

    def make_mock_db():
        mock_coll = MagicMock()
        mock_coll.count_documents.return_value = 1
        mock_coll.find.return_value.sort.return_value = iter(docs)
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_coll)
        return mock_db

    kwargs = dict(collection_name="voters", pg_table="user", mapper=map_voter,
                  run_id="test-run-2", batch_size=100, redis=redis,
                  session_maker=session_maker, error_path="/tmp/test_errors2.jsonl")

    ins1, _, _ = await run_collection(mongo_db=make_mock_db(), **kwargs)
    ins2, skip2, _ = await run_collection(mongo_db=make_mock_db(), **kwargs)

    assert ins1 == 1
    assert ins2 == 0
    assert skip2 == 1
