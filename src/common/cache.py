"""Redis 缓存小工具：JSON/原始文本读写 + SCAN 前缀失效。

设计要点
--------
- **失败不影响业务**：缓存只是加速层，Redis 抖动/断连时记 warning 并放行
  （读 miss、写跳过），绝不能让请求 500。
- **失效用 SCAN，不用 KEYS**：``KEYS`` 在大 keyspace 会阻塞 Redis 单线程；
  ``scan_iter`` 游标遍历，生产可接受。
- 只服务**全局公共数据**（投票对象/问卷结构/自动补全/已通过提名）。
  带用户身份的数据（vote_token 维度）禁止进共享缓存。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_SCAN_COUNT = 500


async def cache_get_raw(redis: aioredis.Redis, key: str) -> Optional[str]:
    """读原始字符串；miss/异常返回 None。"""
    try:
        return await redis.get(key)
    except Exception as exc:  # noqa: BLE001 - 缓存必须 fail-open
        logger.warning("cache get failed key=%s: %s", key, exc)
        return None


async def cache_set_raw(
    redis: aioredis.Redis, key: str, payload: str, ttl_seconds: int
) -> None:
    """写原始字符串（调用方已序列化）；异常只记日志。"""
    try:
        await redis.set(key, payload, ex=ttl_seconds)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cache set failed key=%s: %s", key, exc)


async def cache_get_json(redis: aioredis.Redis, key: str) -> Optional[Any]:
    raw = await cache_get_raw(redis, key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("cache json decode failed key=%s", key)
        return None


async def cache_set_json(
    redis: aioredis.Redis, key: str, value: Any, ttl_seconds: int
) -> None:
    try:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        logger.warning("cache json encode failed key=%s", key)
        return
    await cache_set_raw(redis, key, payload, ttl_seconds)


async def invalidate_prefix(redis: aioredis.Redis, prefix: str) -> int:
    """删除所有 ``prefix*`` 键，返回删除数量；异常只记日志。"""
    deleted = 0
    try:
        async for key in redis.scan_iter(match=f"{prefix}*", count=_SCAN_COUNT):
            await redis.delete(key)
            deleted += 1
    except Exception as exc:  # noqa: BLE001
        logger.warning("cache invalidate failed prefix=%s: %s", prefix, exc)
    return deleted
