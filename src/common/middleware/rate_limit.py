from __future__ import annotations

import time
from typing import Any

from fastapi import HTTPException

from src.common.config import get_settings

RATE_LIMIT_WINDOW_SIZE_IN_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 30

try:
    import redis.asyncio as redis_async

    _USE_REDIS_ASYNCIO = True
except Exception:  # pragma: no cover
    import aioredis as redis_async  # type: ignore

    _USE_REDIS_ASYNCIO = False


async def get_redis_client() -> Any:
    settings = get_settings()
    if _USE_REDIS_ASYNCIO:
        return redis_async.from_url(settings.redis_url, decode_responses=True)
    # aioredis v1 API
    return await redis_async.create_redis_pool(settings.redis_url, encoding="utf-8")


async def rate_limit(uid: str, conn: Any) -> None:
    cur_time = int(time.time() * 1000)
    last_reset_key = f"rate-limit-{uid}-last-reset"
    token_key = f"rate-limit-{uid}-tokens"
    last_time_raw = await conn.get(last_reset_key)
    if last_time_raw is None:
        await conn.set(last_reset_key, cur_time)
        await conn.set(token_key, RATE_LIMIT_MAX_REQUESTS)
        last_time = cur_time
        tokens_remaining = RATE_LIMIT_MAX_REQUESTS
    else:
        last_time = int(last_time_raw)
        tokens_remaining = int((await conn.get(token_key)) or 0)

    if cur_time - last_time > RATE_LIMIT_WINDOW_SIZE_IN_SECONDS * 1000:
        await conn.set(last_reset_key, cur_time)
        await conn.set(token_key, RATE_LIMIT_MAX_REQUESTS)
    else:
        if tokens_remaining <= 0:
            raise HTTPException(status_code=429, detail="REQUEST_TOO_FREQUENT")

    await conn.decr(token_key, 1)
