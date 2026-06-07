"""Admin endpoints: compute-results, import-candidates, finalize-ranking."""

from __future__ import annotations

from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.admin.schemas import (
    BanResponse,
    ComputeResultsResponse,
    FinalizeRankingResponse,
    ImportCandidatesRequest,
    ImportCandidatesResponse,
    UserDetailResponse,
    UserListResponse,
)
from src.apps.admin.service import AdminService
from src.apps.result.compute_dao import ComputeDAO
from src.apps.result.compute_service import ComputeInProgressError, ComputeService
from src.apps.result.dao import ResultNotComputedError
from src.common.config import Settings, get_settings
from src.common.database import get_db_session
from src.common.redis import get_redis

router = APIRouter(prefix="/admin", tags=["admin"])


def _check_admin_secret(settings: Settings, secret: Optional[str]) -> None:
    if settings.admin_secret and secret != settings.admin_secret:
        raise HTTPException(status_code=403, detail="FORBIDDEN")


async def get_admin_service(
    session: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> AdminService:
    compute_dao = ComputeDAO(session)
    compute_svc = ComputeService(compute_dao, redis, settings)
    return AdminService(compute_svc, compute_dao, session)


@router.post("/compute-results", response_model=ComputeResultsResponse)
async def compute_results(
    vote_year: Optional[int] = None,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> ComputeResultsResponse:
    _check_admin_secret(settings, x_admin_secret)
    year = vote_year or settings.vote_year
    try:
        result = await service.compute_results(year)
        return ComputeResultsResponse(**result)
    except ComputeInProgressError:
        raise HTTPException(status_code=409, detail="COMPUTE_IN_PROGRESS")


@router.post("/import-candidates", response_model=ImportCandidatesResponse)
async def import_candidates(
    body: ImportCandidatesRequest,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> ImportCandidatesResponse:
    _check_admin_secret(settings, x_admin_secret)
    count = await service.import_candidates(body)
    return ImportCandidatesResponse(imported=count)


@router.post("/finalize-ranking", response_model=FinalizeRankingResponse)
async def finalize_ranking(
    vote_year: Optional[int] = None,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> FinalizeRankingResponse:
    _check_admin_secret(settings, x_admin_secret)
    year = vote_year or settings.vote_year
    try:
        saved = await service.finalize_ranking(year)
    except ResultNotComputedError:
        raise HTTPException(status_code=503, detail="RESULT_NOT_COMPUTED")
    return FinalizeRankingResponse(vote_year=year, saved=saved)


def _user_to_item(u) -> dict:
    return {
        "id": u.id,
        "nickname": u.nickname,
        "email": u.email,
        "phone": u.phone_number,
        "email_verified": u.email_verified,
        "phone_verified": u.phone_verified,
        "register_date": u.register_date.isoformat() if u.register_date else None,
        "removed": u.removed,
    }


@router.get("/users", response_model=UserListResponse)
async def list_users(
    email: Optional[str] = None,
    phone: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> UserListResponse:
    _check_admin_secret(settings, x_admin_secret)
    data = await service.list_users(email, phone, page, page_size)
    items = [_user_to_item(u) for u in data["items"]]
    return UserListResponse(items=items, total=data["total"])


@router.get("/users/{user_id}", response_model=UserDetailResponse)
async def get_user_detail(
    user_id: str,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> UserDetailResponse:
    _check_admin_secret(settings, x_admin_secret)
    result = await service.get_user_detail(user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")
    return UserDetailResponse(
        user=_user_to_item(result["user"]),
        vote_submitted=result["vote_submitted"],
    )


@router.patch("/users/{user_id}/ban", response_model=BanResponse)
async def ban_user(
    user_id: str,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> BanResponse:
    _check_admin_secret(settings, x_admin_secret)
    user = await service.ban_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")
    return BanResponse(removed=user.removed)


@router.patch("/users/{user_id}/unban", response_model=BanResponse)
async def unban_user(
    user_id: str,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> BanResponse:
    _check_admin_secret(settings, x_admin_secret)
    user = await service.unban_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")
    return BanResponse(removed=user.removed)
