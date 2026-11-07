"""Public candidate search API routes."""

from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.autocomplete.dao import AutocompleteDAO
from src.apps.autocomplete.schemas import (
    CandidateSearchRequest,
    CandidateSearchResponse,
)
from src.apps.autocomplete.service import CandidateSearchService
from src.common.config import Settings, get_settings
from src.common.database import get_db_session
from src.common.redis import get_redis

router = APIRouter(prefix="/autocomplete", tags=["autocomplete"])


async def get_candidate_search_service(
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    redis: aioredis.Redis = Depends(get_redis),
) -> CandidateSearchService:
    return CandidateSearchService(
        AutocompleteDAO(session), redis, settings.vote_year
    )


@router.post("/search", response_model=CandidateSearchResponse)
async def search_candidates(
    request: CandidateSearchRequest,
    service: CandidateSearchService = Depends(get_candidate_search_service),
) -> CandidateSearchResponse:
    return await service.search(request)
