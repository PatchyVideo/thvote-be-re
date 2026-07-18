"""id 白名单 / 展示注册表（B-050）。

数据来源：从前端 characterList/musicList 提取的冻结快照 JSON
（scripts/extract_whitelist.mjs 产出）。运行时只读快照，不依赖前端仓库。
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


@dataclass(frozen=True)
class WhitelistEntry:
    id: str
    name: str
    name_jp: str
    origin: str
    type: str
    first_appearance: str | None
    album: str | None
    system_id: int


def _to_entry(raw: dict) -> WhitelistEntry:
    kinds = raw.get("kind") or []
    work = raw.get("work") or []
    date = raw.get("date")
    return WhitelistEntry(
        id=str(raw["id"]),
        name=raw.get("name", ""),
        name_jp=raw.get("name_jp", ""),
        origin="、".join(work) if work else "",
        type=_KIND_MAPPING.get(kinds[0], "其他") if kinds else "未知",
        first_appearance=str(date) if date else None,
        album=raw.get("album"),
        system_id=int(raw.get("system_id", _UNKNOWN_SYSTEM_ID)),
    )


class Whitelist:
    def __init__(self, entries: list[WhitelistEntry]):
        self._by_id: dict[str, WhitelistEntry] = {e.id: e for e in entries}
        if len(self._by_id) != len(entries):
            raise ValueError(
                f"whitelist has duplicate ids: {len(entries) - len(self._by_id)} collision(s)"
            )

    @property
    def ids(self) -> set[str]:
        return set(self._by_id.keys())

    def __contains__(self, oid: str) -> bool:
        return oid in self._by_id

    def get(self, oid: str) -> WhitelistEntry | None:
        return self._by_id.get(oid)

    def name_of(self, oid: str) -> str:
        e = self._by_id.get(oid)
        return e.name if e else oid

    def system_id_of(self, oid: str) -> int:
        e = self._by_id.get(oid)
        return e.system_id if e else _UNKNOWN_SYSTEM_ID


@lru_cache(maxsize=4)
def load_whitelist(category: Literal["character", "music"]) -> Whitelist:
    path = _DATA_DIR / f"whitelist_{category}.json"
    raw_list = json.loads(path.read_text(encoding="utf-8"))
    return Whitelist([_to_entry(r) for r in raw_list])
