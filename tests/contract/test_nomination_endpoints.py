"""Contract tests for nomination admin + public endpoints (B-037)."""
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_nominations_403_without_secret(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/admin/nominations")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_nominations_list_shape(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/admin/nominations?status=pending",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data and "total" in data


@pytest.mark.asyncio
async def test_approve_nomination_404(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            "/api/v1/admin/nominations/99999/approve",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reject_nomination_404(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            "/api/v1/admin/nominations/99999/reject",
            json={"reason": "no"},
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_approved_nominations_public_shape(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/nominations/approved")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
