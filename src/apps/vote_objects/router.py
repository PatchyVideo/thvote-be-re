"""Vote-objects public router: grouped candidate listings for the voting page."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.vote_objects.dao import VoteObjectsDAO
from src.apps.vote_objects.service import VoteObjectsService
from src.common.config import Settings, get_settings
from src.common.database import get_db_session

router = APIRouter(prefix="/vote-objects", tags=["vote-objects"])


async def get_vote_objects_service(
    session: AsyncSession = Depends(get_db_session),
) -> VoteObjectsService:
    return VoteObjectsService(VoteObjectsDAO(session))


@router.get("/characters")
async def list_characters(
    vote_year: Optional[int] = None,
    service: VoteObjectsService = Depends(get_vote_objects_service),
    settings: Settings = Depends(get_settings),
) -> dict:
    return await service.characters(vote_year or settings.vote_year)


@router.get("/music")
async def list_music(
    vote_year: Optional[int] = None,
    service: VoteObjectsService = Depends(get_vote_objects_service),
    settings: Settings = Depends(get_settings),
) -> dict:
    return await service.music(vote_year or settings.vote_year)


@router.get("/{category}/{candidate_id}")
async def get_detail(
    category: str,
    candidate_id: int,
    service: VoteObjectsService = Depends(get_vote_objects_service),
) -> dict:
    if category not in ("character", "music"):
        raise HTTPException(status_code=404, detail="UNKNOWN_CATEGORY")
    obj = await service.detail(category, candidate_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return obj
