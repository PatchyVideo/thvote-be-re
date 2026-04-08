"""Vote data API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.vote_data.schemas import (
    CharacterVoteRequest,
    CharacterVoteResponse,
    CpVoteRequest,
    CpVoteResponse,
    MusicVoteRequest,
    MusicVoteResponse,
    QuestionnaireVoteRequest,
    QuestionnaireVoteResponse,
    VoteDataSummaryResponse,
)
from src.apps.vote_data.service import VoteDataService
from src.common.database import get_db_session

router = APIRouter(prefix="/vote-data", tags=["vote-data"])


async def get_vote_data_service(
    session: AsyncSession = Depends(get_db_session),
) -> VoteDataService:
    """Dependency to get VoteDataService instance."""
    from src.apps.vote_data.dao import VoteDataDAO

    dao = VoteDataDAO(session)
    return VoteDataService(dao)


@router.post("/character/{user_id}", response_model=CharacterVoteResponse)
async def submit_character_vote(
    user_id: str,
    request: CharacterVoteRequest,
    service: VoteDataService = Depends(get_vote_data_service),
) -> CharacterVoteResponse:
    """Submit character votes for a user."""
    return await service.submit_character_vote(user_id, request)


@router.post("/music/{user_id}", response_model=MusicVoteResponse)
async def submit_music_vote(
    user_id: str,
    request: MusicVoteRequest,
    service: VoteDataService = Depends(get_vote_data_service),
) -> MusicVoteResponse:
    """Submit music votes for a user."""
    return await service.submit_music_vote(user_id, request)


@router.post("/cp/{user_id}", response_model=CpVoteResponse)
async def submit_cp_vote(
    user_id: str,
    request: CpVoteRequest,
    service: VoteDataService = Depends(get_vote_data_service),
) -> CpVoteResponse:
    """Submit CP votes for a user."""
    return await service.submit_cp_vote(user_id, request)


@router.post("/questionnaire/{user_id}", response_model=QuestionnaireVoteResponse)
async def submit_questionnaire(
    user_id: str,
    request: QuestionnaireVoteRequest,
    service: VoteDataService = Depends(get_vote_data_service),
) -> QuestionnaireVoteResponse:
    """Submit questionnaire answers for a user."""
    return await service.submit_questionnaire(user_id, request)


@router.get("/summary/{user_id}", response_model=VoteDataSummaryResponse)
async def get_vote_summary(
    user_id: str,
    service: VoteDataService = Depends(get_vote_data_service),
) -> VoteDataSummaryResponse:
    """Get a summary of user's vote data."""
    return await service.get_user_vote_summary(user_id)
