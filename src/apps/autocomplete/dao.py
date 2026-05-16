"""Autocomplete data access objects."""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db_model.candidate import CandidateCharacter, CandidateMusic


class AutocompleteDAO:
    def __init__(self, session: AsyncSession, vote_year: int):
        self.session = session
        self.vote_year = vote_year

    async def search_characters(self, query: str, limit: int = 10) -> list[dict]:
        stmt = (
            select(CandidateCharacter)
            .where(
                CandidateCharacter.vote_year == self.vote_year,
                or_(
                    CandidateCharacter.name.ilike(f"%{query}%"),
                    CandidateCharacter.name_jp.ilike(f"%{query}%"),
                ),
            )
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [
            {"name": r.name, "origin": r.origin, "name_jp": r.name_jp, "type": r.type}
            for r in rows
        ]

    async def search_music(self, query: str, limit: int = 10) -> list[dict]:
        stmt = (
            select(CandidateMusic)
            .where(
                CandidateMusic.vote_year == self.vote_year,
                or_(
                    CandidateMusic.name.ilike(f"%{query}%"),
                    CandidateMusic.name_jp.ilike(f"%{query}%"),
                ),
            )
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [
            {
                "name": r.name,
                "origin": r.album or None,
                "name_jp": r.name_jp,
                "type": r.type,
            }
            for r in rows
        ]

    async def search_cps(self, query: str, limit: int = 10) -> list[dict]:
        return []
