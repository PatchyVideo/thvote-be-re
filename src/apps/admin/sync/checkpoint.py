from __future__ import annotations

import redis.asyncio as aioredis

_CHECKPOINT_KEY = "sync:checkpoint:{run_id}:{collection}"
_TTL = 7 * 86400  # 7 days


async def save_checkpoint(
    redis: aioredis.Redis, run_id: str, collection: str, last_id: str
) -> None:
    key = _CHECKPOINT_KEY.format(run_id=run_id, collection=collection)
    await redis.set(key, last_id, ex=_TTL)


async def load_checkpoint(
    redis: aioredis.Redis, run_id: str, collection: str
) -> str | None:
    key = _CHECKPOINT_KEY.format(run_id=run_id, collection=collection)
    val = await redis.get(key)
    return val.decode() if val else None
