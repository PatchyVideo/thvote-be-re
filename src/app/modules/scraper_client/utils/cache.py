"""Scraper Redis cache module.

Provides caching functionality for scraper results using Redis.
"""

from __future__ import annotations

import pickle
from datetime import timedelta
from typing import Any

from ....common.cache.redis import get_redis_client

CACHE_PREFIX = "scraper_cache_"
RATE_LIMIT_PREFIX = "scraper_rate_limit_"


async def get_cache(key: str) -> Any | None:
    """Get value from Redis cache."""
    redis = get_redis_client()
    full_key = f"{CACHE_PREFIX}{key}"
    value = await redis.get(full_key)
    if value:
        try:
            return pickle.loads(bytes.fromhex(value))
        except Exception:
            return None
    return None


async def set_cache(
    key: str,
    value: Any,
    ex: timedelta | None = None,
) -> None:
    """Set value to Redis cache."""
    redis = get_redis_client()
    full_key = f"{CACHE_PREFIX}{key}"
    serialized = pickle.dumps(value).hex()
    if ex:
        await redis.set(full_key, serialized, ex=ex)
    else:
        await redis.set(full_key, serialized)


async def del_cache(key: str) -> int:
    """Delete a key from cache."""
    redis = get_redis_client()
    full_key = f"{CACHE_PREFIX}{key}"
    return await redis.delete(full_key)


async def get_rate_limit_last(site: str) -> float | None:
    """Get the last request timestamp for rate limiting."""
    redis = get_redis_client()
    key = f"{RATE_LIMIT_PREFIX}{site}"
    value = await redis.get(key)
    return float(value) if value else None


async def set_rate_limit_last(site: str, timestamp: float) -> None:
    """Set the last request timestamp for rate limiting."""
    redis = get_redis_client()
    key = f"{RATE_LIMIT_PREFIX}{site}"
    await redis.set(key, str(timestamp))


async def clean_scraper_cache() -> int:
    """Clean all scraper cache entries."""
    redis = get_redis_client()
    count = 0
    async for key in redis.scan_iter(match=f"{CACHE_PREFIX}*"):
        await redis.delete(key)
        count += 1
    return count
