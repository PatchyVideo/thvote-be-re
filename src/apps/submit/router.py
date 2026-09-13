"""Submit API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.submit.dao import SubmitDAO
from src.apps.submit.schemas import (
    CharacterSubmitRest,
    CPSubmitRest,
    DojinSubmitRest,
    EmptyJSON,
    MusicSubmitRest,
    PaperSubmitRest,
    QuerySubmitRequest,
    SubmitMetadata,
    VotingStatistics,
    VotingStatus,
)
from src.apps.submit.service import SubmitService
from src.apps.user.deps import get_client_ip
from src.common.database import get_db_session
from src.common.middleware.rate_limit import get_redis_client, rate_limit
from src.common.security.jwt import (
    JWTValidationError,
    VoteTokenPayload,
    decode_vote_token,
)

router = APIRouter(prefix="", tags=["submit-handler"])


async def get_submit_service(
    session: AsyncSession = Depends(get_db_session),
) -> SubmitService:
    """Dependency to get SubmitService instance."""
    dao = SubmitDAO(session)
    return SubmitService(dao)


def _verify_vote_token(token: str | None) -> VoteTokenPayload:
    """Decode and validate a vote_token from request metadata."""
    if not token:
        raise HTTPException(status_code=401, detail="VOTE_TOKEN_REQUIRED")
    try:
        return decode_vote_token(token)
    except JWTValidationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _bind_submit_identity(meta: SubmitMetadata, client_ip: str) -> VoteTokenPayload:
    """Verify the vote_token and pin server-controlled metadata fields.

    ``vote_id`` is the token subject (user_id), never the client-supplied
    value — otherwise any token holder could write as another voter.  Mirrors
    the old Rust gateway's ``generate_submit_metadata`` and the GraphQL bridge.
    ``user_ip`` likewise trusts the peer over anything the client sent.
    """
    payload = _verify_vote_token(meta.vote_token)
    meta.vote_id = payload.user_id
    meta.user_ip = client_ip
    return payload


def _readback_user_id(body: QuerySubmitRequest) -> str:
    """Read-back is scoped by the vote_token; a raw ``vote_id`` is ignored."""
    return _verify_vote_token(body.vote_token).user_id


async def _acquire_vote_lock(user_id: str) -> tuple[str, str]:
    redis_client = await get_redis_client()
    lock_key = f"lock-submit-{user_id}"
    lock_value = str(uuid.uuid4())
    acquired = await redis_client.set(lock_key, lock_value, nx=True, px=10_000)
    if not acquired:
        raise HTTPException(status_code=429, detail="SUBMIT_LOCKED")
    return lock_key, lock_value


async def _release_vote_lock(lock_key: str, lock_value: str) -> None:
    redis_client = await get_redis_client()
    current = await redis_client.get(lock_key)
    if current == lock_value:
        await redis_client.delete(lock_key)


@router.post("/character/", response_model=EmptyJSON)
async def submit_character_v1(
    body: CharacterSubmitRest,
    service: SubmitService = Depends(get_submit_service),
    client_ip: str = Depends(get_client_ip),
) -> EmptyJSON:
    payload = _bind_submit_identity(body.meta, client_ip)
    redis_client = await get_redis_client()
    await rate_limit(payload.user_id, redis_client)
    lock_key, lock_value = await _acquire_vote_lock(payload.user_id)
    try:
        await service.submit_character(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await _release_vote_lock(lock_key, lock_value)
    return EmptyJSON()


@router.post("/music/", response_model=EmptyJSON)
async def submit_music_v1(
    body: MusicSubmitRest,
    service: SubmitService = Depends(get_submit_service),
    client_ip: str = Depends(get_client_ip),
) -> EmptyJSON:
    payload = _bind_submit_identity(body.meta, client_ip)
    redis_client = await get_redis_client()
    await rate_limit(payload.user_id, redis_client)
    lock_key, lock_value = await _acquire_vote_lock(payload.user_id)
    try:
        await service.submit_music(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await _release_vote_lock(lock_key, lock_value)
    return EmptyJSON()


@router.post("/cp/", response_model=EmptyJSON)
async def submit_cp_v1(
    body: CPSubmitRest,
    service: SubmitService = Depends(get_submit_service),
    client_ip: str = Depends(get_client_ip),
) -> EmptyJSON:
    payload = _bind_submit_identity(body.meta, client_ip)
    redis_client = await get_redis_client()
    await rate_limit(payload.user_id, redis_client)
    lock_key, lock_value = await _acquire_vote_lock(payload.user_id)
    try:
        await service.submit_cp(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await _release_vote_lock(lock_key, lock_value)
    return EmptyJSON()


@router.post("/paper/", response_model=EmptyJSON)
async def submit_paper_v1(
    body: PaperSubmitRest,
    service: SubmitService = Depends(get_submit_service),
    client_ip: str = Depends(get_client_ip),
) -> EmptyJSON:
    payload = _bind_submit_identity(body.meta, client_ip)
    redis_client = await get_redis_client()
    await rate_limit(payload.user_id, redis_client)
    lock_key, lock_value = await _acquire_vote_lock(payload.user_id)
    try:
        await service.submit_paper(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await _release_vote_lock(lock_key, lock_value)
    return EmptyJSON()


@router.post("/dojin/", response_model=EmptyJSON)
async def submit_dojin_v1(
    body: DojinSubmitRest,
    service: SubmitService = Depends(get_submit_service),
    client_ip: str = Depends(get_client_ip),
) -> EmptyJSON:
    payload = _bind_submit_identity(body.meta, client_ip)
    redis_client = await get_redis_client()
    await rate_limit(payload.user_id, redis_client)
    lock_key, lock_value = await _acquire_vote_lock(payload.user_id)
    try:
        await service.submit_dojin(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await _release_vote_lock(lock_key, lock_value)
    return EmptyJSON()


@router.post("/get-character/", response_model=CharacterSubmitRest)
async def get_submit_character_v1(
    body: QuerySubmitRequest,
    service: SubmitService = Depends(get_submit_service),
) -> CharacterSubmitRest:
    return await service.get_character_submit(_readback_user_id(body))


@router.post("/get-music/", response_model=MusicSubmitRest)
async def get_submit_music_v1(
    body: QuerySubmitRequest,
    service: SubmitService = Depends(get_submit_service),
) -> MusicSubmitRest:
    return await service.get_music_submit(_readback_user_id(body))


@router.post("/get-cp/", response_model=CPSubmitRest)
async def get_submit_cp_v1(
    body: QuerySubmitRequest,
    service: SubmitService = Depends(get_submit_service),
) -> CPSubmitRest:
    return await service.get_cp_submit(_readback_user_id(body))


@router.post("/get-paper/", response_model=PaperSubmitRest)
async def get_submit_paper_v1(
    body: QuerySubmitRequest,
    service: SubmitService = Depends(get_submit_service),
) -> PaperSubmitRest:
    return await service.get_paper_submit(_readback_user_id(body))


@router.post("/get-dojin/", response_model=DojinSubmitRest)
async def get_submit_dojin_v1(
    body: QuerySubmitRequest,
    service: SubmitService = Depends(get_submit_service),
) -> DojinSubmitRest:
    return await service.get_dojin_submit(_readback_user_id(body))


@router.post("/voting-status/", response_model=VotingStatus)
async def get_voting_status_v1(
    body: QuerySubmitRequest,
    service: SubmitService = Depends(get_submit_service),
) -> VotingStatus:
    return await service.get_voting_status(_readback_user_id(body))


@router.post("/voting-statistics/", response_model=VotingStatistics)
async def get_voting_statistics_v1(
    service: SubmitService = Depends(get_submit_service),
) -> VotingStatistics:
    return await service.get_voting_statistics()


@router.get("/nominations/approved")
async def list_approved_nominations_v1(
    page: int = 1,
    page_size: int = 50,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Public: approved dojin nominations, deduped by udid with count."""
    rows = await SubmitDAO(session).list_approved_nominations(page, page_size)
    items = [
        {
            "udid": r.udid,
            "title": r.title,
            "url": r.url,
            "author": r.author,
            "nomination_count": r.cnt,
        }
        for r in rows
    ]
    return {"items": items, "page": page}
