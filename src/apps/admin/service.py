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

    async def get_ranking_preview(
        self, vote_year: int | None, category: str, limit: int
    ) -> list[dict]:
        year = vote_year or self.compute_service.settings.vote_year
        cat_key = {"character": "chars", "music": "musics", "cp": "cps"}.get(category)
        if not cat_key:
            return []
        key = f"result:{year}:{cat_key}:ranking"
        raw = await self.compute_service.redis.get(key)
        if not raw:
            return []
        entries = json.loads(raw)
        return entries[:limit]

    async def list_candidates(
        self, category: str, vote_year: int, q: str | None, page: int, page_size: int
    ) -> dict:
        rows, total = await self.compute_dao.list_candidates(
            category, vote_year, q, page, page_size
        )
        return {"items": rows, "total": total}

    async def delete_candidate(self, candidate_id: int, category: str) -> bool:
        return await self.compute_dao.delete_candidate(candidate_id, category)

    async def list_activity_logs(
        self,
        user_id: str | None,
        action: str | None,
        since: str | None,
        page: int,
        page_size: int,
    ) -> dict:
        from datetime import datetime
        from sqlalchemy import desc
        from src.db_model.activity_log import ActivityLog

        query = select(ActivityLog)
        if user_id:
            query = query.where(ActivityLog.user_id == user_id)
        if action:
            query = query.where(ActivityLog.event_type == action)
        if since:
            dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            query = query.where(ActivityLog.created_at >= dt)

        total = (await self._session.execute(
            select(sqlfunc.count()).select_from(query.subquery())
        )).scalar_one()
        rows = (await self._session.execute(
            query.order_by(desc(ActivityLog.created_at))
            .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()
        return {"items": rows, "total": total}

    async def export_votes_csv(self, vote_year: int, category: str):
        """Async generator yielding CSV rows (header first, then data)."""
        import json as _json
        from src.db_model.raw_submit import (
            RawCharacterSubmit, RawMusicSubmit, RawCPSubmit,
            RawPaperSubmit, RawDojinSubmit,
        )
        _models = {
            "character": RawCharacterSubmit,
            "music": RawMusicSubmit,
            "cp": RawCPSubmit,
            "paper": RawPaperSubmit,
            "dojin": RawDojinSubmit,
        }
        model = _models.get(category)
        if model is None:
            return

        yield "vote_id,attempt,created_at,user_ip,payload\n"

        offset = 0
        batch_size = 500
        while True:
            rows = (await self._session.execute(
                select(model).order_by(model.id).offset(offset).limit(batch_size)
            )).scalars().all()
            if not rows:
                break
            for r in rows:
                payload = getattr(r, "payload", None) or getattr(r, "papers_json", "")
                payload_str = _json.dumps(payload, ensure_ascii=False).replace('"', '""')
                created = r.created_at.isoformat() if r.created_at else ""
                yield f'"{r.vote_id}",{r.attempt or ""},"{created}","{r.user_ip}","{payload_str}"\n'
            offset += batch_size

    async def get_stats(self, vote_year: int | None = None) -> dict:
        from datetime import datetime, timezone
        from src.db_model.user import User
        from src.db_model.raw_submit import (
            RawCharacterSubmit, RawMusicSubmit, RawCPSubmit,
            RawPaperSubmit, RawDojinSubmit,
        )

        year = vote_year or self.compute_service.settings.vote_year
        settings = self.compute_service.settings

        now = datetime.now(timezone.utc)
        start = datetime.fromisoformat(settings.vote_start_iso.replace("Z", "+00:00"))
        end = datetime.fromisoformat(settings.vote_end_iso.replace("Z", "+00:00"))
        if now < start:
            window_status = "upcoming"
        elif now > end:
            window_status = "closed"
        else:
            window_status = "open"

        total_users = (await self._session.execute(
            select(sqlfunc.count()).select_from(User).where(User.removed.is_(False))
        )).scalar_one()

        async def _count_distinct_voters(model):
            return (await self._session.execute(
                select(sqlfunc.count(sqlfunc.distinct(model.vote_id))).select_from(model)
            )).scalar_one()

        return {
            "vote_year": year,
            "total_users": total_users,
            "vote_window": {
                "status": window_status,
                "start": settings.vote_start_iso,
                "end": settings.vote_end_iso,
            },
            "submissions": {
                "character": await _count_distinct_voters(RawCharacterSubmit),
                "music": await _count_distinct_voters(RawMusicSubmit),
                "cp": await _count_distinct_voters(RawCPSubmit),
                "paper": await _count_distinct_voters(RawPaperSubmit),
                "dojin": await _count_distinct_voters(RawDojinSubmit),
            },
        }
