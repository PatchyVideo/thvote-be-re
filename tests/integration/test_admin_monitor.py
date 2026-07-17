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


@pytest.mark.asyncio
async def test_max_ip_group_size_is_max_not_union(db_session):
    from src.apps.admin.monitor.dao import MonitorDAO
    # IP group A = {u1, u2, u3} on 1.1.1.1 (size 3)
    await _seed_char(db_session, "u1", "1.1.1.1", fill=1500)
    await _seed_char(db_session, "u2", "1.1.1.1")
    await _seed_char(db_session, "u3", "1.1.1.1")
    # IP group B = {u1, u4, u5, u6} on 2.2.2.2 (size 4) -- u1 is in BOTH groups
    await _seed_char(db_session, "u1", "2.2.2.2", fill=900)
    await _seed_char(db_session, "u4", "2.2.2.2")
    await _seed_char(db_session, "u5", "2.2.2.2")
    await _seed_char(db_session, "u6", "2.2.2.2")

    dao = MonitorDAO(db_session)
    features = await dao.account_features("u1")
    # the larger single group (B, size 4), NOT the union of A and B (6)
    assert features.max_ip_group_size == 4
    # happy-path: min_fill_duration_ms reflects the smallest seeded fill for u1
    assert features.min_fill_duration_ms == 900
    # u1 was seeded with no client_env at all
    assert features.has_client_env is False


@pytest.mark.asyncio
async def test_ip_groups_excludes_unknown_sentinel(db_session):
    from src.apps.admin.monitor.dao import MonitorDAO
    await _seed_char(db_session, "u1", "<unknown>")
    await _seed_char(db_session, "u2", "<unknown>")
    await _seed_char(db_session, "u3", "<unknown>")
    await _seed_char(db_session, "u4", "5.5.5.5")
    await _seed_char(db_session, "u5", "5.5.5.5")

    dao = MonitorDAO(db_session)
    groups = await dao.ip_groups(min_size=2, limit=10)
    assert groups == [{"key": "5.5.5.5", "voter_count": 2}]


@pytest.mark.asyncio
async def test_submissions_by_day_buckets(db_session):
    from src.apps.admin.monitor.dao import MonitorDAO
    await _seed_char(db_session, "u1", "1.1.1.1")
    await _seed_char(db_session, "u2", "2.2.2.2")

    dao = MonitorDAO(db_session)
    rows = await dao.submissions_by_day()
    assert sum(r["count"] for r in rows) == 2
    for r in rows:
        assert isinstance(r["date"], str)
        assert len(r["date"]) == 10  # YYYY-MM-DD, not a bare year


@pytest.mark.asyncio
async def test_candidate_vote_ids_selects_suspicious(db_session):
    from src.apps.admin.monitor.dao import MonitorDAO
    await _seed_char(db_session, "u1", "1.1.1.1", fill=200, env=None)
    await _seed_char(
        db_session, "u2", "2.2.2.2", fill=9000, env={"ua": "Mozilla/5.0"}
    )

    dao = MonitorDAO(db_session)
    candidates = await dao.candidate_vote_ids(
        cluster_min=5, fast_fill_ms=2000, cap=100
    )
    assert "u1" in candidates
    assert "u2" not in candidates


@pytest.mark.asyncio
async def test_distinct_ip_and_device_counts(db_session):
    from src.apps.admin.monitor.dao import MonitorDAO
    await _seed_char(db_session, "u1", "1.1.1.1", device="dev-a")
    await _seed_char(db_session, "u2", "1.1.1.1", device="dev-a")
    await _seed_char(db_session, "u3", "2.2.2.2", device="dev-b")

    dao = MonitorDAO(db_session)
    assert await dao.distinct_ip_count() == 2
    assert await dao.distinct_device_count() == 2


@pytest.mark.asyncio
async def test_service_suspects_ranks_fast_fill(db_session):
    import fakeredis
    from src.apps.admin.monitor.service import MonitorService
    from src.common.config import get_settings

    await _seed_char(db_session, "bot", "3.3.3.3", fill=200, env=None)   # suspicious
    await _seed_char(db_session, "human", "4.4.4.4", fill=9000,
                     env={"ua": "Mozilla/5.0"})                          # clean

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    svc = MonitorService(db_session, redis, get_settings())
    page = await svc.suspects(page=1, page_size=20)
    ids = [s.vote_id for s in page.items]
    assert "bot" in ids
    top = page.items[0]
    assert top.vote_id == "bot"
    assert top.score >= 3
    assert top.reasons


@pytest.mark.asyncio
async def test_overview_endpoint_requires_secret(app):
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        resp = await ac.get("/api/v1/admin/monitor/overview")   # no header
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_overview_endpoint_returns_totals(app, db_session, admin_secret):
    await _seed_char(db_session, "u1", "1.1.1.1")
    await _seed_char(db_session, "u2", "1.1.1.1")
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        resp = await ac.get("/api/v1/admin/monitor/overview",
                            headers={"X-Admin-Secret": admin_secret})
    assert resp.status_code == 200
    body = resp.json()
    assert body["category_totals"]["character"] == 2
    assert body["distinct_ips"] == 1


@pytest.mark.asyncio
async def test_votes_endpoint_filter(app, db_session, admin_secret):
    await _seed_char(db_session, "u1", "1.1.1.1", fill=500)
    await _seed_char(db_session, "u2", "9.9.9.9")
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/admin/monitor/votes?category=character&user_ip=1.1.1.1",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["vote_id"] == "u1"


@pytest.mark.asyncio
async def test_votes_endpoint_rejects_bad_category(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/admin/monitor/votes?category=bogus",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invalidate_and_restore_vote(app, db_session, admin_secret):
    from src.db_model.raw_submit import RawCharacterSubmit
    row = RawCharacterSubmit(vote_id="u1", user_ip="1.1.1.1", payload=[1], attempt=1)
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    rid = row.id

    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        h = {"X-Admin-Secret": admin_secret}
        r1 = await ac.patch(
            f"/api/v1/admin/monitor/vote/character/{rid}/invalidate", headers=h)
        assert r1.status_code == 200 and r1.json()["ok"] is True
        # verify flag via the votes listing
        r2 = await ac.get(
            "/api/v1/admin/monitor/votes?category=character&invalidated=true",
            headers=h)
        assert r2.json()["total"] == 1
        r3 = await ac.patch(
            f"/api/v1/admin/monitor/vote/character/{rid}/restore", headers=h)
        assert r3.status_code == 200
        r4 = await ac.get(
            "/api/v1/admin/monitor/votes?category=character&invalidated=true",
            headers=h)
        assert r4.json()["total"] == 0


@pytest.mark.asyncio
async def test_invalidate_unknown_row_404(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        r = await ac.patch(
            "/api/v1/admin/monitor/vote/character/999999/invalidate",
            headers={"X-Admin-Secret": admin_secret})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_review_upsert(app, db_session, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        h = {"X-Admin-Secret": admin_secret}
        r = await ac.patch(
            "/api/v1/admin/monitor/account/u1/review",
            headers=h, json={"status": "suspicious", "note": "shared IP"})
        assert r.status_code == 200 and r.json()["ok"] is True
        # second upsert overwrites, still one row, reflected in account detail
        await ac.patch(
            "/api/v1/admin/monitor/account/u1/review",
            headers=h, json={"status": "cleared", "note": ""})
        detail = await ac.get(
            "/api/v1/admin/monitor/account/u1", headers=h)
    assert detail.json()["review"]["status"] == "cleared"
