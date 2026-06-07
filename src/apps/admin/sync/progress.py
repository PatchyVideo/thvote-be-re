from __future__ import annotations

import redis.asyncio as aioredis

_PROGRESS_KEY = "sync:progress:{run_id}"
_CANCEL_KEY = "sync:cancel:{run_id}"
_CURRENT_RUN_KEY = "sync:current_run"
_TTL = 86400  # 24 hours


async def set_progress(redis: aioredis.Redis, run_id: str, **fields: int | str) -> None:
    key = _PROGRESS_KEY.format(run_id=run_id)
    await redis.hset(key, mapping={k: str(v) for k, v in fields.items()})
    await redis.expire(key, _TTL)


async def get_progress(redis: aioredis.Redis, run_id: str) -> dict[str, str]:
    key = _PROGRESS_KEY.format(run_id=run_id)
    raw = await redis.hgetall(key)
    return {k.decode(): v.decode() for k, v in raw.items()}


async def set_cancel_signal(redis: aioredis.Redis, run_id: str) -> None:
    key = _CANCEL_KEY.format(run_id=run_id)
    await redis.set(key, "1", ex=3600)


async def check_cancel(redis: aioredis.Redis, run_id: str) -> bool:
    key = _CANCEL_KEY.format(run_id=run_id)
    return bool(await redis.exists(key))


async def set_current_run(redis: aioredis.Redis, run_id: str) -> None:
    await redis.set(_CURRENT_RUN_KEY, run_id, ex=_TTL)


async def get_current_run(redis: aioredis.Redis) -> str | None:
    val = await redis.get(_CURRENT_RUN_KEY)
    return val.decode() if val else None


async def clear_current_run(redis: aioredis.Redis) -> None:
    await redis.delete(_CURRENT_RUN_KEY)
