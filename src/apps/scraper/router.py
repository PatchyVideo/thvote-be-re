"""Scraper API routes."""

from fastapi import APIRouter, Depends

from src.apps.scraper.schemas import ReqBody, RespBody
from src.apps.scraper.service import ScraperService

router = APIRouter(prefix="/scraper", tags=["scraper"])


async def get_scraper_service() -> ScraperService:
    """Dependency to get ScraperService instance."""
    return ScraperService()


@router.post("/scrape", response_model=RespBody)
async def scrape_url(
    body: ReqBody,
    service: ScraperService = Depends(get_scraper_service),
) -> RespBody:
    """Scrape data from a URL."""
    return await service.scrape_url(body.url)
