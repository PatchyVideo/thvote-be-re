"""Autocomplete service layer."""

from src.apps.autocomplete.dao import AutocompleteDAO
from src.apps.autocomplete.schemas import (AutocompleteRequest,
                                           AutocompleteResponse,
                                           AutocompleteSuggestion)


class AutocompleteService:
    """Service for autocomplete operations."""

    def __init__(self, autocomplete_dao: AutocompleteDAO):
        self.autocomplete_dao = autocomplete_dao

    async def search(self, request: AutocompleteRequest) -> AutocompleteResponse:
        """Search for suggestions matching the query."""
        results: list[AutocompleteSuggestion] = []

        # Search in all categories
        characters = await self.autocomplete_dao.search_characters(
            request.query, request.limit
        )
        for char in characters:
            results.append(
                AutocompleteSuggestion(
                    name=char.get("name", ""),
                    type="character",
                    origin=char.get("origin"),
                )
            )

        music = await self.autocomplete_dao.search_music(request.query, request.limit)
        for m in music:
            results.append(
                AutocompleteSuggestion(
                    name=m.get("name", ""),
                    type="music",
                    origin=m.get("origin"),
                )
            )

        cps = await self.autocomplete_dao.search_cps(request.query, request.limit)
        for cp in cps:
            results.append(
                AutocompleteSuggestion(
                    name=cp.get("name", ""),
                    type="cp",
                    origin=cp.get("origin"),
                )
            )

        # Limit total results
        return AutocompleteResponse(suggestions=results[: request.limit])
