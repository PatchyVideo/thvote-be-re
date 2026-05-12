"""ComputeService — orchestrates compute pipeline and writes to Redis."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import redis.asyncio as aioredis

from src.apps.result.compute import (
    compute_completion_rates,
    compute_covote,
    compute_cp_ranking,
    compute_gender_map,
    compute_global_stats,
    compute_paper_results,
    compute_ranking,
)
from src.apps.result.compute_dao import ComputeDAO
from src.common.config import Settings
from src.common.exceptions import AppException

logger = logging.getLogger(__name__)

LOCK_TTL_MS = 300_000  # 5 minutes


class ComputeInProgressError(AppException):
    pass


class ComputeService:
    def __init__(self, compute_dao: ComputeDAO, redis: aioredis.Redis, settings: Settings):
        self.dao = compute_dao
        self.redis = redis
        self.settings = settings

    def _key(self, vote_year: int, *parts: str) -> str:
        return f"result:{vote_year}:" + ":".join(parts)

    def _lock_key(self, vote_year: int) -> str:
        return f"compute_lock:{vote_year}"

    async def compute_all(self, vote_year: int) -> dict:
        """Run full computation pipeline for the given vote_year. Writes results to Redis."""
        lock_key = self._lock_key(vote_year)
        acquired = await self.redis.set(lock_key, "1", nx=True, px=LOCK_TTL_MS)
        if not acquired:
            raise ComputeInProgressError("Compute already in progress")

        t0 = time.monotonic()
        try:
            s = self.settings
            vote_start_str = s.vote_start_iso.replace("Z", "+00:00")
            vote_end_str = s.vote_end_iso.replace("Z", "+00:00")
            vote_start = datetime.fromisoformat(vote_start_str)
            vote_end = datetime.fromisoformat(vote_end_str)
            # Ensure timezone-aware regardless of format
            if vote_start.tzinfo is None:
                vote_start = vote_start.replace(tzinfo=timezone.utc)
            if vote_end.tzinfo is None:
                vote_end = vote_end.replace(tzinfo=timezone.utc)
            total_hours = max(1, int((vote_end - vote_start).total_seconds() / 3600))

            # Load all data
            char_votes = await self.dao.load_char_votes()
            music_votes = await self.dao.load_music_votes()
            cp_votes = await self.dao.load_cp_votes()
            q_votes = await self.dao.load_questionnaire_votes()

            char_candidates = await self.dao.load_char_candidates(vote_year)
            music_candidates = await self.dao.load_music_candidates(vote_year)

            char_hist = await self.dao.load_historical(vote_year, "character")
            music_hist = await self.dao.load_historical(vote_year, "music")
            cp_hist = await self.dao.load_historical(vote_year, "cp")

            # Compute
            gender_map = compute_gender_map(
                q_votes, s.gender_question_id, s.gender_male_value, s.gender_female_value
            )
            char_ranking, char_global = compute_ranking(
                char_votes, char_candidates, gender_map, char_hist, vote_start, total_hours
            )
            music_ranking, music_global = compute_ranking(
                music_votes, music_candidates, gender_map, music_hist, vote_start, total_hours
            )
            cp_ranking, cp_global = compute_cp_ranking(
                cp_votes, gender_map, cp_hist, vote_start, total_hours
            )

            all_voters = (
                {uid for uid, _, _ in char_votes}
                | {uid for uid, _, _ in music_votes}
                | {uid for uid, _, _ in cp_votes}
                | {uid for uid, _ in q_votes}
            )
            global_stats = compute_global_stats(char_votes, music_votes, cp_votes, q_votes, gender_map)
            completion_rates = compute_completion_rates(
                char_votes, music_votes, cp_votes, q_votes, all_voters
            )
            paper_results = compute_paper_results(q_votes, vote_start, total_hours)
            char_covote = compute_covote(char_votes, top_k=100)
            music_covote = compute_covote(music_votes, top_k=100)

            # Bulk write to Redis
            pipe = self.redis.pipeline()
            pipe.set(self._key(vote_year, "chars", "ranking"), json.dumps(char_ranking))
            pipe.set(self._key(vote_year, "chars", "global"), json.dumps(char_global))
            pipe.set(self._key(vote_year, "musics", "ranking"), json.dumps(music_ranking))
            pipe.set(self._key(vote_year, "musics", "global"), json.dumps(music_global))
            pipe.set(self._key(vote_year, "cps", "ranking"), json.dumps(cp_ranking))
            pipe.set(self._key(vote_year, "cps", "global"), json.dumps(cp_global))
            pipe.set(self._key(vote_year, "global_stats"), json.dumps(global_stats))
            pipe.set(self._key(vote_year, "completion_rates"), json.dumps(completion_rates))
            pipe.set(self._key(vote_year, "covote", "chars"), json.dumps(char_covote))
            pipe.set(self._key(vote_year, "covote", "musics"), json.dumps(music_covote))
            for qid, data in paper_results.items():
                pipe.set(self._key(vote_year, "paper", qid), json.dumps(data))
            await pipe.execute()

            duration = round(time.monotonic() - t0, 2)
            logger.info("Compute complete for vote_year=%d in %.2fs", vote_year, duration)
            return {
                "ok": True,
                "vote_year": vote_year,
                "duration_seconds": duration,
                "counts": {
                    "chars": len(char_ranking),
                    "musics": len(music_ranking),
                    "cps": len(cp_ranking),
                    "questions": len(paper_results),
                },
            }
        finally:
            await self.redis.delete(lock_key)
