"""管理端安全监控读侧查询(B-049)。只读 raw_*(路径 A);排除 raw_work(废弃)。

每个聚合都是单表/UNION 上的索引 GROUP BY,取证量级(每表约 5 万行)亚秒。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Date, cast, func, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.admin.monitor.scoring import AccountFeatures
from src.db_model.raw_submit import (
    RawCharacterSubmit,
    RawCPSubmit,
    RawDojinSubmit,
    RawMusicSubmit,
    RawPaperSubmit,
)
from src.db_model.user import User

# 参与监控的 5 类(raw_work 废弃,不含)。paper 用 papers_json,其余用 payload。
CATEGORY_MODELS: dict[str, type] = {
    "character": RawCharacterSubmit,
    "music": RawMusicSubmit,
    "cp": RawCPSubmit,
    "paper": RawPaperSubmit,
    "dojin": RawDojinSubmit,
}
_MODELS = tuple(CATEGORY_MODELS.values())

_SCRIPTED_UA_MARKERS = ("headless", "phantom", "selenium", "python-requests",
                        "curl", "wget", "httpx", "bot")


class MonitorDAO:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ── 概览 ────────────────────────────────────────────────────────────────
    async def category_totals(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for name, model in CATEGORY_MODELS.items():
            stmt = select(func.count(func.distinct(model.vote_id)))
            out[name] = (await self.session.execute(stmt)).scalar_one()
        return out

    async def distinct_ip_count(self) -> int:
        sub = union_all(*[select(m.user_ip.label("ip")) for m in _MODELS]).subquery()
        stmt = select(func.count(func.distinct(sub.c.ip)))
        return (await self.session.execute(stmt)).scalar_one()

    async def distinct_device_count(self) -> int:
        sub = union_all(*[
            select(m.additional_fingreprint.label("dev")) for m in _MODELS
        ]).subquery()
        stmt = select(func.count(func.distinct(sub.c.dev))).where(
            sub.c.dev.isnot(None)
        )
        return (await self.session.execute(stmt)).scalar_one()

    async def submissions_by_day(self) -> list[dict]:
        sub = union_all(*[
            select(m.created_at.label("ts")) for m in _MODELS
        ]).subquery()
        day = cast(sub.c.ts, Date).label("day")
        stmt = select(day, func.count().label("n")).group_by(day).order_by(day)
        rows = (await self.session.execute(stmt)).all()
        return [{"date": str(r.day), "count": r.n} for r in rows]

    # ── 聚类 ────────────────────────────────────────────────────────────────
    async def _groups(self, col_name: str, min_size: int, limit: int) -> list[dict]:
        sub = union_all(*[
            select(
                getattr(m, col_name).label("key"),
                m.vote_id.label("vote_id"),
            )
            for m in _MODELS
        ]).subquery()
        cnt = func.count(func.distinct(sub.c.vote_id)).label("voter_count")
        stmt = (
            select(sub.c.key, cnt)
            .where(sub.c.key.isnot(None))
            .group_by(sub.c.key)
            .having(cnt >= min_size)
            .order_by(cnt.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [{"key": r.key, "voter_count": r.voter_count} for r in rows]

    async def ip_groups(self, min_size: int, limit: int) -> list[dict]:
        return await self._groups("user_ip", min_size, limit)

    async def device_groups(self, min_size: int, limit: int) -> list[dict]:
        return await self._groups("additional_fingreprint", min_size, limit)

    async def group_members(self, kind: str, key: str) -> list[str]:
        col = "user_ip" if kind == "ip" else "additional_fingreprint"
        sub = union_all(*[
            select(getattr(m, col).label("key"), m.vote_id.label("vote_id"))
            for m in _MODELS
        ]).subquery()
        stmt = select(func.distinct(sub.c.vote_id)).where(sub.c.key == key)
        return [r[0] for r in (await self.session.execute(stmt)).all()]

    # ── 投票浏览器(单类别过滤 + 分页)──────────────────────────────────────
    async def list_votes(
        self,
        category: str,
        vote_id: Optional[str],
        user_ip: Optional[str],
        device: Optional[str],
        invalidated: Optional[bool],
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int]:
        model = CATEGORY_MODELS[category]  # KeyError → 调用方(router)先校验
        conds = []
        if vote_id:
            conds.append(model.vote_id == vote_id)
        if user_ip:
            conds.append(model.user_ip == user_ip)
        if device:
            conds.append(model.additional_fingreprint == device)
        if invalidated is not None:
            conds.append(model.invalidated.is_(invalidated))

        total = (await self.session.execute(
            select(func.count()).select_from(model).where(*conds)
        )).scalar_one()

        stmt = (
            select(model)
            .where(*conds)
            .order_by(model.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        objs = (await self.session.execute(stmt)).scalars().all()
        rows = [{
            "id": o.id,
            "vote_id": o.vote_id,
            "user_ip": o.user_ip,
            "device": o.additional_fingreprint,
            "fill_duration_ms": o.fill_duration_ms,
            "client_env": o.client_env,
            "attempt": o.attempt,
            "invalidated": o.invalidated,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        } for o in objs]
        return rows, total

    # ── 单账号钻取 ─────────────────────────────────────────────────────────
    async def account_votes(self, vote_id: str) -> dict:
        out: dict[str, list] = {}
        for name, model in CATEGORY_MODELS.items():
            stmt = select(model).where(model.vote_id == vote_id).order_by(
                model.created_at.desc()
            )
            objs = (await self.session.execute(stmt)).scalars().all()
            out[name] = [self._row_full(name, o) for o in objs]
        return out

    @staticmethod
    def _row_full(category: str, o) -> dict:
        payload = o.papers_json if category == "paper" else o.payload
        return {
            "id": o.id,
            "user_ip": o.user_ip,
            "device": o.additional_fingreprint,
            "fill_duration_ms": o.fill_duration_ms,
            "client_env": o.client_env,
            "attempt": o.attempt,
            "invalidated": o.invalidated,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "payload": payload,
        }

    # ── 可疑打分:候选集 + 特征装配 ─────────────────────────────────────────
    async def candidate_vote_ids(
        self, cluster_min: int, fast_fill_ms: int, cap: int
    ) -> list[str]:
        """只挑已命中廉价 SQL 信号的账号(在大组里 / 首投过快 / 无 client_env),
        避免给全部投票人算分。结果去重、封顶(封顶记日志,见 service)。"""
        big_ips = [g["key"] for g in await self.ip_groups(cluster_min, cap)]
        big_devs = [g["key"] for g in await self.device_groups(cluster_min, cap)]
        vote_ids: set[str] = set()
        for m in _MODELS:
            conds = [
                (m.fill_duration_ms.isnot(None)) & (m.fill_duration_ms < fast_fill_ms),
                m.client_env.is_(None),
            ]
            if big_ips:
                conds.append(m.user_ip.in_(big_ips))
            if big_devs:
                conds.append(m.additional_fingreprint.in_(big_devs))
            stmt = select(func.distinct(m.vote_id)).where(or_(*conds)).limit(cap)
            vote_ids.update(r[0] for r in (await self.session.execute(stmt)).all())
            if len(vote_ids) >= cap:
                break
        return list(vote_ids)[:cap]

    async def account_features(self, vote_id: str) -> AccountFeatures:
        # 各类别最小首投耗时 + 是否有 client_env/ua + ua 是否脚本特征
        min_fill: Optional[int] = None
        has_env = False
        ua_scripted = False
        first_vote_ts: Optional[datetime] = None
        for m in _MODELS:
            stmt = select(
                m.fill_duration_ms, m.client_env, m.created_at
            ).where(m.vote_id == vote_id)
            for fill, env, ts in (await self.session.execute(stmt)).all():
                if fill is not None and (min_fill is None or fill < min_fill):
                    min_fill = fill
                if env:
                    ua = str((env or {}).get("ua", "")).lower()
                    if ua:
                        has_env = True  # 有 env 且有 ua 才算"像真人浏览器"
                        if any(k in ua for k in _SCRIPTED_UA_MARKERS):
                            ua_scripted = True
                if ts is not None and (first_vote_ts is None or ts < first_vote_ts):
                    first_vote_ts = ts

        seconds: Optional[float] = None
        reg = (await self.session.execute(
            select(User.register_date).where(User.id == vote_id)
        )).scalar_one_or_none()
        if reg is not None and first_vote_ts is not None:
            try:
                seconds = (first_vote_ts - reg).total_seconds()
            except (TypeError, ValueError):
                seconds = None

        ip_size = await self._max_group_size("user_ip", vote_id)
        dev_size = await self._max_group_size("additional_fingreprint", vote_id)

        return AccountFeatures(
            min_fill_duration_ms=min_fill,
            has_client_env=has_env,
            ua_is_scripted=ua_scripted,
            seconds_register_to_first_vote=seconds,
            max_ip_group_size=ip_size,
            max_device_group_size=dev_size,
            # 跨账号 payload 雷同检测较贵,初版不算(恒 False),留作后续信号。
            has_duplicate_payload=False,
        )

    async def _max_group_size(self, col: str, vote_id: str) -> int:
        """该账号所在的 IP/设备组里,最大有多少不同账号(取此账号出现的各 key 的最大组规模)。"""
        keys_sub = union_all(*[
            select(getattr(m, col).label("key")).where(m.vote_id == vote_id)
            for m in _MODELS
        ]).subquery()
        keys = [r[0] for r in (await self.session.execute(
            select(func.distinct(keys_sub.c.key)).where(keys_sub.c.key.isnot(None))
        )).all()]
        if not keys:
            return 0
        all_sub = union_all(*[
            select(getattr(m, col).label("key"), m.vote_id.label("vote_id"))
            for m in _MODELS
        ]).subquery()
        stmt = select(func.count(func.distinct(all_sub.c.vote_id))).where(
            all_sub.c.key.in_(keys)
        )
        return (await self.session.execute(stmt)).scalar_one()
