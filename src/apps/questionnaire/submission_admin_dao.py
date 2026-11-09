"""Database operations scoped to an account, year and complete submission batch."""
from sqlalchemy import Integer, and_, cast, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db_model.questionnaire_def import PaperAnswer


class SubmissionAdminDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_latest(
        self, vote_year: int, vote_id: str | None, invalidated: bool | None,
        page: int, page_size: int,
    ) -> tuple[list[list[PaperAnswer]], int]:
        p = PaperAnswer
        attempt = func.coalesce(p.attempt, 0)
        conditions = [p.vote_year == vote_year]
        if vote_id:
            conditions.append(p.vote_id == vote_id)
        latest = select(
            p.vote_id.label("vote_id"), func.max(attempt).label("attempt"),
        ).where(*conditions).group_by(p.vote_id).subquery()
        latest_join = and_(p.vote_id == latest.c.vote_id, attempt == latest.c.attempt)
        grouped = select(
            p.vote_id.label("vote_id"), func.max(p.created_at).label("created_at"),
            func.max(cast(p.invalidated, Integer)).label("invalidated"),
        ).join(latest, latest_join).where(p.vote_year == vote_year).group_by(p.vote_id)
        summaries = grouped.subquery()
        stmt = select(summaries)
        if invalidated is not None:
            stmt = stmt.where(summaries.c.invalidated == int(invalidated))
        total = (await self.session.execute(
            select(func.count()).select_from(stmt.subquery())
        )).scalar_one()
        selected = (await self.session.execute(
            stmt.order_by(summaries.c.created_at.desc(), summaries.c.vote_id)
            .offset((page - 1) * page_size).limit(page_size)
        )).all()
        if not selected:
            return [], total
        ids = [r.vote_id for r in selected]
        rows = (await self.session.execute(
            select(p).join(latest, latest_join).where(
                p.vote_year == vote_year, p.vote_id.in_(ids),
            ).order_by(p.id)
        )).scalars().all()
        by_vote: dict[str, list[PaperAnswer]] = {vid: [] for vid in ids}
        for row in rows:
            by_vote[row.vote_id].append(row)
        return list(by_vote.values()), total

    async def history(self, vote_id: str, vote_year: int) -> list[PaperAnswer]:
        return list((await self.session.execute(
            select(PaperAnswer).where(
                PaperAnswer.vote_id == vote_id, PaperAnswer.vote_year == vote_year,
            ).order_by(func.coalesce(PaperAnswer.attempt, 0).desc(), PaperAnswer.id)
        )).scalars().all())

    async def set_invalidated(
        self, vote_id: str, vote_year: int, attempt: int, invalidated: bool,
    ) -> int:
        result = await self.session.execute(update(PaperAnswer).where(
            PaperAnswer.vote_id == vote_id, PaperAnswer.vote_year == vote_year,
            func.coalesce(PaperAnswer.attempt, 0) == attempt,
        ).values(invalidated=invalidated))
        await self.session.commit()
        return result.rowcount
