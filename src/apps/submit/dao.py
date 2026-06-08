"""Submit data access objects."""

from sqlalchemy import delete, desc, func, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.submit.models import (
    RawCharacterSubmit,
    RawCPSubmit,
    RawDojinSubmit,
    RawMusicSubmit,
    RawPaperSubmit,
)


class SubmitDAO:
    """Data access object for submit operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_character_submit(self, data: dict) -> int:
        """Upsert a character submit record (replace existing for same vote_id)."""
        await self.session.execute(
            delete(RawCharacterSubmit).where(
                RawCharacterSubmit.vote_id == data["vote_id"]
            )
        )
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
        """Upsert a music submit record (replace existing for same vote_id)."""
        await self.session.execute(
            delete(RawMusicSubmit).where(
                RawMusicSubmit.vote_id == data["vote_id"]
            )
        )
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
        """Upsert a CP submit record (replace existing for same vote_id)."""
        await self.session.execute(
            delete(RawCPSubmit).where(
                RawCPSubmit.vote_id == data["vote_id"]
            )
        )
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
        """Upsert a paper submit record (replace existing for same vote_id)."""
        await self.session.execute(
            delete(RawPaperSubmit).where(
                RawPaperSubmit.vote_id == data["vote_id"]
            )
        )
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
        """Upsert a dojin submit record (replace existing for same vote_id)."""
        await self.session.execute(
            delete(RawDojinSubmit).where(
                RawDojinSubmit.vote_id == data["vote_id"]
            )
        )
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
        dojin = await _distinct_count(RawDojinSubmit)

        paper = await _distinct_count(RawPaperSubmit)

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
            "num_finished_paper": paper,
            "num_finished_voting": int(vote_users or 0),
            "num_character": ch,
            "num_cp": cp,
            "num_music": music,
            "num_dojin": dojin,
        }

    # ── nomination (dojin review) + questionnaire gate ──────────────────────

    async def has_paper(self, vote_id: str) -> bool:
        """True if the user submitted any questionnaire (weak gate)."""
        stmt = (
            select(RawPaperSubmit.id)
            .where(RawPaperSubmit.vote_id == vote_id)
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none() is not None

    async def nomination_exists(self, vote_id: str, udid: str) -> bool:
        from src.db_model.dojin_nomination import DojinNomination

        stmt = select(DojinNomination.id).where(
            DojinNomination.vote_id == vote_id,
            DojinNomination.udid == udid,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none() is not None

    async def create_nomination(self, row: dict) -> int:
        from src.db_model.dojin_nomination import DojinNomination

        obj = DojinNomination(**row)
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj.id

    async def list_nominations(
        self, status: str | None, page: int, page_size: int
    ) -> tuple[list, int]:
        from src.db_model.dojin_nomination import DojinNomination

        q = select(DojinNomination)
        if status and status != "all":
            q = q.where(DojinNomination.status == status)
        total = (await self.session.execute(
            select(func.count()).select_from(q.subquery())
        )).scalar_one()
        rows = (await self.session.execute(
            q.order_by(desc(DojinNomination.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )).scalars().all()
        return rows, total

    async def set_nomination_status(
        self,
        nom_id: int,
        status: str,
        reviewed_by: str,
        reject_reason: str | None,
    ) -> bool:
        from datetime import datetime, timezone

        from src.db_model.dojin_nomination import DojinNomination

        row = (await self.session.execute(
            select(DojinNomination).where(DojinNomination.id == nom_id)
        )).scalar_one_or_none()
        if row is None:
            return False
        row.status = status
        row.reviewed_by = reviewed_by
        row.reject_reason = reject_reason
        row.reviewed_at = datetime.now(timezone.utc)
        await self.session.commit()
        return True

    async def list_approved_nominations(
        self, page: int, page_size: int
    ) -> list:
        """Approved nominations deduped by udid with nomination_count."""
        from src.db_model.dojin_nomination import DojinNomination

        base = (
            select(
                DojinNomination.udid,
                func.min(DojinNomination.title).label("title"),
                func.min(DojinNomination.url).label("url"),
                func.min(DojinNomination.author).label("author"),
                func.count(func.distinct(DojinNomination.vote_id)).label("cnt"),
            )
            .where(DojinNomination.status == "approved")
            .group_by(DojinNomination.udid)
        )
        rows = (await self.session.execute(
            base.offset((page - 1) * page_size).limit(page_size)
        )).all()
        return rows
