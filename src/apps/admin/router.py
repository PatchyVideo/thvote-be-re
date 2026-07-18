"""Admin endpoints: compute-results, import-candidates, finalize-ranking."""

from __future__ import annotations

import logging
import secrets
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.apps.admin.deps import require_admin
from src.apps.admin.schemas import (
    ActivityLogResponse,
    BanResponse,
    CandidateFieldsResponse,
    CandidateImportRequest,
    CandidateImportResponse,
    CandidateListResponse,
    CandidateUpdateRequest,
    ComputeResultsResponse,
    FinalizeRankingResponse,
    ImportCandidatesRequest,
    ImportCandidatesResponse,
    NominationListResponse,
    NominationRejectRequest,
    StatsResponse,
    SyncHistoryResponse,
    SyncStartRequest,
    SyncStartResponse,
    SyncStatusResponse,
    UserDetailResponse,
    UserListResponse,
)
from src.apps.admin.service import AdminService, SyncService
from src.apps.admin.sync.progress import set_current_run
from src.apps.result.compute_dao import ComputeDAO
from src.apps.result.compute_service import ComputeInProgressError, ComputeService
from src.apps.result.dao import ResultNotComputedError
from src.common.config import Settings, get_settings
from src.common.database import get_db_session, get_session_maker
from src.common.redis import get_redis

_logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    # B-049:统一鉴权闸门(secret 必填 + IP 白名单,fail-closed)。
    dependencies=[Depends(require_admin)],
)


def _check_admin_secret(settings: Settings, secret: Optional[str]) -> None:
    # belt-and-suspenders:router 级 require_admin 已是主闸门,这里保留仅为
    # 冗余兜底(同样返回 403),不再是唯一防线。
    if settings.admin_secret and (
        not secret or not secrets.compare_digest(secret, settings.admin_secret)
    ):
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


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    vote_year: Optional[int] = None,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> StatsResponse:
    _check_admin_secret(settings, x_admin_secret)
    data = await service.get_stats(vote_year)
    return StatsResponse(**data)


