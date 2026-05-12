"""ComputeDAO — reads raw vote + candidate data from PostgreSQL for computation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.result.compute import CandidateMeta
from src.db_model.candidate import CandidateCharacter, CandidateMusic, FinalRanking
from src.db_model.character import Character
from src.db_model.cp import Cp
from src.db_model.music import Music
from src.db_model.questionnaire import Questionnaire


def _normalize_items(raw_list: list) -> list[dict]:
    """Backward-compat: old list[str] → list[dict]."""
    result = []
    for item in (raw_list or []):
        if isinstance(item, str):
            result.append({"id": item, "first": False, "reason": None})
        elif isinstance(item, dict):
            result.append(item)
    return result


class ComputeDAO:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def load_char_votes(self) -> list[tuple[str, datetime, list[dict]]]:
        rows = (await self.session.execute(select(Character))).scalars().all()
        return [(r.id, r.submit_datetime, _normalize_items(r.character_list)) for r in rows]

    async def load_music_votes(self) -> list[tuple[str, datetime, list[dict]]]:
        rows = (await self.session.execute(select(Music))).scalars().all()
        return [(r.id, r.submit_datetime, _normalize_items(r.music_list)) for r in rows]

    async def load_cp_votes(self) -> list[tuple[str, datetime, list[dict]]]:
        rows = (await self.session.execute(select(Cp))).scalars().all()
        return [(r.id, r.submit_datetime, _normalize_items(r.cp_list)) for r in rows]

    async def load_questionnaire_votes(self) -> list[tuple[str, list[dict]]]:
        rows = (await self.session.execute(select(Questionnaire))).scalars().all()
        return [(r.id, r.questionnaire_list or []) for r in rows]

    async def load_char_candidates(self, vote_year: int) -> dict[str, CandidateMeta]:
        rows = (await self.session.execute(
            select(CandidateCharacter).where(CandidateCharacter.vote_year == vote_year)
        )).scalars().all()
        return {r.name: CandidateMeta(
            name=r.name, name_jp=r.name_jp, origin=r.origin,
            type=r.type, first_appearance=r.first_appearance,
        ) for r in rows}

    async def load_music_candidates(self, vote_year: int) -> dict[str, CandidateMeta]:
        rows = (await self.session.execute(
            select(CandidateMusic).where(CandidateMusic.vote_year == vote_year)
        )).scalars().all()
        return {r.name: CandidateMeta(
            name=r.name, name_jp=r.name_jp, origin="",
            type=r.type, first_appearance=r.first_appearance, album=r.album,
        ) for r in rows}

    async def load_historical(self, vote_year: int, category: str) -> dict[str, dict]:
        """Load rank_last_1 and rank_last_2 from final_ranking for historical comparison."""
        hist: dict[str, dict] = {}
        for delta, suffix in [(1, "1"), (2, "2")]:
            rows = (await self.session.execute(
                select(FinalRanking).where(
                    FinalRanking.vote_year == vote_year - delta,
                    FinalRanking.category == category,
                )
            )).scalars().all()
            for r in rows:
                entry = hist.setdefault(r.name, {})
                entry[f"rank_{suffix}"] = r.rank
                entry[f"votes_{suffix}"] = r.vote_count
                entry[f"first_{suffix}"] = r.first_vote_count
        return hist

    async def upsert_candidates(self, vote_year: int, category: str, items: list[dict]) -> int:
        """Bulk upsert candidate rows. Returns number of rows upserted."""
        Model = CandidateCharacter if category == "character" else CandidateMusic
        count = 0
        for item in items:
            existing = (await self.session.execute(
                select(Model).where(Model.vote_year == vote_year, Model.name == item["name"])
            )).scalar_one_or_none()
            if existing:
                for k, v in item.items():
                    if k != "name" and hasattr(existing, k):
                        setattr(existing, k, v)
            else:
                row = Model(vote_year=vote_year, **item)
                self.session.add(row)
            count += 1
        await self.session.commit()
        return count

    async def save_final_ranking(self, vote_year: int, category: str, entries: list[dict]) -> int:
        """Archive final ranking for historical comparison."""
        count = 0
        for entry in entries:
            rank_list = entry.get("rank", [{}])
            rank = entry.get("display_rank") or (rank_list[0].get("rank", 0) if rank_list else 0)
            vc = rank_list[0].get("vote_count", 0) if rank_list else 0
            fc = rank_list[0].get("favorite_vote_count", 0) if rank_list else 0
            existing = (await self.session.execute(
                select(FinalRanking).where(
                    FinalRanking.vote_year == vote_year,
                    FinalRanking.category == category,
                    FinalRanking.rank == rank,
                )
            )).scalar_one_or_none()
            if existing:
                existing.name = entry["name"]
                existing.vote_count = vc
                existing.first_vote_count = fc
            else:
                self.session.add(FinalRanking(
                    vote_year=vote_year, category=category, rank=rank,
                    name=entry["name"], vote_count=vc, first_vote_count=fc,
                ))
            count += 1
        await self.session.commit()
        return count
