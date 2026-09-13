"""POST /scraper/scrape is public; it must at least be per-IP rate limited so
nobody can use the server as a free proxy to hammer third-party sites
(and burn the server's own Pixiv credentials)."""

import os
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-do-not-use-in-prod")

from src.apps.scraper.router import get_scraper_service
from src.apps.scraper.schemas import RespBody, ScrapeData
from src.main import create_app


class _StubScraper:
    """No network: answer every URL with a canned payload."""

    async def scrape_url(self, url: str) -> RespBody:
        return RespBody(data=ScrapeData(title="stub", udid=url))


@pytest_asyncio.fixture
async def client():
    app = create_app()
    app.dependency_overrides[get_scraper_service] = lambda: _StubScraper()

    import fakeredis.aioredis as fakeredis
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    with patch("src.apps.scraper.router.get_redis_client", return_value=fake_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c


@pytest.mark.asyncio
async def test_scrape_is_rate_limited_per_ip(client):
    from src.apps.scraper.router import SCRAPE_MAX_REQUESTS_PER_WINDOW

    body = {"url": "https://www.bilibili.com/video/BV1xx411c7mD"}
    for _ in range(SCRAPE_MAX_REQUESTS_PER_WINDOW):
        resp = await client.post("/api/v1/scraper/scrape", json=body)
        assert resp.status_code == 200, resp.text

    resp = await client.post("/api/v1/scraper/scrape", json=body)
    assert resp.status_code == 429
    assert resp.json()["detail"] == "REQUEST_TOO_FREQUENT"
