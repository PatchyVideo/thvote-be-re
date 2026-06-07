"""Contract tests: sync endpoint wire format."""
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_sync_start_no_secret(app, admin_secret):
    """Without secret header, returns 403."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/admin/sync/start", json={})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_sync_start_no_mongodb(app, admin_secret):
    """Without MONGODB_URI configured, returns 503."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/admin/sync/start",
            json={},
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 503
    assert resp.json()["detail"] == "MONGODB_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_sync_status_shape(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/admin/sync/status",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "run_id" in data


@pytest.mark.asyncio
async def test_sync_history_shape(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/admin/sync/history",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
