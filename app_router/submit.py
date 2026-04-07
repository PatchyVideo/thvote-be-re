from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from dao.submit_models import (
    CPSubmitRest,
    CharacterSubmitRest,
    DojinSubmitRest,
    EmptyJSON,
    MusicSubmitRest,
    PaperSubmitRest,
    QuerySubmitRequest,
    VotingStatistics,
    VotingStatus,
)
from database import get_db_session
from services.rate_limit import get_redis_client, rate_limit
from services.submit_service import SubmitServiceV1
from services.submit_validator import SubmitValidatorV1

router = APIRouter(prefix="/v1", tags=["submit-handler"])

validator = SubmitValidatorV1()
service = SubmitServiceV1()


async def _acquire_vote_lock(vote_id: str) -> tuple[str, str]:
    redis_client = await get_redis_client()
    lock_key = f"lock-submit-{vote_id}"
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
async def submit_character_v1(body: CharacterSubmitRest, db: AsyncSession = Depends(get_db_session)) -> EmptyJSON:
    redis_client = await get_redis_client()
    await rate_limit(body.meta.vote_id, redis_client)
    lock_key, lock_value = await _acquire_vote_lock(body.meta.vote_id)
    try:
        sanitized = await validator.validate_character(body)
        await service.submit_character(db, sanitized)
    finally:
        await _release_vote_lock(lock_key, lock_value)
    return EmptyJSON()


@router.post("/music/", response_model=EmptyJSON)
async def submit_music_v1(body: MusicSubmitRest, db: AsyncSession = Depends(get_db_session)) -> EmptyJSON:
    redis_client = await get_redis_client()
    await rate_limit(body.meta.vote_id, redis_client)
    lock_key, lock_value = await _acquire_vote_lock(body.meta.vote_id)
    try:
        sanitized = await validator.validate_music(body)
        await service.submit_music(db, sanitized)
    finally:
        await _release_vote_lock(lock_key, lock_value)
    return EmptyJSON()


@router.post("/cp/", response_model=EmptyJSON)
async def submit_cp_v1(body: CPSubmitRest, db: AsyncSession = Depends(get_db_session)) -> EmptyJSON:
    redis_client = await get_redis_client()
    await rate_limit(body.meta.vote_id, redis_client)
    lock_key, lock_value = await _acquire_vote_lock(body.meta.vote_id)
    try:
        sanitized = await validator.validate_cp(body)
        await service.submit_cp(db, sanitized)
    finally:
        await _release_vote_lock(lock_key, lock_value)
    return EmptyJSON()


@router.post("/paper/", response_model=EmptyJSON)
async def submit_paper_v1(body: PaperSubmitRest, db: AsyncSession = Depends(get_db_session)) -> EmptyJSON:
    redis_client = await get_redis_client()
    await rate_limit(body.meta.vote_id, redis_client)
    lock_key, lock_value = await _acquire_vote_lock(body.meta.vote_id)
    try:
        sanitized = await validator.validate_paper(body)
        await service.submit_paper(db, sanitized)
    finally:
        await _release_vote_lock(lock_key, lock_value)
    return EmptyJSON()


@router.post("/dojin/", response_model=EmptyJSON)
async def submit_dojin_v1(body: DojinSubmitRest, db: AsyncSession = Depends(get_db_session)) -> EmptyJSON:
    redis_client = await get_redis_client()
    await rate_limit(body.meta.vote_id, redis_client)
    lock_key, lock_value = await _acquire_vote_lock(body.meta.vote_id)
    try:
        sanitized = await validator.validate_dojin(body)
        await service.submit_dojin(db, sanitized)
    finally:
        await _release_vote_lock(lock_key, lock_value)
    return EmptyJSON()


@router.post("/get-character/", response_model=CharacterSubmitRest)
async def get_submit_character_v1(body: QuerySubmitRequest, db: AsyncSession = Depends(get_db_session)) -> CharacterSubmitRest:
    return await service.get_submit_character(db, body.vote_id)


@router.post("/get-music/", response_model=MusicSubmitRest)
async def get_submit_music_v1(body: QuerySubmitRequest, db: AsyncSession = Depends(get_db_session)) -> MusicSubmitRest:
    return await service.get_submit_music(db, body.vote_id)


@router.post("/get-cp/", response_model=CPSubmitRest)
async def get_submit_cp_v1(body: QuerySubmitRequest, db: AsyncSession = Depends(get_db_session)) -> CPSubmitRest:
    return await service.get_submit_cp(db, body.vote_id)


@router.post("/get-paper/", response_model=PaperSubmitRest)
async def get_submit_paper_v1(body: QuerySubmitRequest, db: AsyncSession = Depends(get_db_session)) -> PaperSubmitRest:
    return await service.get_submit_paper(db, body.vote_id)


@router.post("/get-dojin/", response_model=DojinSubmitRest)
async def get_submit_dojin_v1(body: QuerySubmitRequest, db: AsyncSession = Depends(get_db_session)) -> DojinSubmitRest:
    return await service.get_submit_dojin(db, body.vote_id)


@router.post("/voting-status/", response_model=VotingStatus)
async def get_voting_status_v1(body: QuerySubmitRequest, db: AsyncSession = Depends(get_db_session)) -> VotingStatus:
    return await service.get_voting_status(db, body.vote_id)


@router.post("/voting-statistics/", response_model=VotingStatistics)
async def get_voting_statistics_v1(db: AsyncSession = Depends(get_db_session)) -> VotingStatistics:
    return await service.get_voting_statistics(db)

