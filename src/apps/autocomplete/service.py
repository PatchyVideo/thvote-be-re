"""Autocomplete service layer."""

import math

from src.apps.autocomplete.dao import AutocompleteDAO
from src.apps.autocomplete.schemas import (
    AutocompleteRequest,
    AutocompleteResponse,
    AutocompleteSuggestion,
)


class AutocompleteService:
    def __init__(self, autocomplete_dao: AutocompleteDAO):
        self.autocomplete_dao = autocomplete_dao

    async def search(self, request: AutocompleteRequest) -> AutocompleteResponse:
        per_cat = math.ceil(request.limit / 2)
        results: list[AutocompleteSuggestion] = []

        for item in await self.autocomplete_dao.search_characters(request.query, per_cat):
            results.append(AutocompleteSuggestion(
                name=item.get("name", ""),
                type="character",
                origin=item.get("origin"),
            ))

        for item in await self.autocomplete_dao.search_music(request.query, per_cat):
            results.append(AutocompleteSuggestion(
                name=item.get("name", ""),
                type="music",
                origin=item.get("origin"),
            ))

        return AutocompleteResponse(suggestions=results[: request.limit])
