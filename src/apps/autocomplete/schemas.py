"""Autocomplete schemas for request/response validation."""

from typing import Optional

from pydantic import BaseModel


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
