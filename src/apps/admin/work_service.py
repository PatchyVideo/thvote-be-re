"""Work CRUD service for admin panel."""

from __future__ import annotations

import csv
import io
import json
import logging
from typing import Any, Literal, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.admin.schemas import (
    WorkImportError,
    WorkImportItem,
    WorkImportResponse,
    WorkImportUpdate,
)
from src.db_model.work import Work
from src.db_model.voteable import VoteableCharacter, VoteableMusic

_logger = logging.getLogger(__name__)

VALID_TYPES = {"old", "new", "CD", "book", "others"}


def _parse_work_rows(fmt: str, content: str) -> list[Any]:
    text = content.lstrip("\ufeff").strip()
    if not text:
        raise ValueError("导入内容不能为空")
    if fmt == "auto":
        fmt = "json" if text[0] in "[{" else "csv"
    if fmt == "json":
        try:
            rows = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("JSON 格式不正确") from exc
        if not isinstance(rows, list):
            raise ValueError("JSON 必须是作品对象数组")
        return rows
    if fmt != "csv":
        raise ValueError("仅支持 JSON 或 CSV")
    try:
        reader = csv.DictReader(io.StringIO(text), strict=True)
        if not {"name", "type"}.issubset(reader.fieldnames or []):
            raise ValueError("CSV 表头必须包含 name 和 type")
        return list(reader)
    except csv.Error as exc:
        raise ValueError("CSV 格式不正确") from exc


class WorkService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def import_works(
        self, fmt: Literal["auto", "json", "csv"], content: str,
        dry_run: bool = True,
    ) -> WorkImportResponse:
        """Preview all changes; apply the batch only when every row is valid."""
        report = WorkImportResponse(create=[], update=[], unchanged=[], errors=[])
        try:
            rows = _parse_work_rows(fmt, content)
        except ValueError as exc:
            report.errors.append(WorkImportError(row=0, reason=str(exc)))
            return report

        existing = (await self.session.execute(select(Work))).scalars().all()
        by_name = {work.name: work for work in existing}
        seen: set[str] = set()
        for number, raw in enumerate(rows, 1):
            reason = ""
            if not isinstance(raw, dict):
                reason = "每条作品记录必须是对象"
            else:
                name, wtype = raw.get("name"), raw.get("type")
                if not isinstance(name, str) or not name.strip():
                    reason = "作品名不能为空，且必须是字符串"
                elif len(name.strip()) > 255:
                    reason = "作品名不能超过 255 个字符"
                elif name.strip() in seen:
                    reason = f"作品名称重复：{name.strip()}"
                elif not isinstance(wtype, str) or wtype.strip() not in VALID_TYPES:
                    reason = "分类必须为 old、new、CD、book 或 others"
            if reason:
                report.errors.append(WorkImportError(row=number, reason=reason))
                continue
            name, wtype = name.strip(), wtype.strip()
            seen.add(name)
            item = WorkImportItem(name=name, type=wtype)
            target = by_name.get(name)
            if target is None:
                report.create.append(item)
            elif target.type == wtype:
                report.unchanged.append(item)
            else:
                report.update.append(WorkImportUpdate(
                    name=name, type=wtype, previous_type=target.type,
                ))

        if not dry_run and not report.errors:
            for item in report.create:
                self.session.add(Work(name=item.name, type=item.type))
            for item in report.update:
                by_name[item.name].type = item.type
            await self.session.commit()
            report.applied = True
        return report

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
