"""ComputeDAO — reads raw vote + candidate data from PostgreSQL for computation."""

from __future__ import annotations

from datetime import datetime
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
    for item in raw_list or []:
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
        return [
            (r.id, r.submit_datetime, _normalize_items(r.character_list)) for r in rows
        ]

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
        rows = (
            (
                await self.session.execute(
                    select(CandidateCharacter).where(
                        CandidateCharacter.vote_year == vote_year
                    )
                )
            )
            .scalars()
            .all()
        )
        return {
            r.name: CandidateMeta(
                name=r.name,
                name_jp=r.name_jp,
                origin=r.origin,
                type=r.type,
                first_appearance=r.first_appearance,
            )
            for r in rows
        }

    async def load_music_candidates(self, vote_year: int) -> dict[str, CandidateMeta]:
        rows = (
            (
                await self.session.execute(
                    select(CandidateMusic).where(CandidateMusic.vote_year == vote_year)
                )
            )
            .scalars()
            .all()
        )
        return {
            r.name: CandidateMeta(
                name=r.name,
                name_jp=r.name_jp,
                origin="",
                type=r.type,
                first_appearance=r.first_appearance,
                album=r.album,
            )
            for r in rows
        }

    async def load_historical(
        self, vote_year: int, category: str
    ) -> dict[str, dict]:
        """Load rank_last_1 and rank_last_2 from final_ranking for historical."""
        hist: dict[str, dict] = {}
        for delta, suffix in [(1, "1"), (2, "2")]:
            rows = (
                (
                    await self.session.execute(
                        select(FinalRanking).where(
                            FinalRanking.vote_year == vote_year - delta,
                            FinalRanking.category == category,
                        )
                    )
                )
                .scalars()
                .all()
            )
            for r in rows:
                entry = hist.setdefault(r.name, {})
                entry[f"rank_{suffix}"] = r.rank
                entry[f"votes_{suffix}"] = r.vote_count
                entry[f"first_{suffix}"] = r.first_vote_count
        return hist

    async def upsert_candidates(
        self, vote_year: int, category: str, items: list[dict]
    ) -> int:
        """Bulk upsert candidate rows. Returns number of rows upserted."""
        Model = CandidateCharacter if category == "character" else CandidateMusic
        # Get valid column names for the model
        # (exclude 'id' and 'vote_year' which are handled separately)
        model_columns = {
            c.key for c in Model.__table__.columns if c.key not in ("id", "vote_year")
        }
        count = 0
        for item in items:
            # Only pass fields that exist in the model
            filtered = {k: v for k, v in item.items() if k in model_columns}
            existing = (
                await self.session.execute(
                    select(Model).where(
                        Model.vote_year == vote_year,
                        Model.name == filtered.get("name", item.get("name")),
                    )
                )
            ).scalar_one_or_none()
            if existing:
                for k, v in filtered.items():
                    if k != "name" and hasattr(existing, k):
                        setattr(existing, k, v)
            else:
                row = Model(vote_year=vote_year, **filtered)
                self.session.add(row)
            count += 1
        await self.session.commit()
        return count

    async def save_final_ranking(
        self, vote_year: int, category: str, entries: list[dict]
    ) -> int:
        """Archive final ranking for historical comparison."""
        count = 0
        for entry in entries:
            rank_list = entry.get("rank", [{}])
            rank = entry.get("display_rank") or (
                rank_list[0].get("rank", 0) if rank_list else 0
            )
            vc = rank_list[0].get("vote_count", 0) if rank_list else 0
            fc = rank_list[0].get("favorite_vote_count", 0) if rank_list else 0
            existing = (
                await self.session.execute(
                    select(FinalRanking).where(
                        FinalRanking.vote_year == vote_year,
                        FinalRanking.category == category,
                        FinalRanking.name == entry["name"],
                    )
                )
            ).scalar_one_or_none()
            if existing:
                existing.rank = rank  # update rank if character moved
                existing.vote_count = vc
                existing.first_vote_count = fc
            else:
                self.session.add(
                    FinalRanking(
                        vote_year=vote_year,
                        category=category,
                        rank=rank,
                        name=entry["name"],
                        vote_count=vc,
                        first_vote_count=fc,
                    )
                )
            count += 1
        await self.session.commit()
        return count

    async def list_candidates(
        self,
        category: str,
        vote_year: int,
        q: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list, int]:
        from sqlalchemy import func as sqlfunc
        from src.db_model.candidate import CandidateCharacter, CandidateMusic

        model = CandidateCharacter if category == "character" else CandidateMusic
        query = select(model).where(model.vote_year == vote_year)
        if q:
            query = query.where(model.name.ilike(f"%{q}%"))

        total = (await self.session.execute(
            select(sqlfunc.count()).select_from(query.subquery())
        )).scalar_one()
        rows = (await self.session.execute(
            query.order_by(model.name).offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()
        return rows, total

    async def delete_candidate(self, candidate_id: int, category: str) -> bool:
        from sqlalchemy import delete
        from src.db_model.candidate import CandidateCharacter, CandidateMusic

        model = CandidateCharacter if category == "character" else CandidateMusic
        result = await self.session.execute(
            delete(model).where(model.id == candidate_id)
        )
        await self.session.commit()
        return result.rowcount > 0
