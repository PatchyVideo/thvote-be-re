"""Public candidate search request and response contracts."""

from typing import Literal

from pydantic import BaseModel, Field


CandidateCategory = Literal["character", "music"]


class CandidateSearchRequest(BaseModel):
    category: CandidateCategory
    query: str = Field(max_length=64)
    vote_year: int | None = Field(default=None, gt=0)


class CandidateSearchResponse(BaseModel):
    category: CandidateCategory
    query: str
    vote_year: int
    candidate_ids: list[int]
