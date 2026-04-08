"""Pydantic DTOs for vote submission flows."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    """Return the current UTC time."""
    return datetime.now(tz=timezone.utc)


class SubmitMetadata(BaseModel):
    """Request metadata stored alongside a raw submit snapshot."""

    vote_id: str = "<unknown>"
    attempt: int | None = None
    created_at: datetime = Field(default_factory=utcnow)
    user_ip: str = "<unknown>"
    additional_fingerprint: str | None = None


class CharacterVoteItem(BaseModel):
    id: str
    reason: str | None = None
    first: bool | None = None


class MusicVoteItem(BaseModel):
    id: str
    reason: str | None = None
    first: bool | None = None


class CPVoteItem(BaseModel):
    id_a: str
    id_b: str
    id_c: str | None = None
    active: str | None = None
    first: bool | None = None
    reason: str | None = None


class DojinVoteItem(BaseModel):
    dojin_type: str
    url: str
    title: str
    author: str
    reason: str
    image_url: str | None = None


class CharacterSubmitRequest(BaseModel):
    characters: list[CharacterVoteItem]
    meta: SubmitMetadata


class MusicSubmitRequest(BaseModel):
    music: list[MusicVoteItem]
    meta: SubmitMetadata


class CPSubmitRequest(BaseModel):
    cps: list[CPVoteItem]
    meta: SubmitMetadata


class PaperSubmitRequest(BaseModel):
    papers_json: str
    meta: SubmitMetadata


class DojinSubmitRequest(BaseModel):
    dojins: list[DojinVoteItem]
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


class EmptyResult(BaseModel):
    ok: bool = True


def scrub_metadata(meta: SubmitMetadata) -> SubmitMetadata:
    """Remove sensitive fields before returning submit snapshots."""
    data: dict[str, Any] = meta.model_dump()
    data["additional_fingerprint"] = None
    data["user_ip"] = ""
    data["vote_id"] = ""
    return SubmitMetadata(**data)
