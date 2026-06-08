"""Vote-objects service: group candidates by classification."""
from __future__ import annotations

from src.apps.vote_objects.dao import VoteObjectsDAO


def _group_by(items: list[dict], key: str) -> list[dict]:
    """Group items into [{group, items}], preserving first-seen group order."""
    groups: dict[str, list] = {}
    order: list[str] = []
    for it in items:
        g = it.get(key) or "未分类"
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append(it)
    return [{"group": g, "items": groups[g]} for g in order]


class VoteObjectsService:
    def __init__(self, dao: VoteObjectsDAO) -> None:
        self.dao = dao

    async def characters(self, vote_year: int) -> dict:
        items = await self.dao.list_characters(vote_year)
        return {"vote_year": vote_year, "groups": _group_by(items, "origin")}

    async def music(self, vote_year: int) -> dict:
        items = await self.dao.list_music(vote_year)
        return {"vote_year": vote_year, "groups": _group_by(items, "album")}

    async def detail(self, category: str, candidate_id: int) -> dict | None:
        return await self.dao.get_one(category, candidate_id)
