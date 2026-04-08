"""Vote data schemas for request/response validation."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CharacterVoteRequest(BaseModel):
    """Request schema for character voting."""

    character_list: list[str] = Field(..., min_length=1)


class MusicVoteRequest(BaseModel):
    """Request schema for music voting."""

    music_list: list[str] = Field(..., min_length=1)


class CpVoteRequest(BaseModel):
    """Request schema for CP voting."""

    cp_list: list[str] = Field(..., min_length=1)


class QuestionnaireVoteRequest(BaseModel):
    """Request schema for questionnaire voting."""

    questionnaire_list: list[dict[str, Any]] = Field(..., min_length=1)


class CharacterVoteResponse(BaseModel):
    """Response schema for character vote data."""

    id: str
    submit_datetime: datetime
    character_list: list[str]

    class Config:
        from_attributes = True


class MusicVoteResponse(BaseModel):
    """Response schema for music vote data."""

    id: str
    submit_datetime: datetime
    music_list: list[str]

    class Config:
        from_attributes = True


class CpVoteResponse(BaseModel):
    """Response schema for CP vote data."""

    id: str
    submit_datetime: datetime
    cp_list: list[str]

    class Config:
        from_attributes = True


class QuestionnaireVoteResponse(BaseModel):
    """Response schema for questionnaire vote data."""

    id: str
    submit_datetime: datetime
    questionnaire_list: list[dict[str, Any]]

    class Config:
        from_attributes = True


class VoteDataSummaryResponse(BaseModel):
    """Response schema for vote data summary."""

    user_id: str
    has_character: bool
    has_music: bool
    has_cp: bool
    has_questionnaire: bool
