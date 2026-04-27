"""Token-bucket rate limiter backed by the shared Redis client."""

from __future__ import annotations

import time

from fastapi import HTTPException

from src.common.redis import get_redis

RATE_LIMIT_WINDOW_SIZE_IN_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 30


async def rate_limit(
    uid: str,
    conn=None,
    *,
    window: int = RATE_LIMIT_WINDOW_SIZE_IN_SECONDS,
    max_requests: int = RATE_LIMIT_MAX_REQUESTS,
) -> None:
    """Enforce a token-bucket rate limit for *uid*.

    Parameters
    ----------
    uid:
        Identifier to rate-limit on (vote_id, email, phone, ...).
    conn:
        Optional Redis connection override.  When *None* the shared
        client from ``common.redis`` is used.
    window:
        Window size in seconds (default 60).
    max_requests:
        Allowed requests per window (default 30).
    """
    if conn is None:
        conn = await get_redis()

    cur_time = int(time.time() * 1000)
    last_reset_key = f"rate-limit-{uid}-last-reset"
    token_key = f"rate-limit-{uid}-tokens"
    last_time_raw = await conn.get(last_reset_key)
    if last_time_raw is None:
        await conn.set(last_reset_key, cur_time)
        await conn.set(token_key, max_requests)
        last_time = cur_time
        tokens_remaining = max_requests
    else:
        last_time = int(last_time_raw)
        tokens_remaining = int((await conn.get(token_key)) or 0)

    if cur_time - last_time > window * 1000:
        await conn.set(last_reset_key, cur_time)
        await conn.set(token_key, max_requests)
    else:
        if tokens_remaining <= 0:
            raise HTTPException(status_code=429, detail="REQUEST_TOO_FREQUENT")

    await conn.decr(token_key, 1)


# Backward-compatible alias so existing imports don't break.
get_redis_client = get_redis
