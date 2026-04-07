from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class SubmitMetadata(BaseModel):
    vote_id: str = "<unknown>"
    attempt: int | None = None
    created_at: datetime = Field(default_factory=utcnow)
    user_ip: str = "<unknown>"
    additional_fingreprint: str | None = None


class CharacterSubmit(BaseModel):
    id: str
    reason: str | None = None
    first: bool | None = None


class MusicSubmit(BaseModel):
    id: str
    reason: str | None = None
    first: bool | None = None


class CPSubmit(BaseModel):
    id_a: str
    id_b: str
    id_c: str | None = None
    active: str | None = None
    first: bool | None = None
    reason: str | None = None


class DojinSubmit(BaseModel):
    dojin_type: str
    url: str
    title: str
    author: str
    reason: str
    image_url: str | None = None


class CharacterSubmitRest(BaseModel):
    characters: list[CharacterSubmit]
    meta: SubmitMetadata


class MusicSubmitRest(BaseModel):
    music: list[MusicSubmit]
    meta: SubmitMetadata


class CPSubmitRest(BaseModel):
    cps: list[CPSubmit]
    meta: SubmitMetadata


class PaperSubmitRest(BaseModel):
    papers_json: str
    meta: SubmitMetadata


class DojinSubmitRest(BaseModel):
    dojins: list[DojinSubmit]
    meta: SubmitMetadata


class QuerySubmitRequest(BaseModel):
    vote_id: str


class VotingStatus(BaseModel):
    characters: bool
    musics: bool
    cps: bool
    papers: bool
    dojin: bool


class VotingStatistics(BaseModel):
    num_user: int
    num_finished_paper: int
    num_finished_voting: int
    num_character: int
    num_cp: int
    num_music: int
    num_dojin: int


class EmptyJSON(BaseModel):
    ok: bool = True


def scrub_metadata(meta: SubmitMetadata) -> SubmitMetadata:
    data: dict[str, Any] = meta.model_dump()
    data["additional_fingreprint"] = None
    data["user_ip"] = ""
    data["vote_id"] = ""
    return SubmitMetadata(**data)

