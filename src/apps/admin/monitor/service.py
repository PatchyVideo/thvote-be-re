"""监控编排 + 轻缓存(B-049)。贵的聚合(概览/分组/可疑名单)缓存 60s;
按需实时算,数据陈旧 60s 对监控可接受。可疑名单只给命中廉价信号的候选打分。
"""

from __future__ import annotations

import json
import logging

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.admin.monitor.dao import MonitorDAO
from src.apps.admin.monitor.schemas import (
    GroupItem,
    GroupsResponse,
    OverviewResponse,
    SuspectItem,
    SuspectsResponse,
    VotesPage,
)
from src.apps.admin.monitor.scoring import (
    CLUSTER_MIN_SIZE,
    FAST_FILL_MS,
    score_account,
)
from src.common.config import Settings

_logger = logging.getLogger(__name__)

_CACHE_TTL = 60
_SUSPECT_CAP = 2000  # 候选账号封顶,超出记日志(不静默截断)


class MonitorService:
    def __init__(self, session: AsyncSession, redis: aioredis.Redis,
                 settings: Settings):
        self.dao = MonitorDAO(session)
        self.redis = redis
        self.settings = settings

    async def _cached(self, key: str, compute):
        try:
            raw = await self.redis.get(key)
            if raw:
                return json.loads(raw)
        except Exception:  # 缓存不可用不该拖垮读接口
            _logger.warning("monitor cache read failed for %s", key)
        value = await compute()
        try:
            await self.redis.set(key, json.dumps(value), ex=_CACHE_TTL)
        except Exception:
            _logger.warning("monitor cache write failed for %s", key)
        return value

    async def overview(self) -> OverviewResponse:
        async def _compute():
            return {
                "category_totals": await self.dao.category_totals(),
                "distinct_ips": await self.dao.distinct_ip_count(),
                "distinct_devices": await self.dao.distinct_device_count(),
                "submissions_by_day": await self.dao.submissions_by_day(),
            }
        data = await self._cached("admin:monitor:overview", _compute)
        return OverviewResponse(**data)

    async def groups(self, kind: str, min_size: int, limit: int) -> GroupsResponse:
        async def _compute():
            if kind == "device":
                items = await self.dao.device_groups(min_size, limit)
            else:
                items = await self.dao.ip_groups(min_size, limit)
            return items
        key = f"admin:monitor:groups:{kind}:{min_size}:{limit}"
        items = await self._cached(key, _compute)
        return GroupsResponse(
            kind=kind, items=[GroupItem(**i) for i in items]
        )

    async def suspects(self, page: int, page_size: int) -> SuspectsResponse:
        async def _compute():
            candidates = await self.dao.candidate_vote_ids(
                CLUSTER_MIN_SIZE, FAST_FILL_MS, _SUSPECT_CAP
            )
            truncated = len(candidates) >= _SUSPECT_CAP
            if truncated:
                _logger.warning(
                    "suspect candidates hit cap %s; list truncated", _SUSPECT_CAP
                )
            scored = []
            for vid in candidates:
                features = await self.dao.account_features(vid)
                result = score_account(features)
                if result.score > 0:
                    scored.append(
                        {"vote_id": vid, "score": result.score,
                         "reasons": result.reasons}
                    )
            scored.sort(key=lambda s: s["score"], reverse=True)
            return {"scored": scored, "truncated": truncated}

        data = await self._cached("admin:monitor:suspects", _compute)
        scored = data["scored"]
        total = len(scored)
        start = (page - 1) * page_size
        window = scored[start:start + page_size]
        return SuspectsResponse(
            items=[SuspectItem(**s) for s in window],
            total=total, page=page, page_size=page_size,
            truncated=data["truncated"],
        )

    async def list_votes(self, category: str, vote_id, user_ip, device,
                         invalidated, page: int, page_size: int) -> VotesPage:
        rows, total = await self.dao.list_votes(
            category, vote_id, user_ip, device, invalidated, page, page_size
        )
        return VotesPage(items=rows, total=total, page=page, page_size=page_size)
