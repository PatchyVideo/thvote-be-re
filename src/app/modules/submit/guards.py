"""Submit guards: rate limiting and vote locking."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import TypeVar

from fastapi import HTTPException

from ...common.cache.redis import get_redis_client
from ...common.middleware.rate_limit import rate_limit

T = TypeVar("T")

LOCK_EXPIRE_MS = 10_000


async def _acquire_vote_lock(vote_id: str) -> tuple[str, str]:
    redis_client = get_redis_client()
    lock_key = f"lock-submit-{vote_id}"
    lock_value = str(uuid.uuid4())
    acquired = await redis_client.set(lock_key, lock_value, nx=True, px=LOCK_EXPIRE_MS)
    if not acquired:
        raise HTTPException(status_code=429, detail="SUBMIT_LOCKED")
    return lock_key, lock_value


async def _release_vote_lock(lock_key: str, lock_value: str) -> None:
    redis_client = get_redis_client()
    current = await redis_client.get(lock_key)
    if current == lock_value:
        await redis_client.delete(lock_key)


async def guarded_submit(vote_id: str, callback: Callable[[], Awaitable[T]]) -> T:
    """Apply rate limiting and vote locking, then run callback."""
    await rate_limit(vote_id)
    lock_key, lock_value = await _acquire_vote_lock(vote_id)
    try:
        return await callback()
    finally:
        await _release_vote_lock(lock_key, lock_value)
