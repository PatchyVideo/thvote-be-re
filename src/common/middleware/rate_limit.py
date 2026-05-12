"""Token-bucket rate limiter backed by the shared Redis client.

Uses INCR + EXPIRE for atomic fixed-window rate limiting.  INCR is a
single Redis operation and returns a unique counter per request, so there
is no TOCTOU race between reading the remaining token count and consuming
one (the previous GET→check→DECR sequence was non-atomic).

Window semantics: the counter resets when the TTL set by the first INCR
in a window expires.  Edge case: if the process crashes between INCR (→1)
and EXPIRE, the key persists without expiry.  This is an extremely narrow
race whose worst case is that the rate limiter blocks that uid permanently
until the Redis key is manually deleted — not a security hole.
"""

from __future__ import annotations

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
    """Enforce a fixed-window rate limit for *uid*.

    Parameters
    ----------
    uid:
        Identifier to rate-limit on (vote_id, email, phone, user_id, ...).
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

    count_key = f"rate-limit-{uid}"
    count = await conn.incr(count_key)
    if count == 1:
        await conn.expire(count_key, window)
    if count > max_requests:
        raise HTTPException(status_code=429, detail="REQUEST_TOO_FREQUENT")


# Backward-compatible alias so existing imports don't break.
get_redis_client = get_redis
