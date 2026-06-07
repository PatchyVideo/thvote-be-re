"""Admin service — wraps ComputeService and ComputeDAO."""

from __future__ import annotations

import json

from sqlalchemy import func as sqlfunc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.admin.schemas import ImportCandidatesRequest
from src.apps.result.compute_dao import ComputeDAO
from src.apps.result.compute_service import ComputeService
from src.apps.result.dao import ResultNotComputedError
from src.apps.user.dao import UserDAO
from src.apps.vote_data.dao import VoteDataDAO
from src.db_model.raw_submit import RawDojinSubmit


class AdminService:
    def __init__(self, compute_service: ComputeService, compute_dao: ComputeDAO, session: AsyncSession | None = None):
        self.compute_service = compute_service
        self.compute_dao = compute_dao
        self._session = session

    async def compute_results(self, vote_year: int) -> dict:
        return await self.compute_service.compute_all(vote_year)

    async def import_candidates(self, request: ImportCandidatesRequest) -> int:
        items = [item.model_dump(exclude_none=False) for item in request.items]
        return await self.compute_dao.upsert_candidates(
            request.vote_year, request.category, items
        )

    async def finalize_ranking(self, vote_year: int) -> int:
        """Read computed Redis ranking and archive to final_ranking PG table."""
        redis = self.compute_service.redis
        total = 0
        found_any = False
        for category in ("character", "music", "cp"):
            cat_key = {"character": "chars", "music": "musics", "cp": "cps"}[category]
            key = f"result:{vote_year}:{cat_key}:ranking"
            raw = await redis.get(key)
            if raw:
                found_any = True
                entries = json.loads(raw)
                saved = await self.compute_dao.save_final_ranking(
                    vote_year, category, entries
                )
                total += saved
        if not found_any:
            raise ResultNotComputedError(
                "No ranking data found in Redis for any category"
            )
        return total

    async def list_users(
        self, email: str | None, phone: str | None, page: int, page_size: int
    ) -> dict:
        user_dao = UserDAO(self._session)
        users, total = await user_dao.search_users(email, phone, page, page_size)
        return {"items": users, "total": total}

    async def get_user_detail(self, user_id: str) -> dict | None:
        user_dao = UserDAO(self._session)
        user = await user_dao.get_by_id_any(user_id)
        if user is None:
            return None
        vote_dao = VoteDataDAO(self._session)
        char = await vote_dao.get_character_by_id(user_id)
        music = await vote_dao.get_music_by_id(user_id)
        cp = await vote_dao.get_cp_by_id(user_id)
        questionnaire = await vote_dao.get_questionnaire_by_id(user_id)
        dojin_count = (await self._session.execute(
            select(sqlfunc.count()).select_from(RawDojinSubmit).where(RawDojinSubmit.vote_id == user_id)
        )).scalar_one()
        return {
            "user": user,
            "vote_submitted": {
                "character": char is not None,
                "music": music is not None,
                "cp": cp is not None,
                "paper": questionnaire is not None,
                "dojin": dojin_count > 0,
            },
        }

    async def ban_user(self, user_id: str):
        return await UserDAO(self._session).set_removed(user_id, removed=True)

    async def unban_user(self, user_id: str):
        return await UserDAO(self._session).set_removed(user_id, removed=False)
