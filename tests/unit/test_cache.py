"""Redis 缓存工具单测（fail-open + JSON 往返 + SCAN 前缀失效）。"""
from __future__ import annotations

import fakeredis.aioredis
import pytest

from src.common.cache import (
    cache_get_json,
    cache_get_raw,
    cache_set_json,
    cache_set_raw,
    invalidate_prefix,
)


@pytest.mark.asyncio
async def test_cache_roundtrip_and_prefix_invalidate():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    try:
        await cache_set_json(r, "vote_objects:12:characters", {"a": 1, "中文": [1, 2]}, 60)
        assert await cache_get_json(r, "vote_objects:12:characters") == {
            "a": 1,
            "中文": [1, 2],
        }
        await cache_set_raw(r, "vote_objects:12:music", "{}", 60)
        await cache_set_json(r, "questionnaire:structure:12", {"x": 1}, 60)

        deleted = await invalidate_prefix(r, "vote_objects:")
        assert deleted == 2
        assert await cache_get_json(r, "vote_objects:12:characters") is None
        assert await cache_get_raw(r, "vote_objects:12:music") is None
        # 其他 scope 不受影响
        assert await cache_get_json(r, "questionnaire:structure:12") == {"x": 1}
    finally:
        await r.aclose()


@pytest.mark.asyncio
async def test_cache_fail_open_when_redis_down():
    class Boom:
        async def get(self, *a, **k):
            raise RuntimeError("redis down")

        async def set(self, *a, **k):
            raise RuntimeError("redis down")

        def scan_iter(self, *a, **k):
            raise RuntimeError("redis down")

    boom = Boom()
    assert await cache_get_raw(boom, "k") is None  # type: ignore[arg-type]
    assert await cache_get_json(boom, "k") is None  # type: ignore[arg-type]
    await cache_set_raw(boom, "k", "v", 1)  # type: ignore[arg-type]  不抛
    await cache_set_json(boom, "k", {"a": 1}, 1)  # type: ignore[arg-type]
    assert await invalidate_prefix(boom, "k:") == 0  # type: ignore[arg-type]
