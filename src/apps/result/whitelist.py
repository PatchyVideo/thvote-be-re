"""id 白名单 / 展示注册表（B-050 → 计票真相源迁 DB）。

双键 ``Whitelist``（canonical key = ``str(candidate_id)``；legacy 8-hex
``old_id`` 仍可作为第二 token 命中同一条 entry）+ 异步 DB 加载
``load_whitelist_db``，数据源为 ``voteable_* JOIN candidate_*(vote_year)
LEFT JOIN work``（设计稿 §4.1/§4.2/§4.4）。

旧的 JSON 快照加载路径（``load_whitelist``/``_to_entry``）已随 Task 6 删除
（compute_service.py / result_compat.py 全部切到 ``load_whitelist_db``）；
快照 JSON 本身仍在 ``data/`` 目录保留，作为 ``scripts/whitelist_to_import.py``
一次性回填导入通道的数据源。
"""

from __future__ import annotations

from dataclasses import dataclass

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
