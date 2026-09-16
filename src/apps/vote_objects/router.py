"""Vote-objects public router: grouped candidate listings for the voting page.

0019 起响应含资源字段（imageUrl/aliases/musicUrl/include），单次可达 100~255KB。
这里加一层 Redis 缓存：命中直接回缓存字节（跳过 DB join 与序列化），
GZipMiddleware 仍会压缩；管理端写入时按 `vote_objects:` 前缀失效。
"""

from __future__ import annotations

import json
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.vote_objects.dao import VoteObjectsDAO
from src.apps.vote_objects.service import VoteObjectsService
from src.common.cache import cache_get_raw, cache_set_raw
from src.common.config import Settings, get_settings
from src.common.database import get_db_session
from src.common.redis import get_redis

router = APIRouter(prefix="/vote-objects", tags=["vote-objects"])

# 投票对象是全局公共数据，只随管理端写入变化（写入即失效）。
VOTE_OBJECTS_CACHE_TTL = 600


def _json_response(payload: str) -> Response:
    return Response(content=payload, media_type="application/json")


async def get_vote_objects_service(
    session: AsyncSession = Depends(get_db_session),
) -> VoteObjectsService:
    return VoteObjectsService(VoteObjectsDAO(session))


@router.get("/characters")
async def list_characters(
    vote_year: Optional[int] = None,
    service: VoteObjectsService = Depends(get_vote_objects_service),
    settings: Settings = Depends(get_settings),
    redis: aioredis.Redis = Depends(get_redis),
) -> Response:
    year = vote_year or settings.vote_year
    key = f"vote_objects:{year}:characters"
    cached = await cache_get_raw(redis, key)
    if cached is not None:
        return _json_response(cached)
    data = await service.characters(year)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    await cache_set_raw(redis, key, payload, VOTE_OBJECTS_CACHE_TTL)
    return _json_response(payload)


@router.get("/music")
async def list_music(
    vote_year: Optional[int] = None,
    service: VoteObjectsService = Depends(get_vote_objects_service),
    settings: Settings = Depends(get_settings),
    redis: aioredis.Redis = Depends(get_redis),
) -> Response:
    year = vote_year or settings.vote_year
    key = f"vote_objects:{year}:music"
    cached = await cache_get_raw(redis, key)
    if cached is not None:
        return _json_response(cached)
    data = await service.music(year)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    await cache_set_raw(redis, key, payload, VOTE_OBJECTS_CACHE_TTL)
    return _json_response(payload)


@router.get("/{category}/{candidate_id}")
async def get_detail(
    category: str,
    candidate_id: int,
    service: VoteObjectsService = Depends(get_vote_objects_service),
    redis: aioredis.Redis = Depends(get_redis),
) -> Response:
    if category not in ("character", "music"):
        raise HTTPException(status_code=404, detail="UNKNOWN_CATEGORY")
    key = f"vote_objects:detail:{category}:{candidate_id}"
    cached = await cache_get_raw(redis, key)
    if cached is not None:
        return _json_response(cached)
    obj = await service.detail(category, candidate_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    await cache_set_raw(redis, key, payload, VOTE_OBJECTS_CACHE_TTL)
    return _json_response(payload)
