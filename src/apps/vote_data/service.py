"""Vote data service layer."""

from datetime import UTC, datetime

from src.apps.vote_data.dao import VoteDataDAO
from src.apps.vote_data.models import Character, Cp, Music, Questionnaire
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


class VoteDataService:
    """Service for vote data business logic."""

    def __init__(self, vote_data_dao: VoteDataDAO):
        self.vote_data_dao = vote_data_dao

    async def submit_character_vote(
        self, user_id: str, request: CharacterVoteRequest
    ) -> CharacterVoteResponse:
        """Submit character votes for a user."""
        items = [item.model_dump() for item in request.character_list]
        existing = await self.vote_data_dao.get_character_by_id(user_id)
        if existing:
            await self.vote_data_dao.update_character(user_id, items)
        else:
            character = Character(
                id=user_id,
                submit_datetime=datetime.now(UTC),
                character_list=items,
            )
            await self.vote_data_dao.create_character(character)
        return CharacterVoteResponse(
            id=user_id,
            submit_datetime=datetime.now(UTC),
            character_list=items,
        )

    async def submit_music_vote(
        self, user_id: str, request: MusicVoteRequest
    ) -> MusicVoteResponse:
        """Submit music votes for a user."""
        items = [item.model_dump() for item in request.music_list]
        existing = await self.vote_data_dao.get_music_by_id(user_id)
        if existing:
            await self.vote_data_dao.update_music(user_id, items)
        else:
            music = Music(
                id=user_id,
                submit_datetime=datetime.now(UTC),
                music_list=items,
            )
            await self.vote_data_dao.create_music(music)
        return MusicVoteResponse(
            id=user_id,
            submit_datetime=datetime.now(UTC),
            music_list=items,
        )

    async def submit_cp_vote(
        self, user_id: str, request: CpVoteRequest
    ) -> CpVoteResponse:
        """Submit CP votes for a user."""
        items = [item.model_dump() for item in request.cp_list]
        existing = await self.vote_data_dao.get_cp_by_id(user_id)
        if existing:
            await self.vote_data_dao.update_cp(user_id, items)
        else:
            cp = Cp(
                id=user_id,
                submit_datetime=datetime.now(UTC),
                cp_list=items,
            )
            await self.vote_data_dao.create_cp(cp)
        return CpVoteResponse(
            id=user_id,
            submit_datetime=datetime.now(UTC),
            cp_list=items,
        )

    async def submit_questionnaire(
        self, user_id: str, request: QuestionnaireVoteRequest
    ) -> QuestionnaireVoteResponse:
        """Submit questionnaire answers for a user."""
        existing = await self.vote_data_dao.get_questionnaire_by_id(user_id)
        if existing:
            await self.vote_data_dao.update_questionnaire(
                user_id, request.questionnaire_list
            )
        else:
            questionnaire = Questionnaire(
                id=user_id,
                submit_datetime=datetime.now(UTC),
                questionnaire_list=request.questionnaire_list,
            )
            await self.vote_data_dao.create_questionnaire(questionnaire)
        return QuestionnaireVoteResponse(
            id=user_id,
            submit_datetime=datetime.now(UTC),
            questionnaire_list=request.questionnaire_list,
        )

    async def get_user_vote_summary(self, user_id: str) -> VoteDataSummaryResponse:
        """Get a summary of user's vote data."""
        has_character = (
            await self.vote_data_dao.get_character_by_id(user_id) is not None
        )
        has_music = await self.vote_data_dao.get_music_by_id(user_id) is not None
        has_cp = await self.vote_data_dao.get_cp_by_id(user_id) is not None
        has_questionnaire = (
            await self.vote_data_dao.get_questionnaire_by_id(user_id) is not None
        )

        return VoteDataSummaryResponse(
            user_id=user_id,
            has_character=has_character,
            has_music=has_music,
            has_cp=has_cp,
            has_questionnaire=has_questionnaire,
        )
