"""Vote-objects DAO: grouped candidate listings for the voting page (B-040)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db_model.candidate import CandidateCharacter, CandidateMusic


class VoteObjectsDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_characters(self, vote_year: int) -> list[dict]:
        rows = (await self.session.execute(
            select(CandidateCharacter).where(
                CandidateCharacter.vote_year == vote_year,
                CandidateCharacter.merged_into.is_(None),
            ).order_by(CandidateCharacter.name)
        )).scalars().all()
        return [
            {
                "id": r.id, "name": r.name, "name_jp": r.name_jp,
                "origin": r.origin, "first_appearance": r.first_appearance,
            }
            for r in rows
        ]

    async def list_music(self, vote_year: int) -> list[dict]:
        rows = (await self.session.execute(
            select(CandidateMusic).where(
                CandidateMusic.vote_year == vote_year,
                CandidateMusic.merged_into.is_(None),
            ).order_by(CandidateMusic.name)
        )).scalars().all()
        return [
            {
                "id": r.id, "name": r.name, "name_jp": r.name_jp,
                "album": r.album, "first_appearance": r.first_appearance,
            }
            for r in rows
        ]

    async def get_one(self, category: str, candidate_id: int) -> dict | None:
        model = (
            CandidateCharacter if category == "character" else CandidateMusic
        )
        r = (await self.session.execute(
            select(model).where(model.id == candidate_id)
        )).scalar_one_or_none()
        if r is None:
            return None
        out = {
            "id": r.id, "vote_year": r.vote_year, "name": r.name,
            "name_jp": r.name_jp, "first_appearance": r.first_appearance,
            "merged_into": r.merged_into,
        }
        out["origin" if category == "character" else "album"] = getattr(
            r, "origin" if category == "character" else "album", None
        )
        return out
