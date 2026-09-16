"""Autocomplete API routes."""

from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.autocomplete.dao import AutocompleteDAO
from src.apps.autocomplete.schemas import AutocompleteRequest, AutocompleteResponse
from src.apps.autocomplete.service import AutocompleteService
from src.common.cache import cache_get_json, cache_set_json
from src.common.config import Settings, get_settings
from src.common.database import get_db_session
from src.common.redis import get_redis

router = APIRouter(prefix="/autocomplete", tags=["autocomplete"])

# 按 (年份, 关键词, limit) 缓存；候选名单变更时按 autocomplete: 前缀失效。
AUTOCOMPLETE_CACHE_TTL = 60


async def get_autocomplete_service(
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AutocompleteService:
    dao = AutocompleteDAO(session, settings.vote_year)
    return AutocompleteService(dao)


@router.post("/search", response_model=AutocompleteResponse)
async def search_autocomplete(
    request: AutocompleteRequest,
    service: AutocompleteService = Depends(get_autocomplete_service),
    settings: Settings = Depends(get_settings),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    """Search for autocomplete suggestions (Redis cached, 60s)."""
    query = (request.query or "").strip().lower()[:64]
    key = f"autocomplete:{settings.vote_year}:{request.limit}:{query}"
    cached = await cache_get_json(redis, key)
    if cached is not None:
        return cached
    result = await service.search(request)
    payload = result.model_dump()
    await cache_set_json(redis, key, payload, AUTOCOMPLETE_CACHE_TTL)
    return payload
