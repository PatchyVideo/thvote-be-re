"""id 白名单 / 展示注册表（B-050 → 计票真相源迁 DB）。

新实现：双键 ``Whitelist``（canonical key = ``str(candidate_id)``；legacy
8-hex ``old_id`` 仍可作为第二 token 命中同一条 entry）+ 异步 DB 加载
``load_whitelist_db``，数据源为 ``voteable_* JOIN candidate_*(vote_year)
LEFT JOIN work``（设计稿 §4.1/§4.2/§4.4）。

旧的 JSON 快照加载路径（``load_whitelist``/``_to_entry``）暂时保留在文件
尾部并标记 ``# DEPRECATED: Task 6 移除``——compute_service.py 等调用方尚未
切换到 DB 加载，迁移完成前不能删除。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

_DATA_DIR = Path(__file__).parent / "data"
_UNKNOWN_SYSTEM_ID = 10**9  # 未知 id 排最后（正常不该走到，白名单已先过滤）

# 前端 kind → 展示用 type（唯一来源；原 compute.KIND_MAPPING 已随死代码清理删除）
_KIND_MAPPING: dict[str, str] = {
    "old": "旧作", "new": "新作", "CD": "专辑", "book": "出版物",
    "others": "其他", "other": "其他", "game": "游戏",
}

SORT_ORDER_TAIL_BASE = 10**8  # sort_order 缺失时排到尾部,彼此按 candidate_id 顺延


@dataclass(frozen=True)
class WhitelistEntry:
    candidate_id: int
    voteable_id: int
    old_id: str | None
    name: str
    name_jp: str
    origin: str
    type: str
    first_appearance: str | None
    album: str | None
    system_id: int


class Whitelist:
    def __init__(self, entries: list[WhitelistEntry]):
        self._entries = list(entries)
        self._by_token: dict[str, WhitelistEntry] = {}
        for e in entries:
            for token in filter(None, (str(e.candidate_id), e.old_id)):
                if token in self._by_token:
                    raise ValueError(f"whitelist token collision: {token!r}")
                self._by_token[token] = e

    @property
    def entries(self) -> list[WhitelistEntry]:
        return self._entries

    @property
    def ids(self) -> set[str]:
        return {str(e.candidate_id) for e in self._entries}

    def __contains__(self, token: str) -> bool:
        return token in self._by_token

    def get(self, token: str) -> WhitelistEntry | None:
        return self._by_token.get(token)

    def canonical(self, token: str) -> str | None:
        e = self._by_token.get(token)
        return str(e.candidate_id) if e else None

    def name_of(self, token: str) -> str:
        e = self._by_token.get(token)
        return e.name if e else token

    def system_id_of(self, token: str) -> int:
        e = self._by_token.get(token)
        return e.system_id if e else _UNKNOWN_SYSTEM_ID


async def load_whitelist_db(session, category, vote_year: int) -> Whitelist:
    """voteable JOIN candidate(vote_year) LEFT JOIN work → Whitelist。"""
    from sqlalchemy import select
    from src.db_model.candidate import CandidateCharacter, CandidateMusic
    from src.db_model.voteable import VoteableCharacter, VoteableMusic
    from src.db_model.work import Work

    C = CandidateCharacter if category == "character" else CandidateMusic
    V = VoteableCharacter if category == "character" else VoteableMusic
    rows = (await session.execute(
        select(C.id, C.sort_order, V.id, V.name, V.name_jp, V.type,
               V.first_appearance, V.old_id, Work.name)
        .join(V, C.voteable_id == V.id)
        .outerjoin(Work, V.work_id == Work.id)
        .where(C.vote_year == vote_year)
    )).all()
    entries = []
    for cid, sort, vid, name, name_jp, vtype, first_app, old_id, wname in rows:
        entries.append(WhitelistEntry(
            candidate_id=cid, voteable_id=vid, old_id=old_id,
            name=name, name_jp=name_jp or "",
            origin=wname or "",
            type=_KIND_MAPPING.get(vtype or "", vtype or "未知"),
            first_appearance=str(first_app) if first_app else None,
            album=(wname or None) if category == "music" else None,
            system_id=(sort if sort is not None
                       else SORT_ORDER_TAIL_BASE + cid),
        ))
    return Whitelist(entries)


# ─────────────────────────────────────────────────────────────────────────
# DEPRECATED: Task 6 移除 —— 旧 JSON 快照加载路径。
#
# 数据来源：从前端 characterList/musicList 提取的冻结快照 JSON
# （scripts/extract_whitelist.mjs 产出）。运行时只读快照，不依赖前端仓库。
# compute_service.py 等调用方切到 load_whitelist_db 后即可随 Task 6 一并删除。
# ─────────────────────────────────────────────────────────────────────────

def _to_entry(raw: dict, seq: int) -> WhitelistEntry:
    """把快照行适配成新 10 字段 WhitelistEntry。

    快照没有真正的 candidate_id/voteable_id 概念，用 1-based 顺序号 ``seq``
    顶替（同一快照每次加载顺序稳定，见 load_whitelist 的 enumerate）；
    old_id 用快照原始 8-hex id，双键索引里旧 token 依然能命中。
    """
    kinds = raw.get("kind") or []
    work = raw.get("work") or []
    date = raw.get("date")
    return WhitelistEntry(
        candidate_id=seq,
        voteable_id=seq,
        old_id=str(raw["id"]),
        name=raw.get("name", ""),
        name_jp=raw.get("name_jp", ""),
        origin="、".join(work) if work else "",
        type=_KIND_MAPPING.get(kinds[0], "其他") if kinds else "未知",
        first_appearance=str(date) if date else None,
        album=raw.get("album"),
        system_id=int(raw.get("system_id", _UNKNOWN_SYSTEM_ID)),
    )


@lru_cache(maxsize=4)
def load_whitelist(category: Literal["character", "music"]) -> Whitelist:
    path = _DATA_DIR / f"whitelist_{category}.json"
    raw_list = json.loads(path.read_text(encoding="utf-8"))
    return Whitelist([_to_entry(r, seq) for seq, r in enumerate(raw_list, start=1)])
