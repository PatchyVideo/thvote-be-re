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


def _ranking_docs(oid):
    return [{
        "_id": oid, "vote_year": 12, "rank": 1, "name": "博丽灵梦",
        "vote_count": 100, "first_vote_count": 40,
    }]


def _mock_db(docs):
    mock_coll = MagicMock()
    mock_coll.count_documents.return_value = len(docs)
    mock_coll.find.return_value.sort.return_value = iter(docs)
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_coll)
    return mock_db


@pytest.mark.asyncio
async def test_run_collection_final_ranking(engine, session_maker, redis):
    from src.apps.admin.sync.runner import run_collection, map_final_ranking
    from sqlalchemy import text

    docs = _ranking_docs(_oid("507f1f77bcf86cd799439011"))

    ins, skip, err = await run_collection(
        mongo_db=_mock_db(docs), collection_name="final_ranking_char",
        pg_table="final_ranking",
        mapper=lambda d: map_final_ranking(d, "character"), run_id="test-run-1",
        batch_size=100, redis=redis, session_maker=session_maker,
        error_path="/tmp/test_errors.jsonl",
    )

    assert (ins, skip, err) == (1, 0, 0)

    async with session_maker() as session:
        result = await session.execute(
            text("SELECT name, category FROM final_ranking LIMIT 1")
        )
        row = result.fetchone()
    assert row is not None
    assert tuple(row) == ("博丽灵梦", "character")


@pytest.mark.asyncio
async def test_run_collection_idempotent(engine, session_maker, redis):
    """Running same data twice inserts once, skips the second time."""
    bson = pytest.importorskip("bson", reason="requires pymongo[bson]")

    from src.apps.admin.sync.runner import run_collection, map_final_ranking

    docs = _ranking_docs(bson.ObjectId("507f1f77bcf86cd799439011"))
    kwargs = dict(collection_name="final_ranking_char", pg_table="final_ranking",
                  mapper=lambda d: map_final_ranking(d, "character"),
                  run_id="test-run-2", batch_size=100, redis=redis,
                  session_maker=session_maker, error_path="/tmp/test_errors2.jsonl")

    ins1, _, _ = await run_collection(mongo_db=_mock_db(docs), **kwargs)
    ins2, skip2, _ = await run_collection(mongo_db=_mock_db(docs), **kwargs)

    assert ins1 == 1
    assert ins2 == 0
    assert skip2 == 1
