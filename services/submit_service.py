from __future__ import annotations

from sqlalchemy import desc, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from dao.submit_models import (
    CPSubmitRest,
    CharacterSubmitRest,
    DojinSubmitRest,
    MusicSubmitRest,
    PaperSubmitRest,
    SubmitMetadata,
    VotingStatistics,
    VotingStatus,
    scrub_metadata,
)
from db_model.raw_submit import (
    RawCPSubmit,
    RawCharacterSubmit,
    RawDojinSubmit,
    RawMusicSubmit,
    RawPaperSubmit,
)


class SubmitServiceV1:
    async def submit_character(self, db: AsyncSession, verified_data: CharacterSubmitRest) -> int:
        row = RawCharacterSubmit(
            vote_id=verified_data.meta.vote_id,
            attempt=verified_data.meta.attempt,
            created_at=verified_data.meta.created_at,
            user_ip=verified_data.meta.user_ip,
            additional_fingreprint=verified_data.meta.additional_fingreprint,
            payload=[x.model_dump() for x in verified_data.characters],
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row.id

    async def get_submit_character(self, db: AsyncSession, vote_id: str) -> CharacterSubmitRest:
        stmt = select(RawCharacterSubmit).where(RawCharacterSubmit.vote_id == vote_id).order_by(desc(RawCharacterSubmit.created_at)).limit(1)
        row = (await db.execute(stmt)).scalars().first()
        if row is None:
            return CharacterSubmitRest(characters=[], meta=SubmitMetadata())
        return CharacterSubmitRest(characters=row.payload, meta=scrub_metadata(SubmitMetadata(
            vote_id=row.vote_id,
            attempt=row.attempt,
            created_at=row.created_at,
            user_ip=row.user_ip,
            additional_fingreprint=row.additional_fingreprint,
        )))

    async def submit_music(self, db: AsyncSession, verified_data: MusicSubmitRest) -> int:
        row = RawMusicSubmit(
            vote_id=verified_data.meta.vote_id,
            attempt=verified_data.meta.attempt,
            created_at=verified_data.meta.created_at,
            user_ip=verified_data.meta.user_ip,
            additional_fingreprint=verified_data.meta.additional_fingreprint,
            payload=[x.model_dump() for x in verified_data.music],
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row.id

    async def get_submit_music(self, db: AsyncSession, vote_id: str) -> MusicSubmitRest:
        stmt = select(RawMusicSubmit).where(RawMusicSubmit.vote_id == vote_id).order_by(desc(RawMusicSubmit.created_at)).limit(1)
        row = (await db.execute(stmt)).scalars().first()
        if row is None:
            return MusicSubmitRest(music=[], meta=SubmitMetadata())
        return MusicSubmitRest(music=row.payload, meta=scrub_metadata(SubmitMetadata(
            vote_id=row.vote_id,
            attempt=row.attempt,
            created_at=row.created_at,
            user_ip=row.user_ip,
            additional_fingreprint=row.additional_fingreprint,
        )))

    async def submit_cp(self, db: AsyncSession, verified_data: CPSubmitRest) -> int:
        row = RawCPSubmit(
            vote_id=verified_data.meta.vote_id,
            attempt=verified_data.meta.attempt,
            created_at=verified_data.meta.created_at,
            user_ip=verified_data.meta.user_ip,
            additional_fingreprint=verified_data.meta.additional_fingreprint,
            payload=[x.model_dump() for x in verified_data.cps],
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row.id

    async def get_submit_cp(self, db: AsyncSession, vote_id: str) -> CPSubmitRest:
        stmt = select(RawCPSubmit).where(RawCPSubmit.vote_id == vote_id).order_by(desc(RawCPSubmit.created_at)).limit(1)
        row = (await db.execute(stmt)).scalars().first()
        if row is None:
            return CPSubmitRest(cps=[], meta=SubmitMetadata())
        return CPSubmitRest(cps=row.payload, meta=scrub_metadata(SubmitMetadata(
            vote_id=row.vote_id,
            attempt=row.attempt,
            created_at=row.created_at,
            user_ip=row.user_ip,
            additional_fingreprint=row.additional_fingreprint,
        )))

    async def submit_paper(self, db: AsyncSession, verified_data: PaperSubmitRest) -> int:
        row = RawPaperSubmit(
            vote_id=verified_data.meta.vote_id,
            attempt=verified_data.meta.attempt,
            created_at=verified_data.meta.created_at,
            user_ip=verified_data.meta.user_ip,
            additional_fingreprint=verified_data.meta.additional_fingreprint,
            papers_json=verified_data.papers_json,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row.id

    async def get_submit_paper(self, db: AsyncSession, vote_id: str) -> PaperSubmitRest:
        stmt = select(RawPaperSubmit).where(RawPaperSubmit.vote_id == vote_id).order_by(desc(RawPaperSubmit.created_at)).limit(1)
        row = (await db.execute(stmt)).scalars().first()
        if row is None:
            return PaperSubmitRest(papers_json="{}", meta=SubmitMetadata())
        return PaperSubmitRest(papers_json=row.papers_json, meta=scrub_metadata(SubmitMetadata(
            vote_id=row.vote_id,
            attempt=row.attempt,
            created_at=row.created_at,
            user_ip=row.user_ip,
            additional_fingreprint=row.additional_fingreprint,
        )))

    async def submit_dojin(self, db: AsyncSession, verified_data: DojinSubmitRest) -> int:
        row = RawDojinSubmit(
            vote_id=verified_data.meta.vote_id,
            attempt=verified_data.meta.attempt,
            created_at=verified_data.meta.created_at,
            user_ip=verified_data.meta.user_ip,
            additional_fingreprint=verified_data.meta.additional_fingreprint,
            payload=[x.model_dump() for x in verified_data.dojins],
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row.id

    async def get_submit_dojin(self, db: AsyncSession, vote_id: str) -> DojinSubmitRest:
        stmt = select(RawDojinSubmit).where(RawDojinSubmit.vote_id == vote_id).order_by(desc(RawDojinSubmit.created_at)).limit(1)
        row = (await db.execute(stmt)).scalars().first()
        if row is None:
            return DojinSubmitRest(dojins=[], meta=SubmitMetadata())
        return DojinSubmitRest(dojins=row.payload, meta=scrub_metadata(SubmitMetadata(
            vote_id=row.vote_id,
            attempt=row.attempt,
            created_at=row.created_at,
            user_ip=row.user_ip,
            additional_fingreprint=row.additional_fingreprint,
        )))

    async def get_voting_status(self, db: AsyncSession, vote_id: str) -> VotingStatus:
        async def _has(model) -> bool:
            stmt = select(model.id).where(model.vote_id == vote_id).limit(1)
            return (await db.execute(stmt)).scalar_one_or_none() is not None

        return VotingStatus(
            characters=await _has(RawCharacterSubmit),
            musics=await _has(RawMusicSubmit),
            cps=await _has(RawCPSubmit),
            papers=await _has(RawPaperSubmit),
            dojin=await _has(RawDojinSubmit),
        )

    async def get_voting_statistics(self, db: AsyncSession) -> VotingStatistics:
        async def _distinct_count(model) -> int:
            stmt = select(func.count(func.distinct(model.vote_id)))
            return int((await db.execute(stmt)).scalar_one() or 0)

        ch = await _distinct_count(RawCharacterSubmit)
        cp = await _distinct_count(RawCPSubmit)
        music = await _distinct_count(RawMusicSubmit)
        paper = await _distinct_count(RawPaperSubmit)
        dojin = await _distinct_count(RawDojinSubmit)

        # Match Rust semantics: num_user is union(voters in ch/cp/music/paper),
        # num_finished_voting is union(voters in ch/cp/music), num_finished_paper is 0.
        q_vote = (
            select(RawCharacterSubmit.vote_id)
            .union(select(RawCPSubmit.vote_id))
            .union(select(RawMusicSubmit.vote_id))
        )
        vote_users = (await db.execute(select(func.count()).select_from(q_vote.subquery()))).scalar_one()

        q_user = (
            select(RawCharacterSubmit.vote_id)
            .union(select(RawCPSubmit.vote_id))
            .union(select(RawMusicSubmit.vote_id))
            .union(select(RawPaperSubmit.vote_id))
        )
        all_users = (await db.execute(select(func.count()).select_from(q_user.subquery()))).scalar_one()

        return VotingStatistics(
            num_user=int(all_users or 0),
            num_finished_paper=0,
            num_finished_voting=int(vote_users or 0),
            num_character=ch,
            num_cp=cp,
            num_music=music,
            num_dojin=dojin,
        )

