"""Scraper service layer."""

from src.apps.scraper.process import get_data
from src.apps.scraper.schemas import RespBody


class ScraperService:
    """Service for scraping operations."""

    async def scrape_url(self, url: str) -> RespBody:
        """Scrape data from a URL.

        Args:
            url: URL to scrape

        Returns:
            RespBody containing scraped data or error status
        """
        return await get_data(url)
