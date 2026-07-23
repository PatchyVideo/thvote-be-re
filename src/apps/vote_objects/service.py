"""Vote-objects service: grouped candidate listings (thin passthrough)."""

from __future__ import annotations

from src.apps.vote_objects.dao import VoteObjectsDAO


class VoteObjectsService:
    def __init__(self, dao: VoteObjectsDAO) -> None:
        self.dao = dao

    async def characters(self, vote_year: int) -> dict:
        return await self.dao.list_characters(vote_year)

    async def music(self, vote_year: int) -> dict:
        return await self.dao.list_music(vote_year)

    async def detail(self, category: str, candidate_id: int) -> dict | None:
        return await self.dao.get_one(category, candidate_id)
