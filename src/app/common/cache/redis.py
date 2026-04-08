"""Shared Redis helpers."""

from functools import lru_cache

from redis.asyncio import Redis

from ..config import get_settings


@lru_cache
def get_redis_client() -> Redis:
    """Return a cached asyncio Redis client."""
    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)
