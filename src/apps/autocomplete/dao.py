"""Autocomplete data access objects."""

from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db_model.candidate import CandidateCharacter, CandidateMusic
from src.db_model.voteable import VoteableCharacter, VoteableMusic
from src.db_model.work import Work


class AutocompleteDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def load_search_documents(
        self, category: Literal["character", "music"], vote_year: int
    ) -> list[tuple[int, tuple[str, ...]]]:
        candidate, voteable = {
            "character": (CandidateCharacter, VoteableCharacter),
            "music": (CandidateMusic, VoteableMusic),
        }[category]
        stmt = (
            select(candidate.id, voteable.name, voteable.aliases, Work.name)
            .select_from(candidate)
            .join(voteable, candidate.voteable_id == voteable.id)
            .outerjoin(Work, voteable.work_id == Work.id)
            .where(candidate.vote_year == vote_year)
            .order_by(candidate.id)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            (cid, tuple(dict.fromkeys(
                term for term in (name, *(aliases or []), work) if term
            )))
            for cid, name, aliases, work in rows
        ]
