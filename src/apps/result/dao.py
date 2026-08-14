"""ResultDAO — reads pre-computed result data from Redis."""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

from src.common.config import Settings
from src.common.exceptions import AppException


class ResultNotComputedError(AppException):
    """Raised when Redis cache is empty.

    Admin must run /admin/compute-results first.
    """


class EntityNotFoundError(AppException):
    """Raised when a specific entity is not found in computed results."""


class ResultDAO:
    def __init__(
        self,
        redis: aioredis.Redis,
        settings: Settings,
        key_infix: str | None = None,
    ):
        self.redis = redis
        self.settings = settings
        # 高级搜索筛选结果的 key 中缀(adv:{版本}:{指纹});None = 预计算主榜。
        self.key_infix = key_infix

    def _year(self, vote_year: int | None) -> int:
        return vote_year if vote_year is not None else self.settings.vote_year

    def _key(self, vote_year: int, *parts: str) -> str:
        base = f"result:{vote_year}:"
        if self.key_infix:
            base += f"{self.key_infix}:"
        return base + ":".join(parts)

    async def _get_json(self, key: str) -> Any:
        raw = await self.redis.get(key)
        if raw is None:
            raise ResultNotComputedError(f"No computed data at Redis key: {key}")
        return json.loads(raw)

    async def get_ranking(
        self, category: str, names: list[str], vote_year: int | None = None
    ) -> tuple[list[dict], dict]:
        """Returns (ranking_list, global_stats_dict). Filters by names if provided."""
        year = self._year(vote_year)
        cat = _category_key(category)
        ranking = await self._get_json(self._key(year, cat, "ranking"))
        global_stats = await self._get_json(self._key(year, cat, "global"))
        if names:
            ranking = [e for e in ranking if e.get("name") in names]
        return ranking, global_stats

    async def get_reasons(
        self, category: str, name: str, vote_year: int | None = None
    ) -> list[str]:
        year = self._year(vote_year)
        cat = _category_key(category)
        ranking = await self._get_json(self._key(year, cat, "ranking"))
        for entry in ranking:
            if entry.get("name") == name:
                return entry.get("reasons", [])
        raise EntityNotFoundError(name)

    async def get_trend(
        self, category: str, name: str, vote_year: int | None = None
    ) -> dict:
        year = self._year(vote_year)
        cat = _category_key(category)
        ranking = await self._get_json(self._key(year, cat, "ranking"))
        for entry in ranking:
            if entry.get("name") == name:
                return {
                    "trend": entry.get("trend", []),
                    "trend_first": entry.get("trend_first", []),
                }
        raise EntityNotFoundError(name)

    async def get_global_stats(self, vote_year: int | None = None) -> dict:
        return await self._get_json(self._key(self._year(vote_year), "global_stats"))

    async def get_single_entity(
        self, category: str, name: str, vote_year: int | None = None
    ) -> dict:
        year = self._year(vote_year)
        cat = _category_key(category)
        ranking = await self._get_json(self._key(year, cat, "ranking"))
        for entry in ranking:
            if entry.get("name") == name:
                return entry
        raise EntityNotFoundError(name)

    async def get_completion_rates(self, vote_year: int | None = None) -> dict:
        return await self._get_json(
            self._key(self._year(vote_year), "completion_rates")
        )

    async def get_questionnaire(
        self, question_id: str, vote_year: int | None = None
    ) -> dict:
        return await self._get_json(
            self._key(self._year(vote_year), "paper", question_id)
        )

    async def get_questionnaire_trend(
        self, question_id: str, vote_year: int | None = None
    ) -> dict:
        return await self.get_questionnaire(question_id, vote_year)

    async def get_covote(
        self, category: str, vote_year: int | None = None
    ) -> list[dict]:
        cat = "chars" if category == "character" else "musics"
        return await self._get_json(self._key(self._year(vote_year), "covote", cat))


def _category_key(category: str) -> str:
    mapping = {"character": "chars", "music": "musics", "cp": "cps"}
    return mapping.get(category, category)
