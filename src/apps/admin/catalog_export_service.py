"""Export complete business catalogs in the voteable import field format."""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db_model.voteable import VoteableCharacter, VoteableMusic
from src.db_model.work import Work

CatalogCategory = Literal["work", "character", "music"]


class CatalogExportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def export(self, category: CatalogCategory) -> list[dict[str, Any]]:
        if category == "work":
            statement = select(Work.name, Work.type).order_by(Work.name, Work.id)
        else:
            model = {
                "character": VoteableCharacter,
                "music": VoteableMusic,
            }[category]
            columns = [
                model.name, model.name_jp, model.type, model.first_appearance,
                model.aliases, model.old_id, model.image_url,
                Work.name.label("work"), Work.type.label("work_type"),
            ]
            if category == "music":
                columns.extend([model.music_url, model.include])
            statement = (
                select(*columns)
                .outerjoin(Work, model.work_id == Work.id)
                .order_by(model.name, model.id)
            )
        rows = (await self.session.execute(statement)).mappings().all()
        return [dict(row) for row in rows]
