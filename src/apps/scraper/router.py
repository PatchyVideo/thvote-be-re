"""Scraper API routes."""

import logging

from fastapi import APIRouter, Depends

from src.apps.scraper.schemas import ReqBody, RespBody
from src.apps.scraper.service import ScraperService
from src.apps.user.deps import get_client_ip
from src.common.middleware.rate_limit import get_redis_client, rate_limit

router = APIRouter(prefix="/scraper", tags=["scraper"])
logger = logging.getLogger(__name__)

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
    result = await service.scrape_url(body.url)
    if result.msg:
        logger.warning("Scraper result %s: %r", result.status, result.msg[:400])
        public_message = "获取信息失败" if result.status == "except" else ""
        return result.model_copy(update={"msg": public_message})
    return result
