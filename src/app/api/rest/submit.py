"""Submit compatibility REST routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...common.database.session import get_db_session
from ...models.dto.submit import (
    CPSubmitRequest,
    CharacterSubmitRequest,
    DojinSubmitRequest,
    EmptyResult,
    MusicSubmitRequest,
    PaperSubmitRequest,
    QuerySubmitRequest,
    VotingStatistics,
    VotingStatus,
)
from ...modules.submit.guards import guarded_submit
from ...modules.submit.repository import SubmitRepository
from ...modules.submit.service import SubmitService

router = APIRouter(prefix="/v1", tags=["submit-handler"])


async def get_submit_service(session: AsyncSession = Depends(get_db_session)) -> SubmitService:
    return SubmitService(SubmitRepository(session))


@router.post("/character/", response_model=EmptyResult)
async def submit_character_v1(
    body: CharacterSubmitRequest,
    service: SubmitService = Depends(get_submit_service),
) -> EmptyResult:
    await guarded_submit(body.meta.vote_id, lambda: service.submit_character(body))
    return EmptyResult()


@router.post("/music/", response_model=EmptyResult)
async def submit_music_v1(
    body: MusicSubmitRequest,
    service: SubmitService = Depends(get_submit_service),
) -> EmptyResult:
    await guarded_submit(body.meta.vote_id, lambda: service.submit_music(body))
    return EmptyResult()


@router.post("/cp/", response_model=EmptyResult)
async def submit_cp_v1(
    body: CPSubmitRequest,
    service: SubmitService = Depends(get_submit_service),
) -> EmptyResult:
    await guarded_submit(body.meta.vote_id, lambda: service.submit_cp(body))
    return EmptyResult()


@router.post("/paper/", response_model=EmptyResult)
async def submit_paper_v1(
    body: PaperSubmitRequest,
    service: SubmitService = Depends(get_submit_service),
) -> EmptyResult:
    await guarded_submit(body.meta.vote_id, lambda: service.submit_paper(body))
    return EmptyResult()


@router.post("/dojin/", response_model=EmptyResult)
async def submit_dojin_v1(
    body: DojinSubmitRequest,
    service: SubmitService = Depends(get_submit_service),
) -> EmptyResult:
    await guarded_submit(body.meta.vote_id, lambda: service.submit_dojin(body))
    return EmptyResult()


@router.post("/get-character/", response_model=CharacterSubmitRequest)
async def get_submit_character_v1(
    body: QuerySubmitRequest,
    service: SubmitService = Depends(get_submit_service),
) -> CharacterSubmitRequest:
    return await service.get_character_submit(body.vote_id)


@router.post("/get-music/", response_model=MusicSubmitRequest)
async def get_submit_music_v1(
    body: QuerySubmitRequest,
    service: SubmitService = Depends(get_submit_service),
) -> MusicSubmitRequest:
    return await service.get_music_submit(body.vote_id)


@router.post("/get-cp/", response_model=CPSubmitRequest)
async def get_submit_cp_v1(
    body: QuerySubmitRequest,
    service: SubmitService = Depends(get_submit_service),
) -> CPSubmitRequest:
    return await service.get_cp_submit(body.vote_id)


@router.post("/get-paper/", response_model=PaperSubmitRequest)
async def get_submit_paper_v1(
    body: QuerySubmitRequest,
    service: SubmitService = Depends(get_submit_service),
) -> PaperSubmitRequest:
    return await service.get_paper_submit(body.vote_id)


@router.post("/get-dojin/", response_model=DojinSubmitRequest)
async def get_submit_dojin_v1(
    body: QuerySubmitRequest,
    service: SubmitService = Depends(get_submit_service),
) -> DojinSubmitRequest:
    return await service.get_dojin_submit(body.vote_id)


@router.post("/voting-status/", response_model=VotingStatus)
async def get_voting_status_v1(
    body: QuerySubmitRequest,
    service: SubmitService = Depends(get_submit_service),
) -> VotingStatus:
    return await service.get_voting_status(body.vote_id)


@router.post("/voting-statistics/", response_model=VotingStatistics)
async def get_voting_statistics_v1(
    service: SubmitService = Depends(get_submit_service),
) -> VotingStatistics:
    return await service.get_voting_statistics()
