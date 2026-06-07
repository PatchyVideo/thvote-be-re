"""Contract tests for admin panel extension endpoints."""
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_users_403_without_secret(app, admin_secret):
    """GET /admin/users returns 403 when X-Admin-Secret header is missing."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/admin/users")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_users_list_shape(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/admin/users", headers={"X-Admin-Secret": admin_secret})
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data and "total" in data


@pytest.mark.asyncio
async def test_stats_shape(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/admin/stats", headers={"X-Admin-Secret": admin_secret})
    assert resp.status_code == 200
    data = resp.json()
    assert {"vote_year", "total_users", "vote_window", "submissions"} <= data.keys()


@pytest.mark.asyncio
async def test_candidates_shape(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/admin/candidates?category=character&vote_year=2024",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data and "total" in data


@pytest.mark.asyncio
async def test_activity_logs_shape(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/admin/activity-logs",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data and "total" in data


@pytest.mark.asyncio
async def test_export_votes_content_type(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/admin/export/votes?vote_year=2024&category=character",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")
