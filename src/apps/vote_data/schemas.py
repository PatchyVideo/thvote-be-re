"""Vote data schemas for request/response validation."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CharacterVoteItem(BaseModel):
    id: str
    first: bool = False
    reason: str | None = None


class MusicVoteItem(BaseModel):
    id: str
    first: bool = False
    reason: str | None = None


class CpVoteItem(BaseModel):
    id_a: str
    id_b: str
    id_c: str | None = None
    active: str | None = None
    first: bool = False
    reason: str | None = None


class CharacterVoteRequest(BaseModel):
    character_list: list[CharacterVoteItem] = Field(..., min_length=1)


class MusicVoteRequest(BaseModel):
    music_list: list[MusicVoteItem] = Field(..., min_length=1)


class CpVoteRequest(BaseModel):
    cp_list: list[CpVoteItem] = Field(..., min_length=1)


class QuestionnaireVoteRequest(BaseModel):
    questionnaire_list: list[dict[str, Any]] = Field(..., min_length=1)


class CharacterVoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    submit_datetime: datetime
    character_list: list[dict[str, Any]]


class MusicVoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    submit_datetime: datetime
    music_list: list[dict[str, Any]]


class CpVoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    submit_datetime: datetime
    cp_list: list[dict[str, Any]]


class QuestionnaireVoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    submit_datetime: datetime
    questionnaire_list: list[dict[str, Any]]


class VoteDataSummaryResponse(BaseModel):
    user_id: str
    has_character: bool
    has_music: bool
    has_cp: bool
    has_questionnaire: bool
