"""Autocomplete data access objects."""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db_model.candidate import CandidateCharacter, CandidateMusic
from src.db_model.voteable import VoteableCharacter, VoteableMusic
from src.db_model.work import Work


class AutocompleteDAO:
    def __init__(self, session: AsyncSession, vote_year: int):
        self.session = session
        self.vote_year = vote_year

    async def search_characters(self, query: str, limit: int = 10) -> list[dict]:
        stmt = (
            select(
                VoteableCharacter.name,
                Work.name,
                VoteableCharacter.name_jp,
                VoteableCharacter.type,
            )
            .join(
                CandidateCharacter,
                CandidateCharacter.voteable_id == VoteableCharacter.id,
            )
            .outerjoin(Work, VoteableCharacter.work_id == Work.id)
            .where(
                CandidateCharacter.vote_year == self.vote_year,
                or_(
                    VoteableCharacter.name.ilike(f"%{query}%"),
                    VoteableCharacter.name_jp.ilike(f"%{query}%"),
                ),
            )
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            {"name": r[0], "origin": r[1] or None, "name_jp": r[2], "type": r[3]}
            for r in rows
        ]

    async def search_music(self, query: str, limit: int = 10) -> list[dict]:
        stmt = (
            select(
                VoteableMusic.name,
                Work.name,
                VoteableMusic.name_jp,
                VoteableMusic.type,
            )
            .join(
                CandidateMusic,
                CandidateMusic.voteable_id == VoteableMusic.id,
            )
            .outerjoin(Work, VoteableMusic.work_id == Work.id)
            .where(
                CandidateMusic.vote_year == self.vote_year,
                or_(
                    VoteableMusic.name.ilike(f"%{query}%"),
                    VoteableMusic.name_jp.ilike(f"%{query}%"),
                ),
            )
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            {
                "name": r[0],
                "origin": r[1] or None,
                "name_jp": r[2],
                "type": r[3],
            }
            for r in rows
        ]

    async def search_cps(self, query: str, limit: int = 10) -> list[dict]:
        return []
