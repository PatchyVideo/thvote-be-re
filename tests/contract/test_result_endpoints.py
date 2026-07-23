"""Contract tests: result endpoints return 503 before compute, 200 after."""

from __future__ import annotations

import json

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
async def client():
    """Create an ASGI test client with fakeredis and in-memory SQLite."""
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )
    from src.db_model.base import Base
    from src.common.database import get_db_session
    from src.common.redis import get_redis
    from src.main import create_app

    # In-memory SQLite engine
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(bind=eng, class_=AsyncSession, expire_on_commit=False)

    # Fakeredis instance
    fake_redis_instance = FakeRedis(decode_responses=True)

    # Override dependencies
    async def _override_get_db():
        async with maker() as session:
            yield session

    async def _override_get_redis():
        return fake_redis_instance

    app = create_app()
    app.dependency_overrides[get_db_session] = _override_get_db
    app.dependency_overrides[get_redis] = _override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    await eng.dispose()


_ALICE = {"category": "character", "name": "Alice"}

RESULT_ENDPOINTS = [
    ("POST", "/api/v1/result/ranking/", {"category": "character"}),
    ("POST", "/api/v1/result/trends/", _ALICE),
    ("POST", "/api/v1/result/global-stats/", {}),
    ("POST", "/api/v1/result/single/", _ALICE),
    ("POST", "/api/v1/result/reasons/", _ALICE),
    ("POST", "/api/v1/result/covote/", {"category": "character"}),
    ("POST", "/api/v1/result/completion-rates/", {}),
    ("POST", "/api/v1/result/questionnaire/", {"question_id": "q11011"}),
    ("POST", "/api/v1/result/questionnaire-trend/", {"question_id": "q11011"}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,body", RESULT_ENDPOINTS)
async def test_result_endpoints_503_before_compute(client, method, path, body):
    resp = await client.request(method, path, json=body)
    assert resp.status_code == 503, (
        f"{path} expected 503, got {resp.status_code}: {resp.text}"
    )
    assert resp.json()["detail"] == "RESULT_NOT_COMPUTED"


@pytest.mark.asyncio
async def test_admin_compute_results_endpoint_reachable(client, admin_secret):
    """先经统一导入通道(Task 4)播种一个角色候选。

    Task 6 起 compute_all 的白名单改读 DB(不再是 JSON 快照永远非空)——两个
    分类的白名单都为空时会报 WHITELIST_EMPTY(见 compute_service.py)，不再是
    "无候选也能算出一份空结果"的旧行为，所以这里必须先播种至少一个候选，
    这条用例才能验证的是"端点可达"而不是白名单为空的错误路径。
    """
    seed_resp = await client.post(
        "/api/v1/admin/voteables/import",
        json={
            "category": "character", "vote_year": 2026, "format": "json",
            "content": json.dumps([{"name": "Alice", "old_id": "aaaa1111"}]),
            "dry_run": False,
        },
        headers={"X-Admin-Secret": admin_secret},
    )
    assert seed_resp.status_code == 200
    assert not seed_resp.json().get("conflicts")

    resp = await client.post(
        "/api/v1/admin/compute-results",
        params={"vote_year": 2026},
        headers={"X-Admin-Secret": admin_secret},
    )
    # Returns 200 with empty data (no votes seeded), not 404
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True


@pytest.mark.asyncio
async def test_admin_import_candidates_endpoint_reachable(client, admin_secret):
    resp = await client.post(
        "/api/v1/admin/import-candidates",
        json={
            "vote_year": 2026,
            "category": "character",
            "items": [
                {
                    "name": "Alice",
                    "name_jp": "アリス",
                    "origin": "EoSD",
                    "type": "旧作",
                }
            ],
        },
        headers={"X-Admin-Secret": admin_secret},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
