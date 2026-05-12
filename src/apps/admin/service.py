"""Admin service — wraps ComputeService and ComputeDAO."""

from __future__ import annotations

import json

from src.apps.admin.schemas import ImportCandidatesRequest
from src.apps.result.compute_dao import ComputeDAO
from src.apps.result.compute_service import ComputeService
from src.apps.result.dao import ResultNotComputedError


class AdminService:
    def __init__(self, compute_service: ComputeService, compute_dao: ComputeDAO):
        self.compute_service = compute_service
        self.compute_dao = compute_dao

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
                saved = await self.compute_dao.save_final_ranking(vote_year, category, entries)
                total += saved
        if not found_any:
            raise ResultNotComputedError("No ranking data found in Redis for any category")
        return total
