"""Unified async Redis client management.

Provides a singleton-style Redis connection used across the application:
- Rate limiting (middleware)
- Verification code storage (user module)
- Distributed locks (submit module)
"""

from __future__ import annotations

from typing import Any

import redis.asyncio as aioredis

from src.common.config import get_settings

_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Return a shared async Redis client, creating it on first call."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
    return _client


async def close_redis() -> None:
    """Close the Redis connection. Call during application shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# ── Distributed lock helpers ────────────────────────────────────────

import uuid


async def acquire_lock(
    key: str,
    timeout_ms: int = 10_000,
) -> str | None:
    """Try to acquire a Redis-based distributed lock.

    Returns the lock value on success, None if already held.
    """
    conn = await get_redis()
    lock_value = str(uuid.uuid4())
    acquired = await conn.set(key, lock_value, nx=True, px=timeout_ms)
    if not acquired:
        return None
    return lock_value


async def release_lock(key: str, lock_value: str) -> None:
    """Release a distributed lock only if we still own it."""
    conn = await get_redis()
    current = await conn.get(key)
    if current == lock_value:
        await conn.delete(key)
