"""Contract tests for candidate management endpoints."""
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_fields_403_without_secret(app, admin_secret):
    # admin_secret fixture configures a server secret; omitting the header → 403
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/admin/candidates/fields?category=character")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_fields_shape(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/admin/candidates/fields?category=music",
                            headers={"X-Admin-Secret": admin_secret})
    assert resp.status_code == 200
    data = resp.json()
    assert data["category"] == "music"
    assert any(f["name"] == "album" for f in data["fields"])


@pytest.mark.asyncio
async def test_import_shape(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/admin/candidates/import", json={
            "vote_year": 2040, "category": "character", "format": "auto",
            "content": "name\n测试角色\n", "dry_run": True,
        }, headers={"X-Admin-Secret": admin_secret})
    assert resp.status_code == 200
    data = resp.json()
    assert {"valid_count", "imported", "valid", "rejected"} <= data.keys()


@pytest.mark.asyncio
async def test_edit_404(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.put("/api/v1/admin/candidates/99999",
                            json={"category": "character", "fields": {"name_jp": "x"}},
                            headers={"X-Admin-Secret": admin_secret})
    assert resp.status_code == 404
