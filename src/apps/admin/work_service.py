"""Work CRUD service for admin panel."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db_model.work import Work
from src.db_model.voteable import VoteableCharacter, VoteableMusic

_logger = logging.getLogger(__name__)

VALID_TYPES = {"old", "new", "CD", "book", "others"}


class WorkService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_works(
        self,
        q: Optional[str] = None,
        wtype: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        base = (
            select(
                Work.id,
                Work.name,
                Work.type,
                Work.created_at,
                func.count(
                    func.distinct(VoteableCharacter.id)
                ).label("character_count"),
                func.count(
                    func.distinct(VoteableMusic.id)
                ).label("music_count"),
            )
            .outerjoin(VoteableCharacter, VoteableCharacter.work_id == Work.id)
            .outerjoin(VoteableMusic, VoteableMusic.work_id == Work.id)
            .group_by(Work.id)
        )

        if q:
            base = base.where(Work.name.ilike(f"%{q}%"))
        if wtype:
            base = base.where(Work.type == wtype)

        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_stmt)).scalar() or 0

        offset = (page - 1) * page_size
        rows = (
            (await self.session.execute(
                base.order_by(Work.name).offset(offset).limit(page_size)
            ))
            .all()
        )

        items = [
            {
                "workId": r[0],
                "name": r[1],
                "type": r[2],
                "createdAt": r[3].isoformat() if r[3] else None,
                "characterCount": r[4] or 0,
                "musicCount": r[5] or 0,
            }
            for r in rows
        ]
        return {"items": items, "total": total}

    async def create_work(self, name: str, wtype: str) -> dict:
        if wtype not in VALID_TYPES:
            raise ValueError(f"Invalid type: {wtype}")
        existing = (
            await self.session.execute(select(Work.id).where(Work.name == name))
        ).scalar()
        if existing:
            raise ValueError(f"Work already exists: {name}")
        w = Work(name=name, type=wtype)
        self.session.add(w)
        await self.session.flush()
        return {"workId": w.id}

    async def update_work(
        self, work_id: int, name: Optional[str], wtype: Optional[str]
    ) -> None:
        w = await self.session.get(Work, work_id)
        if w is None:
            raise LookupError("NOT_FOUND")
        if name is not None:
            w.name = name
        if wtype is not None:
            if wtype not in VALID_TYPES:
                raise ValueError(f"Invalid type: {wtype}")
            w.type = wtype
        await self.session.flush()

    async def delete_work(self, work_id: int) -> None:
        w = await self.session.get(Work, work_id)
        if w is None:
            raise LookupError("NOT_FOUND")
        char_count = (
            await self.session.execute(
                select(func.count()).where(VoteableCharacter.work_id == work_id)
            )
        ).scalar() or 0
        music_count = (
            await self.session.execute(
                select(func.count()).where(VoteableMusic.work_id == work_id)
            )
        ).scalar() or 0
        if char_count > 0 or music_count > 0:
            raise ValueError("WORK_IN_USE")
        await self.session.delete(w)
        await self.session.flush()
