"""Scraper data access objects."""

from __future__ import annotations

from hashlib import md5
from typing import TYPE_CHECKING

from .utils.cache import get_cache as redis_get_cache, set_cache as redis_set_cache

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from .schemas import RespBody


class ScraperDAO:
    """Data access object for scraper operations."""

    def __init__(self, session: AsyncSession | None = None):
        self.session = session

    async def cache_scrape_result(self, url: str, data: RespBody) -> None:
        """Cache scrape result to Redis."""
        cache_key = f"scraper_url:{md5(url.encode()).hexdigest()}"
        await redis_set_cache(cache_key, data)

    async def get_cached_result(self, url: str) -> RespBody | None:
        """Get cached scrape result from Redis."""
        cache_key = f"scraper_url:{md5(url.encode()).hexdigest()}"
        return await redis_get_cache(cache_key)

    async def cache_by_udid(self, udid: str, data: RespBody) -> None:
        """Cache result by UDID (unique identifier)."""
        await redis_set_cache(f"scraper_udid:{udid}", data)

    async def get_by_udid(self, udid: str) -> RespBody | None:
        """Get cached result by UDID."""
        return await redis_get_cache(f"scraper_udid:{udid}")
