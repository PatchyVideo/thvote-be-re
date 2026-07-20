"""Vote-objects DAO: grouped candidate listings JOIN voteable + work for metadata."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db_model.candidate import CandidateCharacter, CandidateMusic
from src.db_model.voteable import VoteableCharacter, VoteableMusic
from src.db_model.work import Work

KIND_LABELS = {
    "old": "游戏旧作",
    "new": "游戏新作",
    "CD": "CD",
    "book": "书籍",
    "others": "其他",
}


def _build_alias_map(rows: list[tuple[int, list[str]]]) -> dict[str, int]:
    """Build {alias: candidate_id} map from (candidate_id, aliases) pairs."""
    alias_map: dict[str, int] = {}
    for candidate_id, aliases in rows:
        for a in (aliases or []):
            alias_map[a] = candidate_id
    return alias_map


def _build_filter_meta(items: list[dict]) -> dict:
    """Extract unique kinds + works from item list to build filterMeta."""
    works_map: dict[int, dict] = {}
    kinds_set: set[str] = set()
    for it in items:
        wids = it.get("workIds", [])
        wtypes = it.get("workTypes", [])
        wnames = it.get("_workNames", {})
        for i, wid in enumerate(wids):
            wtype = wtypes[i] if i < len(wtypes) else ""
            name = wnames.get(wid, "")
            works_map[wid] = {"workId": wid, "name": name, "type": wtype}
            kinds_set.add(wtype)
    kinds = [{"type": k, "label": KIND_LABELS.get(k, k)} for k in sorted(kinds_set)]
    works = sorted(works_map.values(), key=lambda w: w["name"])
    return {"kinds": kinds, "works": works}


class VoteObjectsDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_characters(self, vote_year: int) -> dict:
        rows = (
            (
                await self.session.execute(
                    select(
                        CandidateCharacter.id,
                        VoteableCharacter.name,
                        VoteableCharacter.name_jp,
                        VoteableCharacter.type,
                        VoteableCharacter.first_appearance,
                        VoteableCharacter.aliases,
                        Work.id,
                        Work.name,
                        Work.type,
                    )
                    .join(
                        VoteableCharacter,
                        CandidateCharacter.voteable_id == VoteableCharacter.id,
                    )
                    .outerjoin(Work, VoteableCharacter.work_id == Work.id)
                    .where(CandidateCharacter.vote_year == vote_year)
                    .order_by(VoteableCharacter.name)
                )
            )
            .all()
        )

        items: list[dict] = []
        alias_pairs: list[tuple[int, list[str]]] = []
        for row in rows:
            cid, name, name_jp, vtype, first_app, aliases, wid, wname, wtype = row
            work_ids = [wid] if wid is not None else []
            work_types = [wtype] if wtype else []
            items.append(
                {
                    "candidateId": cid,
                    "name": name,
                    "nameJp": name_jp or "",
                    "type": vtype or "",
                    "firstAppearance": first_app or None,
                    "workIds": work_ids,
                    "workTypes": work_types,
                    "_workNames": {wid: wname} if wid else {},
                    "_groupKey": wname or "未分类",
                }
            )
            alias_pairs.append((cid, aliases))

        groups = _group_by(items, "_groupKey")
        alias_map = _build_alias_map(alias_pairs)
        filter_meta = _build_filter_meta(items)
        # clean internal keys
        for g in groups:
            for it in g["items"]:
                it.pop("_workNames", None)
                it.pop("_groupKey", None)
        return {
            "voteYear": vote_year,
            "groups": groups,
            "filterMeta": filter_meta,
            "aliasMap": alias_map,
        }

    async def list_music(self, vote_year: int) -> dict:
        rows = (
            (
                await self.session.execute(
                    select(
                        CandidateMusic.id,
                        VoteableMusic.name,
                        VoteableMusic.name_jp,
                        VoteableMusic.type,
                        VoteableMusic.first_appearance,
                        VoteableMusic.aliases,
                        Work.id,
                        Work.name,
                        Work.type,
                    )
                    .join(
                        VoteableMusic,
                        CandidateMusic.voteable_id == VoteableMusic.id,
                    )
                    .outerjoin(Work, VoteableMusic.work_id == Work.id)
                    .where(CandidateMusic.vote_year == vote_year)
                    .order_by(VoteableMusic.name)
                )
            )
            .all()
        )

        items: list[dict] = []
        alias_pairs: list[tuple[int, list[str]]] = []
        for row in rows:
            cid, name, name_jp, vtype, first_app, aliases, wid, wname, wtype = row
            work_ids = [wid] if wid is not None else []
            work_types = [wtype] if wtype else []
            items.append(
                {
                    "candidateId": cid,
                    "name": name,
                    "nameJp": name_jp or "",
                    "type": vtype or "",
                    "firstAppearance": first_app or None,
                    "workIds": work_ids,
                    "workTypes": work_types,
                    "_workNames": {wid: wname} if wid else {},
                    "_groupKey": wname or "未分类",
                }
            )
            alias_pairs.append((cid, aliases))

        groups = _group_by(items, "_groupKey")
        alias_map = _build_alias_map(alias_pairs)
        filter_meta = _build_filter_meta(items)
        for g in groups:
            for it in g["items"]:
                it.pop("_workNames", None)
                it.pop("_groupKey", None)
        return {
            "voteYear": vote_year,
            "groups": groups,
            "filterMeta": filter_meta,
            "aliasMap": alias_map,
        }

    async def get_one(self, category: str, candidate_id: int) -> dict | None:
        if category == "character":
            row = (
                await self.session.execute(
                    select(
                        CandidateCharacter.id,
                        CandidateCharacter.vote_year,
                        VoteableCharacter.name,
                        VoteableCharacter.name_jp,
                        VoteableCharacter.type,
                        VoteableCharacter.first_appearance,
                        Work.id,
                        Work.name,
                        Work.type,
                    )
                    .join(
                        VoteableCharacter,
                        CandidateCharacter.voteable_id == VoteableCharacter.id,
                    )
                    .outerjoin(Work, VoteableCharacter.work_id == Work.id)
                    .where(CandidateCharacter.id == candidate_id)
                )
            ).one_or_none()
            if row is None:
                return None
            cid, vy, name, name_jp, vtype, first_app, wid, wname, wtype = row
            return {
                "candidateId": cid,
                "voteYear": vy,
                "name": name,
                "nameJp": name_jp or "",
                "type": vtype or "",
                "firstAppearance": first_app or None,
                "workIds": [wid] if wid is not None else [],
                "workTypes": [wtype] if wtype else [],
            }
        else:
            row = (
                await self.session.execute(
                    select(
                        CandidateMusic.id,
                        CandidateMusic.vote_year,
                        VoteableMusic.name,
                        VoteableMusic.name_jp,
                        VoteableMusic.type,
                        VoteableMusic.first_appearance,
                        Work.id,
                        Work.name,
                        Work.type,
                    )
                    .join(
                        VoteableMusic,
                        CandidateMusic.voteable_id == VoteableMusic.id,
                    )
                    .outerjoin(Work, VoteableMusic.work_id == Work.id)
                    .where(CandidateMusic.id == candidate_id)
                )
            ).one_or_none()
            if row is None:
                return None
            cid, vy, name, name_jp, vtype, first_app, wid, wname, wtype = row
            return {
                "candidateId": cid,
                "voteYear": vy,
                "name": name,
                "nameJp": name_jp or "",
                "type": vtype or "",
                "firstAppearance": first_app or None,
                "workIds": [wid] if wid is not None else [],
                "workTypes": [wtype] if wtype else [],
            }


def _group_by(items: list[dict], key: str) -> list[dict]:
    """Group items into [{group, items}], preserving first-seen group order."""
    groups_map: dict[str, list] = {}
    order: list[str] = []
    for it in items:
        g = it.get(key) or "未分类"
        if g not in groups_map:
            groups_map[g] = []
            order.append(g)
        groups_map[g].append(it)
    return [{"group": g, "items": groups_map[g]} for g in order]
