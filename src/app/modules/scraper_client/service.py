"""Scraper service layer."""

from .process import get_data
from .schemas import RespBody


class ScraperService:
    """Service for scraping operations."""

    async def scrape_url(self, url: str) -> RespBody:
        return await get_data(url)
