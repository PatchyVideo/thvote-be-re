"""Result query API routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.result.dao import ResultDAO
from src.apps.result.schemas import (
    CompletionRatesQuery,
    CovoteQuery,
    GlobalStats,
    GlobalStatsQuery,
    QuestionnaireQuery,
    QuestionnaireTrendQuery,
    RankingCharacterMusic,
    RankingQuery,
    ReasonQuery,
    Reasons,
    SingleQuery,
    TrendQuery,
    Trends,
)
from src.apps.result.service import ResultService
from src.common.database import get_db_session

router = APIRouter(prefix="/result", tags=["result"])


async def get_result_service(
    session: AsyncSession = Depends(get_db_session),
) -> ResultService:
    """Dependency to get ResultService instance."""
    dao = ResultDAO(session)
    return ResultService(dao)


@router.post("/ranking/", response_model=RankingCharacterMusic)
async def get_ranking(
    query: RankingQuery,
    service: ResultService = Depends(get_result_service),
) -> RankingCharacterMusic:
    """Get ranking for characters or music."""
    return await service.get_ranking(query)


@router.post("/trends/", response_model=Trends)
async def get_trends(
    query: TrendQuery,
    service: ResultService = Depends(get_result_service),
) -> Trends:
    """Get voting trends."""
    return await service.get_trends(query)


@router.post("/global-stats/", response_model=GlobalStats)
async def get_global_stats(
    query: GlobalStatsQuery,
    service: ResultService = Depends(get_result_service),
) -> GlobalStats:
    """Get global voting statistics."""
    return await service.get_global_stats(query)


@router.post("/single/", response_model=dict)
async def get_single_entity(
    query: SingleQuery,
    service: ResultService = Depends(get_result_service),
) -> dict:
    """Get a single votable entity."""
    result = await service.get_single_entity(query)
    if result is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return result


@router.post("/reasons/", response_model=Reasons)
async def get_reasons(
    query: ReasonQuery,
    service: ResultService = Depends(get_result_service),
) -> Reasons:
    """Get voting reasons for an entity."""
    return await service.get_reasons(query)


@router.post("/covote/", response_model=dict)
async def get_covote(
    query: CovoteQuery,
    service: ResultService = Depends(get_result_service),
) -> dict:
    """Get co-vote statistics between two entities."""
    return await service.get_covote(query)


@router.post("/completion-rates/", response_model=dict)
async def get_completion_rates(
    query: CompletionRatesQuery,
    service: ResultService = Depends(get_result_service),
) -> dict:
    """Get voting completion rates."""
    return await service.get_completion_rates(query)


@router.post("/questionnaire/", response_model=dict)
async def get_questionnaire(
    query: QuestionnaireQuery,
    service: ResultService = Depends(get_result_service),
) -> dict:
    """Get questionnaire data for a vote ID."""
    return await service.get_questionnaire(query)


@router.post("/questionnaire-trend/", response_model=dict)
async def get_questionnaire_trend(
    query: QuestionnaireTrendQuery,
    service: ResultService = Depends(get_result_service),
) -> dict:
    """Get questionnaire trend data."""
    return await service.get_questionnaire_trend(query)
