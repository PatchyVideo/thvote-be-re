"""Scraper API routes."""

from fastapi import APIRouter, Depends

from ...modules.scraper_client.schemas import ReqBody, RespBody
from ...modules.scraper_client.service import ScraperService

router = APIRouter(prefix="/internal/scraper", tags=["scraper"])


async def get_scraper_service() -> ScraperService:
    return ScraperService()


@router.post("/scrape", response_model=RespBody)
async def scrape_url(
    body: ReqBody,
    service: ScraperService = Depends(get_scraper_service),
) -> RespBody:
    return await service.scrape_url(body.url)
