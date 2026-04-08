"""Submit data access objects."""

from sqlalchemy import desc, select, func, union
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.submit.models import (
    RawCPSubmit,
    RawCharacterSubmit,
    RawDojinSubmit,
    RawMusicSubmit,
    RawPaperSubmit,
)


class SubmitDAO:
    """Data access object for submit operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_character_submit(self, data: dict) -> int:
        """Create a character submit record."""
        row = RawCharacterSubmit(**data)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row.id

    async def get_character_submit(self, vote_id: str) -> dict | None:
        """Get the latest character submit for a vote ID."""
        stmt = (
            select(RawCharacterSubmit)
            .where(RawCharacterSubmit.vote_id == vote_id)
            .order_by(desc(RawCharacterSubmit.created_at))
            .limit(1)
        )
        row = (await self.session.execute(stmt)).scalars().first()
        if row:
            return {
                "payload": row.payload,
                "vote_id": row.vote_id,
                "attempt": row.attempt,
                "created_at": row.created_at,
                "user_ip": row.user_ip,
                "additional_fingreprint": row.additional_fingreprint,
            }
        return None

    async def create_music_submit(self, data: dict) -> int:
        """Create a music submit record."""
        row = RawMusicSubmit(**data)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row.id

    async def get_music_submit(self, vote_id: str) -> dict | None:
        """Get the latest music submit for a vote ID."""
        stmt = (
            select(RawMusicSubmit)
            .where(RawMusicSubmit.vote_id == vote_id)
            .order_by(desc(RawMusicSubmit.created_at))
            .limit(1)
        )
        row = (await self.session.execute(stmt)).scalars().first()
        if row:
            return {
                "payload": row.payload,
                "vote_id": row.vote_id,
                "attempt": row.attempt,
                "created_at": row.created_at,
                "user_ip": row.user_ip,
                "additional_fingreprint": row.additional_fingreprint,
            }
        return None

    async def create_cp_submit(self, data: dict) -> int:
        """Create a CP submit record."""
        row = RawCPSubmit(**data)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row.id

    async def get_cp_submit(self, vote_id: str) -> dict | None:
        """Get the latest CP submit for a vote ID."""
        stmt = (
            select(RawCPSubmit)
            .where(RawCPSubmit.vote_id == vote_id)
            .order_by(desc(RawCPSubmit.created_at))
            .limit(1)
        )
        row = (await self.session.execute(stmt)).scalars().first()
        if row:
            return {
                "payload": row.payload,
                "vote_id": row.vote_id,
                "attempt": row.attempt,
                "created_at": row.created_at,
                "user_ip": row.user_ip,
                "additional_fingreprint": row.additional_fingreprint,
            }
        return None

    async def create_paper_submit(self, data: dict) -> int:
        """Create a paper submit record."""
        row = RawPaperSubmit(**data)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row.id

    async def get_paper_submit(self, vote_id: str) -> dict | None:
        """Get the latest paper submit for a vote ID."""
        stmt = (
            select(RawPaperSubmit)
            .where(RawPaperSubmit.vote_id == vote_id)
            .order_by(desc(RawPaperSubmit.created_at))
            .limit(1)
        )
        row = (await self.session.execute(stmt)).scalars().first()
        if row:
            return {
                "papers_json": row.papers_json,
                "vote_id": row.vote_id,
                "attempt": row.attempt,
                "created_at": row.created_at,
                "user_ip": row.user_ip,
                "additional_fingreprint": row.additional_fingreprint,
            }
        return None

    async def create_dojin_submit(self, data: dict) -> int:
        """Create a dojin submit record."""
        row = RawDojinSubmit(**data)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row.id

    async def get_dojin_submit(self, vote_id: str) -> dict | None:
        """Get the latest dojin submit for a vote ID."""
        stmt = (
            select(RawDojinSubmit)
            .where(RawDojinSubmit.vote_id == vote_id)
            .order_by(desc(RawDojinSubmit.created_at))
            .limit(1)
        )
        row = (await self.session.execute(stmt)).scalars().first()
        if row:
            return {
                "payload": row.payload,
                "vote_id": row.vote_id,
                "attempt": row.attempt,
                "created_at": row.created_at,
                "user_ip": row.user_ip,
                "additional_fingreprint": row.additional_fingreprint,
            }
        return None

    async def has_submit(self, vote_id: str) -> dict[str, bool]:
        """Check if any submits exist for a vote ID."""

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
        """Get voting statistics."""

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
        vote_users = (
            await self.session.execute(select(func.count()).select_from(q_vote))
        ).scalar_one()

        q_user = union(
            select(RawCharacterSubmit.vote_id),
            select(RawCPSubmit.vote_id),
            select(RawMusicSubmit.vote_id),
            select(RawPaperSubmit.vote_id),
        ).subquery()
        all_users = (
            await self.session.execute(select(func.count()).select_from(q_user))
        ).scalar_one()

        return {
            "num_user": int(all_users or 0),
            "num_finished_paper": 0,
            "num_finished_voting": int(vote_users or 0),
            "num_character": ch,
            "num_cp": cp,
            "num_music": music,
            "num_dojin": dojin,
        }
