"""Scraper API routes."""

from fastapi import APIRouter, Depends

from src.apps.scraper.schemas import ReqBody, RespBody
from src.apps.scraper.service import ScraperService
from src.apps.user.deps import get_client_ip
from src.common.middleware.rate_limit import get_redis_client, rate_limit

router = APIRouter(prefix="/scraper", tags=["scraper"])

# Public endpoint that makes outbound calls (partly with the server's own
# Pixiv credentials) — per-IP cap so it can't be used as a free proxy.
# A real user pastes a handful of links while filling the dojin form.
SCRAPE_WINDOW_SECONDS = 60
SCRAPE_MAX_REQUESTS_PER_WINDOW = 10


async def get_scraper_service() -> ScraperService:
    """Dependency to get ScraperService instance."""
    return ScraperService()


@router.post("/scrape", response_model=RespBody)
async def scrape_url(
    body: ReqBody,
    service: ScraperService = Depends(get_scraper_service),
    client_ip: str = Depends(get_client_ip),
) -> RespBody:
    """Scrape data from a URL (per-IP rate limited)."""
    await rate_limit(
        f"scraper-ip-{client_ip}",
        await get_redis_client(),
        window=SCRAPE_WINDOW_SECONDS,
        max_requests=SCRAPE_MAX_REQUESTS_PER_WINDOW,
    )
    return await service.scrape_url(body.url)
