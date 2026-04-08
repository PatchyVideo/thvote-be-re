"""Repository layer for raw submit snapshots."""

from sqlalchemy import desc, func, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.orm.raw_submit import (
    RawCPSubmit,
    RawCharacterSubmit,
    RawDojinSubmit,
    RawMusicSubmit,
    RawPaperSubmit,
)


class SubmitRepository:
    """Data access object for submit operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_character_submit(self, data: dict) -> int:
        row = RawCharacterSubmit(**data)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row.id

    async def get_character_submit(self, vote_id: str) -> dict | None:
        stmt = (
            select(RawCharacterSubmit)
            .where(RawCharacterSubmit.vote_id == vote_id)
            .order_by(desc(RawCharacterSubmit.created_at))
            .limit(1)
        )
        row = (await self.session.execute(stmt)).scalars().first()
        if row is None:
            return None
        return {
            "payload": row.payload,
            "vote_id": row.vote_id,
            "attempt": row.attempt,
            "created_at": row.created_at,
            "user_ip": row.user_ip,
            "additional_fingerprint": row.additional_fingerprint,
        }

    async def create_music_submit(self, data: dict) -> int:
        row = RawMusicSubmit(**data)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row.id

    async def get_music_submit(self, vote_id: str) -> dict | None:
        stmt = (
            select(RawMusicSubmit)
            .where(RawMusicSubmit.vote_id == vote_id)
            .order_by(desc(RawMusicSubmit.created_at))
            .limit(1)
        )
        row = (await self.session.execute(stmt)).scalars().first()
        if row is None:
            return None
        return {
            "payload": row.payload,
            "vote_id": row.vote_id,
            "attempt": row.attempt,
            "created_at": row.created_at,
            "user_ip": row.user_ip,
            "additional_fingerprint": row.additional_fingerprint,
        }

    async def create_cp_submit(self, data: dict) -> int:
        row = RawCPSubmit(**data)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row.id

    async def get_cp_submit(self, vote_id: str) -> dict | None:
        stmt = (
            select(RawCPSubmit)
            .where(RawCPSubmit.vote_id == vote_id)
            .order_by(desc(RawCPSubmit.created_at))
            .limit(1)
        )
        row = (await self.session.execute(stmt)).scalars().first()
        if row is None:
            return None
        return {
            "payload": row.payload,
            "vote_id": row.vote_id,
            "attempt": row.attempt,
            "created_at": row.created_at,
            "user_ip": row.user_ip,
            "additional_fingerprint": row.additional_fingerprint,
        }

    async def create_paper_submit(self, data: dict) -> int:
        row = RawPaperSubmit(**data)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row.id

    async def get_paper_submit(self, vote_id: str) -> dict | None:
        stmt = (
            select(RawPaperSubmit)
            .where(RawPaperSubmit.vote_id == vote_id)
            .order_by(desc(RawPaperSubmit.created_at))
            .limit(1)
        )
        row = (await self.session.execute(stmt)).scalars().first()
        if row is None:
            return None
        return {
            "papers_json": row.papers_json,
            "vote_id": row.vote_id,
            "attempt": row.attempt,
            "created_at": row.created_at,
            "user_ip": row.user_ip,
            "additional_fingerprint": row.additional_fingerprint,
        }

    async def create_dojin_submit(self, data: dict) -> int:
        row = RawDojinSubmit(**data)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row.id

    async def get_dojin_submit(self, vote_id: str) -> dict | None:
        stmt = (
            select(RawDojinSubmit)
            .where(RawDojinSubmit.vote_id == vote_id)
            .order_by(desc(RawDojinSubmit.created_at))
            .limit(1)
        )
        row = (await self.session.execute(stmt)).scalars().first()
        if row is None:
            return None
        return {
            "payload": row.payload,
            "vote_id": row.vote_id,
            "attempt": row.attempt,
            "created_at": row.created_at,
            "user_ip": row.user_ip,
            "additional_fingerprint": row.additional_fingerprint,
        }

    async def has_submit(self, vote_id: str) -> dict[str, bool]:
        async def _has(model) -> bool:
            stmt = select(model.id).where(model.vote_id == vote_id).limit(1)
            return (await self.session.execute(stmt)).scalar_one_or_none() is not None

        return {
            "characters": await _has(RawCharacterSubmit),
            "musics": await _has(RawMusicSubmit),
            "cps": await _has(RawCPSubmit),
            "papers": await _has(RawPaperSubmit),
            "dojin": await _has(RawDojinSubmit),
        }

    async def get_statistics(self) -> dict[str, int]:
        async def _distinct_count(model) -> int:
            stmt = select(func.count(func.distinct(model.vote_id)))
            return int((await self.session.execute(stmt)).scalar_one() or 0)

        ch = await _distinct_count(RawCharacterSubmit)
        cp = await _distinct_count(RawCPSubmit)
        music = await _distinct_count(RawMusicSubmit)
        paper = await _distinct_count(RawPaperSubmit)
        dojin = await _distinct_count(RawDojinSubmit)

        q_vote = union(
            select(RawCharacterSubmit.vote_id),
            select(RawCPSubmit.vote_id),
            select(RawMusicSubmit.vote_id),
        ).subquery()
        vote_users = (await self.session.execute(select(func.count()).select_from(q_vote))).scalar_one()

        q_user = union(
            select(RawCharacterSubmit.vote_id),
            select(RawCPSubmit.vote_id),
            select(RawMusicSubmit.vote_id),
            select(RawPaperSubmit.vote_id),
        ).subquery()
        all_users = (await self.session.execute(select(func.count()).select_from(q_user))).scalar_one()

        return {
            "num_user": int(all_users or 0),
            "num_finished_paper": int(paper or 0),
            "num_finished_voting": int(vote_users or 0),
            "num_character": ch,
            "num_cp": cp,
            "num_music": music,
            "num_dojin": dojin,
        }
