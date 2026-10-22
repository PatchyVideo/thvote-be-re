"""Questionnaire public router: structure query."""

from __future__ import annotations

import json

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.questionnaire.dao import QuestionnaireDAO
from src.apps.questionnaire.service import QuestionnaireService
from src.common.cache import cache_get_raw, cache_set_raw
from src.common.config import Settings, get_settings
from src.common.database import get_db_session
from src.common.redis import get_redis

router = APIRouter(prefix="/questionnaire", tags=["questionnaire"])

# 问卷结构是全局公共数据，只随管理端 CRUD/整树导入变化（写入即失效）。
QUESTIONNAIRE_CACHE_TTL = 1800


async def get_questionnaire_service(
    session: AsyncSession = Depends(get_db_session),
) -> QuestionnaireService:
    return QuestionnaireService(QuestionnaireDAO(session))


@router.get("/structure")
async def get_structure(
    service: QuestionnaireService = Depends(get_questionnaire_service),
    settings: Settings = Depends(get_settings),
    redis: aioredis.Redis = Depends(get_redis),
) -> Response:
    key = f"questionnaire:structure:{settings.vote_year}"
    cached = await cache_get_raw(redis, key)
    if cached is not None:
        return Response(content=cached, media_type="application/json")
    data = await service.get_structure()
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    await cache_set_raw(redis, key, payload, QUESTIONNAIRE_CACHE_TTL)
    return Response(content=payload, media_type="application/json")
