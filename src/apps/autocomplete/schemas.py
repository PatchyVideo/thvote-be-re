"""Autocomplete schemas for request/response validation."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class AutocompleteRequest(BaseModel):
    """Request schema for autocomplete."""

    query: str
    limit: Optional[int] = 10


class AutocompleteSuggestion(BaseModel):
    """Autocomplete suggestion item."""

    name: str
    type: str
    origin: Optional[str] = None


class AutocompleteResponse(BaseModel):
    """Response schema for autocomplete."""

    suggestions: list[AutocompleteSuggestion]


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
