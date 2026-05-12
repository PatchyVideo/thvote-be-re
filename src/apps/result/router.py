"""Result query API routes."""

from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException

from src.apps.result.dao import EntityNotFoundError, ResultDAO, ResultNotComputedError
from src.apps.result.schemas import (
    CompletionRatesQuery,
    CovoteQuery,
    GlobalStatsQuery,
    QuestionnaireQuery,
    QuestionnaireTrendQuery,
    RankingQuery,
    ReasonQuery,
    SingleQuery,
    TrendQuery,
)
from src.apps.result.service import ResultService
from src.common.config import Settings, get_settings
from src.common.redis import get_redis

router = APIRouter(prefix="/result", tags=["result"])


async def get_result_service(
    redis: aioredis.Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> ResultService:
    dao = ResultDAO(redis, settings)
    return ResultService(dao)


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, ResultNotComputedError):
        raise HTTPException(status_code=503, detail="RESULT_NOT_COMPUTED")
    if isinstance(exc, EntityNotFoundError):
        raise HTTPException(status_code=404, detail="ENTITY_NOT_FOUND")
    raise exc


@router.post("/ranking/", response_model=dict)
async def get_ranking(
    query: RankingQuery,
    service: ResultService = Depends(get_result_service),
) -> dict:
    try:
        return await service.get_ranking(query)
    except (ResultNotComputedError, EntityNotFoundError) as e:
        _raise_http(e)


@router.post("/trends/", response_model=dict)
async def get_trends(
    query: TrendQuery,
    service: ResultService = Depends(get_result_service),
) -> dict:
    try:
        return await service.get_trends(query)
    except (ResultNotComputedError, EntityNotFoundError) as e:
        _raise_http(e)


@router.post("/global-stats/", response_model=dict)
async def get_global_stats(
    query: GlobalStatsQuery,
    service: ResultService = Depends(get_result_service),
) -> dict:
    try:
        return await service.get_global_stats(query)
    except ResultNotComputedError as e:
        _raise_http(e)


@router.post("/single/", response_model=dict)
async def get_single_entity(
    query: SingleQuery,
    service: ResultService = Depends(get_result_service),
) -> dict:
    try:
        return await service.get_single_entity(query)
    except (ResultNotComputedError, EntityNotFoundError) as e:
        _raise_http(e)


@router.post("/reasons/", response_model=dict)
async def get_reasons(
    query: ReasonQuery,
    service: ResultService = Depends(get_result_service),
) -> dict:
    try:
        return await service.get_reasons(query)
    except (ResultNotComputedError, EntityNotFoundError) as e:
        _raise_http(e)


@router.post("/covote/", response_model=dict)
async def get_covote(
    query: CovoteQuery,
    service: ResultService = Depends(get_result_service),
) -> dict:
    try:
        return await service.get_covote(query)
    except ResultNotComputedError as e:
        _raise_http(e)


@router.post("/completion-rates/", response_model=dict)
async def get_completion_rates(
    query: CompletionRatesQuery,
    service: ResultService = Depends(get_result_service),
) -> dict:
    try:
        return await service.get_completion_rates(query)
    except ResultNotComputedError as e:
        _raise_http(e)


@router.post("/questionnaire/", response_model=dict)
async def get_questionnaire(
    query: QuestionnaireQuery,
    service: ResultService = Depends(get_result_service),
) -> dict:
    try:
        return await service.get_questionnaire(query)
    except ResultNotComputedError as e:
        _raise_http(e)


@router.post("/questionnaire-trend/", response_model=dict)
async def get_questionnaire_trend(
    query: QuestionnaireTrendQuery,
    service: ResultService = Depends(get_result_service),
) -> dict:
    try:
        return await service.get_questionnaire_trend(query)
    except ResultNotComputedError as e:
        _raise_http(e)
