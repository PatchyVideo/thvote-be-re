"""管理端安全监控 REST 端点(B-049)。挂在 /api/v1/admin/monitor,require_admin 守卫。"""

from __future__ import annotations

from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.admin.deps import require_admin
from src.apps.admin.monitor.dao import CATEGORY_MODELS, MonitorDAO
from src.apps.admin.monitor.schemas import (
    AccountDetail,
    ActionResult,
    GroupsResponse,
    OverviewResponse,
    ReviewRequest,
    SuspectsResponse,
    VotesPage,
)
from src.apps.admin.monitor.service import MonitorService
from src.common.config import Settings, get_settings
from src.common.database import get_db_session
from src.common.redis import get_redis

monitor_router = APIRouter(
    prefix="/admin/monitor",
    tags=["admin-monitor"],
    dependencies=[Depends(require_admin)],
)


def _service(
    session: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> MonitorService:
    return MonitorService(session, redis, settings)


@monitor_router.get("/overview", response_model=OverviewResponse)
async def overview(svc: MonitorService = Depends(_service)) -> OverviewResponse:
    return await svc.overview()


@monitor_router.get("/groups", response_model=GroupsResponse)
async def groups(
    kind: str = Query("ip", pattern="^(ip|device)$"),
    min_size: int = Query(2, ge=1),
    limit: int = Query(100, ge=1, le=1000),
    svc: MonitorService = Depends(_service),
) -> GroupsResponse:
    return await svc.groups(kind, min_size, limit)


@monitor_router.get("/groups/{kind}/{key}/members", response_model=list[str])
async def group_members(
    kind: str, key: str, session: AsyncSession = Depends(get_db_session)
) -> list[str]:
    if kind not in ("ip", "device"):
        raise HTTPException(status_code=422, detail="kind must be ip|device")
    return await MonitorDAO(session).group_members(kind, key)


@monitor_router.get("/suspects", response_model=SuspectsResponse)
async def suspects(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    svc: MonitorService = Depends(_service),
) -> SuspectsResponse:
    return await svc.suspects(page, page_size)


@monitor_router.get("/votes", response_model=VotesPage)
async def votes(
    category: str = Query(...),
    vote_id: Optional[str] = None,
    user_ip: Optional[str] = None,
    device: Optional[str] = None,
    invalidated: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    svc: MonitorService = Depends(_service),
) -> VotesPage:
    if category not in CATEGORY_MODELS:
        raise HTTPException(
            status_code=422,
            detail=f"category must be one of {list(CATEGORY_MODELS)}",
        )
    return await svc.list_votes(
        category, vote_id, user_ip, device, invalidated, page, page_size
    )


@monitor_router.get("/account/{vote_id}", response_model=AccountDetail)
async def account(
    vote_id: str, session: AsyncSession = Depends(get_db_session)
) -> AccountDetail:
    from src.db_model.voter_review import VoterReview

    dao = MonitorDAO(session)
    votes_map = await dao.account_votes(vote_id)
    review_obj = await session.get(VoterReview, vote_id)
    review = (
        {"status": review_obj.status, "note": review_obj.note,
         "updated_at": review_obj.updated_at.isoformat()}
        if review_obj else None
    )
    own_ips = sorted({r["user_ip"] for rows in votes_map.values() for r in rows})
    own_devs = sorted({r["device"] for rows in votes_map.values()
                       for r in rows if r["device"]})
    return AccountDetail(
        vote_id=vote_id, votes=votes_map, review=review,
        ip_groups=own_ips, device_groups=own_devs,
    )


# ── 处置动作(仅记录;影响排名属 B-050)────────────────────────────────────

_B050_NOTE = "已记录;影响排名需 B-050 计票重写落地后生效"


async def _set_invalidated(category: str, row_id: int, value: bool,
                           session: AsyncSession) -> ActionResult:
    if category not in CATEGORY_MODELS:
        raise HTTPException(status_code=422, detail="unknown category")
    ok = await MonitorDAO(session).set_invalidated(category, row_id, value)
    if not ok:
        raise HTTPException(status_code=404, detail="vote row not found")
    return ActionResult(ok=True, detail=_B050_NOTE)


@monitor_router.patch(
    "/vote/{category}/{row_id}/invalidate", response_model=ActionResult)
async def invalidate_vote(
    category: str, row_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> ActionResult:
    return await _set_invalidated(category, row_id, True, session)


@monitor_router.patch(
    "/vote/{category}/{row_id}/restore", response_model=ActionResult)
async def restore_vote(
    category: str, row_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> ActionResult:
    return await _set_invalidated(category, row_id, False, session)


@monitor_router.patch("/account/{vote_id}/review", response_model=ActionResult)
async def review_account(
    vote_id: str, body: ReviewRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ActionResult:
    await MonitorDAO(session).upsert_review(vote_id, body.status, body.note)
    return ActionResult(ok=True, detail="review recorded")
