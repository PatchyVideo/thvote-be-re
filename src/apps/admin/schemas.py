"""Admin endpoint schemas."""

from typing import Literal, Optional

from pydantic import BaseModel


class CandidateItem(BaseModel):
    name: str
    name_jp: str = ""
    origin: str = ""
    type: str = ""
    first_appearance: Optional[str] = None
    album: Optional[str] = None


class ImportCandidatesRequest(BaseModel):
    vote_year: int
    category: Literal["character", "music"]
    items: list[CandidateItem]


class ImportCandidatesResponse(BaseModel):
    ok: bool = True
    imported: int


class ComputeResultsResponse(BaseModel):
    ok: bool
    vote_year: int
    duration_seconds: float
    counts: dict


class FinalizeRankingResponse(BaseModel):
    ok: bool = True
    vote_year: int
    saved: int