@router.get("/ranking/preview")
async def preview_ranking(
    category: str = "character",
    vote_year: Optional[int] = None,
    limit: int = 50,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    entries = await service.get_ranking_preview(vote_year, category, limit)
    return {"category": category, "entries": entries}


@router.get("/candidates", response_model=CandidateListResponse)
async def list_candidates(
    category: str = "character",
    vote_year: Optional[int] = None,
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> CandidateListResponse:
    _check_admin_secret(settings, x_admin_secret)
    year = vote_year or settings.vote_year
    data = await service.list_candidates(category, year, q, page, page_size)
    items = [
        {
            "id": r.id, "vote_year": r.vote_year, "name": r.name,
            "name_jp": r.name_jp or "",
            "type": r.type or "",
            "origin": getattr(r, "origin", None),
            "first_appearance": r.first_appearance,
            "album": getattr(r, "album", None),
        }
        for r in data["items"]
    ]
    return CandidateListResponse(items=items, total=data["total"])


@router.get("/candidates/fields", response_model=CandidateFieldsResponse)
async def candidate_fields(
    category: str = "character",
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> CandidateFieldsResponse:
    _check_admin_secret(settings, x_admin_secret)
    return CandidateFieldsResponse(
        category=category, fields=service.get_candidate_fields(category)
    )


@router.post("/candidates/import", response_model=CandidateImportResponse)
async def import_candidates_content(
    body: CandidateImportRequest,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> CandidateImportResponse:
    _check_admin_secret(settings, x_admin_secret)
    result = await service.import_candidates_from_content(
        body.vote_year, body.category, body.format, body.content, body.dry_run
    )
    if "parse_error" in result:
        raise HTTPException(status_code=400, detail=result["parse_error"])
    return CandidateImportResponse(**result)


@router.put("/candidates/{candidate_id}")
async def update_candidate(
    candidate_id: int,
    body: CandidateUpdateRequest,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    result = await service.update_candidate(candidate_id, body.category, body.fields)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="CANDIDATE_NOT_FOUND")
    if result == "conflict":
        raise HTTPException(status_code=409, detail="CANDIDATE_NAME_CONFLICT")
    return {"ok": True}


@router.delete("/candidates/{candidate_id}")
async def delete_candidate(
    candidate_id: int,
    category: str = "character",
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    deleted = await service.delete_candidate(candidate_id, category)
    if not deleted:
        raise HTTPException(status_code=404, detail="CANDIDATE_NOT_FOUND")
    return {"ok": True}


@router.get("/candidates/merges")
async def list_candidate_merges(
    category: str = "character",
    vote_year: Optional[int] = None,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    year = vote_year or settings.vote_year
    return {"items": await service.list_merges(category, year)}


@router.post("/candidates/{candidate_id}/merge-into/{target_id}")
async def merge_candidate(
    candidate_id: int,
    target_id: int,
    category: str = "character",
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    result = await service.merge_candidate(candidate_id, target_id, category)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="CANDIDATE_NOT_FOUND")
    if result == "target_not_found":
        raise HTTPException(status_code=404, detail="TARGET_NOT_FOUND")
    if result == "self":
        raise HTTPException(status_code=400, detail="CANNOT_MERGE_SELF")
    return {"ok": True}


@router.post("/candidates/{candidate_id}/unmerge")
async def unmerge_candidate(
    candidate_id: int,
    category: str = "character",
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    result = await service.unmerge_candidate(candidate_id, category)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="CANDIDATE_NOT_FOUND")
    return {"ok": True}


def _nomination_to_item(n) -> dict:
    return {
        "id": n.id,
        "vote_id": n.vote_id,
        "udid": n.udid,
        "url": n.url,
        "title": n.title,
        "author": n.author,
        "dojin_type": n.dojin_type,
        "publish_date": n.publish_date.isoformat() if n.publish_date else None,
        "status": n.status,
        "reject_reason": n.reject_reason,
        "created_at": n.created_at.isoformat(),
    }


@router.get("/nominations", response_model=NominationListResponse)
async def list_nominations(
    status: str = "pending",
    page: int = 1,
    page_size: int = 50,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> NominationListResponse:
    _check_admin_secret(settings, x_admin_secret)
    data = await service.list_nominations(status, page, page_size)
    items = [_nomination_to_item(n) for n in data["items"]]
    return NominationListResponse(items=items, total=data["total"])


@router.patch("/nominations/{nomination_id}/approve")
async def approve_nomination(
    nomination_id: int,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    ok = await service.review_nomination(nomination_id, approve=True, reason="")
    if not ok:
        raise HTTPException(status_code=404, detail="NOMINATION_NOT_FOUND")
    return {"ok": True}


@router.patch("/nominations/{nomination_id}/reject")
async def reject_nomination(
    nomination_id: int,
    body: NominationRejectRequest,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    ok = await service.review_nomination(
        nomination_id, approve=False, reason=body.reason
    )
    if not ok:
        raise HTTPException(status_code=404, detail="NOMINATION_NOT_FOUND")
    return {"ok": True}


@router.get("/activity-logs", response_model=ActivityLogResponse)
async def list_activity_logs(
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    since: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> ActivityLogResponse:
    _check_admin_secret(settings, x_admin_secret)
    data = await service.list_activity_logs(user_id, action, since, page, page_size)
    items = [
        {
            "id": r.id, "event_type": r.event_type,
            "user_id": r.user_id, "requester_ip": r.requester_ip,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in data["items"]
    ]
    return ActivityLogResponse(items=items, total=data["total"])


@router.get("/export/votes")
async def export_votes(
    vote_year: int,
    category: str,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    _check_admin_secret(settings, x_admin_secret)
    filename = f"votes_{vote_year}_{category}.csv"
    return StreamingResponse(
        service.export_votes_csv(vote_year, category),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Sync endpoints ────────────────────────────────────────────────────────────


async def get_sync_service(
    session: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
    session_maker: async_sessionmaker = Depends(get_session_maker),
) -> SyncService:
    return SyncService(session, session_maker, redis, settings)


async def _run_all_collections_bg(
    run_id: str,
    request: SyncStartRequest,
    settings,
    redis,
    session_maker: async_sessionmaker,
) -> None:
    import pymongo
    from src.apps.admin.sync.runner import COLLECTION_CONFIG, run_collection

    uri = settings.mongodb_uri
    client = pymongo.MongoClient(uri)
    total_inserted = total_skipped = total_errors = 0
    collections_to_run = request.collections or [cfg[1] for cfg in COLLECTION_CONFIG]
    status = "completed"

    try:
        for db_attr, coll_name, pg_table, mapper, _ in COLLECTION_CONFIG:
            if coll_name not in collections_to_run:
                continue
            db_name = getattr(settings, db_attr)
            ins, skp, err = await run_collection(
                mongo_db=client[db_name],
                collection_name=coll_name,
                pg_table=pg_table,
                mapper=mapper,
                run_id=run_id,
                batch_size=request.batch_size,
                redis=redis,
                session_maker=session_maker,
                error_path=f"migrate_errors_{run_id[:8]}.jsonl",
            )
            total_inserted += ins
            total_skipped += skp
            total_errors += err
    except Exception as exc:
        _logger.error("Sync run %s failed: %s", run_id, exc)
        status = "failed"
    finally:
        client.close()
        async with session_maker() as session:
            svc = SyncService(session, session_maker, redis, settings)
            await svc.complete_run(
                run_id, total_inserted, total_skipped, total_errors, status
            )


@router.post("/sync/start", response_model=SyncStartResponse, status_code=202)
async def start_sync(
    body: SyncStartRequest,
    background_tasks: BackgroundTasks,
    x_admin_secret: Optional[str] = Header(None),
    service: SyncService = Depends(get_sync_service),
    settings: Settings = Depends(get_settings),
    redis: aioredis.Redis = Depends(get_redis),
    session_maker: async_sessionmaker = Depends(get_session_maker),
) -> SyncStartResponse:
    _check_admin_secret(settings, x_admin_secret)
    if not settings.mongodb_uri:
        raise HTTPException(status_code=503, detail="MONGODB_NOT_CONFIGURED")
    run_id = await service.start_sync(body)
    background_tasks.add_task(
        _run_all_collections_bg, run_id, body, settings, redis, session_maker
    )
    return SyncStartResponse(run_id=run_id, message="Sync started")


@router.get("/sync/status", response_model=SyncStatusResponse)
async def get_sync_status(
    x_admin_secret: Optional[str] = Header(None),
    service: SyncService = Depends(get_sync_service),
    settings: Settings = Depends(get_settings),
) -> SyncStatusResponse:
    _check_admin_secret(settings, x_admin_secret)
    data = await service.get_status()
    return SyncStatusResponse(**data)


@router.get("/sync/history", response_model=SyncHistoryResponse)
async def get_sync_history(
    page: int = 1,
    page_size: int = 20,
    x_admin_secret: Optional[str] = Header(None),
    service: SyncService = Depends(get_sync_service),
    settings: Settings = Depends(get_settings),
) -> SyncHistoryResponse:
    _check_admin_secret(settings, x_admin_secret)
    data = await service.get_history(page, page_size)
    items = [
        {
            "id": r.id, "run_id": r.run_id,
            "started_at": r.started_at.isoformat(),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "status": r.status,
            "collections": r.collections or [],
            "total_docs": r.total_docs,
            "inserted": r.inserted,
            "skipped": r.skipped,
            "errors": r.errors,
            "initiated_by": r.initiated_by,
        }
        for r in data["items"]
    ]
    return SyncHistoryResponse(items=items, total=data["total"])


@router.post("/sync/cancel")
async def cancel_sync(
    x_admin_secret: Optional[str] = Header(None),
    service: SyncService = Depends(get_sync_service),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    await service.cancel()
    return {"ok": True}


@router.post("/sync/retry/{run_id}", response_model=SyncStartResponse, status_code=202)
async def retry_sync(
    run_id: str,
    background_tasks: BackgroundTasks,
    x_admin_secret: Optional[str] = Header(None),
    service: SyncService = Depends(get_sync_service),
    settings: Settings = Depends(get_settings),
    redis: aioredis.Redis = Depends(get_redis),
    session_maker: async_sessionmaker = Depends(get_session_maker),
) -> SyncStartResponse:
    _check_admin_secret(settings, x_admin_secret)
    if not settings.mongodb_uri:
        raise HTTPException(status_code=503, detail="MONGODB_NOT_CONFIGURED")
    await set_current_run(redis, run_id)
    body = SyncStartRequest()
    background_tasks.add_task(
        _run_all_collections_bg, run_id, body, settings, redis, session_maker
    )
    return SyncStartResponse(run_id=run_id, message="Retry started from checkpoint")
