"""Rate-limit helpers reused by submit and scraper flows."""

from __future__ import annotations

import time

from fastapi import HTTPException
from redis.asyncio import Redis

from ..cache.redis import get_redis_client

RATE_LIMIT_WINDOW_SIZE_IN_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 30


async def rate_limit(uid: str, conn: Redis | None = None) -> None:
    """Apply a fixed-window token bucket compatible with the legacy branch."""
    redis = conn or get_redis_client()
    cur_time = int(time.time() * 1000)
    last_reset_key = f"rate-limit-{uid}-last-reset"
    token_key = f"rate-limit-{uid}-tokens"

    last_time_raw = await redis.get(last_reset_key)
    if last_time_raw is None:
        await redis.set(last_reset_key, cur_time)
        await redis.set(token_key, RATE_LIMIT_MAX_REQUESTS)
        last_time = cur_time
        tokens_remaining = RATE_LIMIT_MAX_REQUESTS
    else:
        last_time = int(last_time_raw)
        tokens_remaining = int((await redis.get(token_key)) or 0)

    if cur_time - last_time > RATE_LIMIT_WINDOW_SIZE_IN_SECONDS * 1000:
        await redis.set(last_reset_key, cur_time)
        await redis.set(token_key, RATE_LIMIT_MAX_REQUESTS)
    elif tokens_remaining <= 0:
        raise HTTPException(status_code=429, detail="REQUEST_TOO_FREQUENT")

    await redis.decr(token_key, 1)
