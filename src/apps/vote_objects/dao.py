"""Vote-objects DAO: grouped candidate listings JOIN voteable for metadata."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db_model.candidate import CandidateCharacter, CandidateMusic
from src.db_model.voteable import VoteableCharacter, VoteableMusic


def _build_alias_map(
    rows: list[tuple[int, list[str]]],
) -> dict[str, int]:
    """Build {alias: candidate_id} map from (candidate_id, aliases) pairs."""
    alias_map: dict[str, int] = {}
    for candidate_id, aliases in rows:
        for a in (aliases or []):
            alias_map[a] = candidate_id
    return alias_map


class VoteObjectsDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_characters(self, vote_year: int) -> dict:
        """Return groups + items with metadata from voteable_character."""
        rows = (
            (
                await self.session.execute(
                    select(
                        CandidateCharacter.id,
                        VoteableCharacter.name,
                        VoteableCharacter.name_jp,
                        VoteableCharacter.origin,
                        VoteableCharacter.type,
                        VoteableCharacter.first_appearance,
                        VoteableCharacter.aliases,
                    )
                    .join(
                        VoteableCharacter,
                        CandidateCharacter.voteable_id == VoteableCharacter.id,
                    )
                    .where(CandidateCharacter.vote_year == vote_year)
                    .order_by(VoteableCharacter.name)
                )
            )
            .all()
        )

        items: list[dict] = []
        alias_pairs: list[tuple[int, list[str]]] = []
        for row in rows:
            cid, name, name_jp, origin, vtype, first_app, aliases = row
            items.append({
                "candidateId": cid,
                "name": name,
                "nameJp": name_jp or "",
                "origin": origin or "",
                "type": vtype or "",
                "firstAppearance": first_app or None,
            })
            alias_pairs.append((cid, aliases))

        groups = _group_by(items, "origin")
        alias_map = _build_alias_map(alias_pairs)
        return {"voteYear": vote_year, "groups": groups, "aliasMap": alias_map}

    async def list_music(self, vote_year: int) -> dict:
        """Return groups + items with metadata from voteable_music."""
        rows = (
            (
                await self.session.execute(
                    select(
                        CandidateMusic.id,
                        VoteableMusic.name,
                        VoteableMusic.name_jp,
                        VoteableMusic.type,
                        VoteableMusic.first_appearance,
                        VoteableMusic.album,
                        VoteableMusic.aliases,
                    )
                    .join(
                        VoteableMusic,
                        CandidateMusic.voteable_id == VoteableMusic.id,
                    )
                    .where(CandidateMusic.vote_year == vote_year)
                    .order_by(VoteableMusic.name)
                )
            )
            .all()
        )

        items: list[dict] = []
        alias_pairs: list[tuple[int, list[str]]] = []
        for row in rows:
            cid, name, name_jp, vtype, first_app, album, aliases = row
            items.append({
                "candidateId": cid,
                "name": name,
                "nameJp": name_jp or "",
                "type": vtype or "",
                "firstAppearance": first_app or None,
                "album": album or None,
            })
            alias_pairs.append((cid, aliases))

        groups = _group_by(items, "album")
        alias_map = _build_alias_map(alias_pairs)
        return {"voteYear": vote_year, "groups": groups, "aliasMap": alias_map}

    async def get_one(self, category: str, candidate_id: int) -> dict | None:
        """Get a single candidate detail JOINed with voteable metadata."""
        if category == "character":
            row = (
                await self.session.execute(
                    select(
                        CandidateCharacter.id,
                        CandidateCharacter.vote_year,
                        VoteableCharacter.name,
                        VoteableCharacter.name_jp,
                        VoteableCharacter.origin,
                        VoteableCharacter.first_appearance,
                    )
                    .join(
                        VoteableCharacter,
                        CandidateCharacter.voteable_id == VoteableCharacter.id,
                    )
                    .where(CandidateCharacter.id == candidate_id)
                )
            ).one_or_none()
            if row is None:
                return None
            cid, vy, name, name_jp, origin, first_app = row
            return {
                "candidateId": cid,
                "voteYear": vy,
                "name": name,
                "nameJp": name_jp or "",
                "origin": origin or "",
                "firstAppearance": first_app or None,
            }
        else:
            row = (
                await self.session.execute(
                    select(
                        CandidateMusic.id,
                        CandidateMusic.vote_year,
                        VoteableMusic.name,
                        VoteableMusic.name_jp,
                        VoteableMusic.album,
                        VoteableMusic.first_appearance,
                    )
                    .join(
                        VoteableMusic,
                        CandidateMusic.voteable_id == VoteableMusic.id,
                    )
                    .where(CandidateMusic.id == candidate_id)
                )
            ).one_or_none()
            if row is None:
                return None
            cid, vy, name, name_jp, album, first_app = row
            return {
                "candidateId": cid,
                "voteYear": vy,
                "name": name,
                "nameJp": name_jp or "",
                "origin": "",
                "album": album or None,
                "firstAppearance": first_app or None,
            }


def _group_by(items: list[dict], key: str) -> list[dict]:
    """Group items into [{group, items}], preserving first-seen group order."""
    groups: dict[str, list] = {}
    order: list[str] = []
    for it in items:
        g = it.get(key) or "未分类"
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append(it)
    return [{"group": g, "items": groups[g]} for g in order]
