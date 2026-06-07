"""Submit service layer."""

import json

from src.apps.submit.dao import SubmitDAO
from src.apps.submit.schemas import (
    CharacterSubmitRest,
    CPSubmitRest,
    DojinSubmitRest,
    MusicSubmitRest,
    PaperSubmitRest,
    SubmitMetadata,
    VotingStatistics,
    VotingStatus,
    scrub_metadata,
)


class SubmitValidator:
    """Validator for submit data."""

    # papers_json 上限:防滥用存储。前端真实问卷 ≈ 几 KB,256KB 给足余量。
    PAPERS_JSON_MAX_BYTES = 256 * 1024

    def validate_character(self, data: CharacterSubmitRest) -> CharacterSubmitRest:
        """Validate character submit data."""
        chset: set[str] = set()
        first_set = False
        if len(data.characters) < 1 or len(data.characters) > 8:
            raise ValueError(f"数量{len(data.characters)}不在范围内[1,8]")
        for c in data.characters:
            if (c.reason is not None) and len(c.reason) > 4096:
                raise ValueError("理由过长")
            if bool(c.first):
                if first_set:
                    raise ValueError("多个本命")
                first_set = True
            if c.id in chset:
                raise ValueError(f"{c.id}已存在")
            chset.add(c.id)
        return data

    def validate_music(self, data: MusicSubmitRest) -> MusicSubmitRest:
        """Validate music submit data."""
        chset: set[str] = set()
        first_set = False
        if len(data.music) < 1 or len(data.music) > 12:
            raise ValueError(f"数量{len(data.music)}不在范围内[1,12]")
        for c in data.music:
            if (c.reason is not None) and len(c.reason) > 4096:
                raise ValueError("理由过长")
            if bool(c.first):
                if first_set:
                    raise ValueError("多个本命")
                first_set = True
            if c.id in chset:
                raise ValueError(f"{c.id}已存在")
            chset.add(c.id)
        return data

    def validate_cp(self, data: CPSubmitRest) -> CPSubmitRest:
        """Validate CP submit data."""
        first_set = False
        if len(data.cps) < 1 or len(data.cps) > 4:
            raise ValueError(f"数量{len(data.cps)}不在范围内[1,4]")
        for c in data.cps:
            if (c.reason is not None) and len(c.reason) > 4096:
                raise ValueError("理由过长")
            if bool(c.first):
                if first_set:
                    raise ValueError("多个本命")
                first_set = True
            if c.active is not None and c.active not in {c.id_a, c.id_b, c.id_c}:
                raise ValueError(f"主动方{c.active}不存在")
        return data

    def validate_paper(self, data: PaperSubmitRest) -> PaperSubmitRest:
        """Validate paper submit data.

        papers_json 是不透明业务数据:前端把整棵问卷答案树序列化成一个 JSON
        字符串,结构随问卷内容逐年变化,统计侧也不读这张原始表——所以这里只把
        关「是合法 JSON」+「大小上限」,不校验内部结构(对齐旧 Rust 的透传语义,
        外加大小护栏;详见
        docs/superpowers/specs/2026-06-07-graphql-submit-bridge-design.md §5)。
        """
        if len(data.papers_json.encode("utf-8")) > self.PAPERS_JSON_MAX_BYTES:
            raise ValueError("问卷数据过大")
        try:
            json.loads(data.papers_json)
        except (json.JSONDecodeError, ValueError):
            raise ValueError("问卷数据不是合法 JSON，请重试")
        return data

    def validate_dojin(self, data: DojinSubmitRest) -> DojinSubmitRest:
        """Validate dojin submit data."""
        for item in data.dojins:
            if len(item.author) > 4096:
                raise ValueError("作者名过长")
            if len(item.reason) > 4096:
                raise ValueError("理由过长")
            if len(item.title) > 4096:
                raise ValueError("作品名过长")
            if len(item.url) > 4096:
                raise ValueError("URL过长")
        return data


class SubmitService:
    """Service for submit operations."""

    def __init__(self, submit_dao: SubmitDAO):
        self.submit_dao = submit_dao
        self.validator = SubmitValidator()

    async def submit_character(self, data: CharacterSubmitRest) -> int:
        """Submit character votes."""
        validated = self.validator.validate_character(data)
        row_data = {
            "vote_id": validated.meta.vote_id,
            "attempt": validated.meta.attempt,
            "created_at": validated.meta.created_at,
            "user_ip": validated.meta.user_ip,
            "additional_fingreprint": validated.meta.additional_fingreprint,
            "payload": [x.model_dump() for x in validated.characters],
        }
        return await self.submit_dao.create_character_submit(row_data)

    async def get_character_submit(self, vote_id: str) -> CharacterSubmitRest:
        """Get character submit for a vote ID."""
        row = await self.submit_dao.get_character_submit(vote_id)
        if row is None:
            return CharacterSubmitRest(characters=[], meta=SubmitMetadata())
        return CharacterSubmitRest(
            characters=row["payload"],
            meta=scrub_metadata(
                SubmitMetadata(
                    vote_id=row["vote_id"],
                    attempt=row["attempt"],
                    created_at=row["created_at"],
                    user_ip=row["user_ip"],
                    additional_fingreprint=row["additional_fingreprint"],
                )
            ),
        )

    async def submit_music(self, data: MusicSubmitRest) -> int:
        """Submit music votes."""
        validated = self.validator.validate_music(data)
        row_data = {
            "vote_id": validated.meta.vote_id,
            "attempt": validated.meta.attempt,
            "created_at": validated.meta.created_at,
            "user_ip": validated.meta.user_ip,
            "additional_fingreprint": validated.meta.additional_fingreprint,
            "payload": [x.model_dump() for x in validated.music],
        }
        return await self.submit_dao.create_music_submit(row_data)

    async def get_music_submit(self, vote_id: str) -> MusicSubmitRest:
        """Get music submit for a vote ID."""
        row = await self.submit_dao.get_music_submit(vote_id)
        if row is None:
            return MusicSubmitRest(music=[], meta=SubmitMetadata())
        return MusicSubmitRest(
            music=row["payload"],
            meta=scrub_metadata(
                SubmitMetadata(
                    vote_id=row["vote_id"],
                    attempt=row["attempt"],
                    created_at=row["created_at"],
                    user_ip=row["user_ip"],
                    additional_fingreprint=row["additional_fingreprint"],
                )
            ),
        )

    async def submit_cp(self, data: CPSubmitRest) -> int:
        """Submit CP votes."""
        validated = self.validator.validate_cp(data)
        row_data = {
            "vote_id": validated.meta.vote_id,
            "attempt": validated.meta.attempt,
            "created_at": validated.meta.created_at,
            "user_ip": validated.meta.user_ip,
            "additional_fingreprint": validated.meta.additional_fingreprint,
            "payload": [x.model_dump() for x in validated.cps],
        }
        return await self.submit_dao.create_cp_submit(row_data)

    async def get_cp_submit(self, vote_id: str) -> CPSubmitRest:
        """Get CP submit for a vote ID."""
        row = await self.submit_dao.get_cp_submit(vote_id)
        if row is None:
            return CPSubmitRest(cps=[], meta=SubmitMetadata())
        return CPSubmitRest(
            cps=row["payload"],
            meta=scrub_metadata(
                SubmitMetadata(
                    vote_id=row["vote_id"],
                    attempt=row["attempt"],
                    created_at=row["created_at"],
                    user_ip=row["user_ip"],
                    additional_fingreprint=row["additional_fingreprint"],
                )
            ),
        )

    async def submit_paper(self, data: PaperSubmitRest) -> int:
        """Submit paper votes."""
        validated = self.validator.validate_paper(data)
        row_data = {
            "vote_id": validated.meta.vote_id,
            "attempt": validated.meta.attempt,
            "created_at": validated.meta.created_at,
            "user_ip": validated.meta.user_ip,
            "additional_fingreprint": validated.meta.additional_fingreprint,
            "papers_json": validated.papers_json,
        }
        return await self.submit_dao.create_paper_submit(row_data)

    async def get_paper_submit(self, vote_id: str) -> PaperSubmitRest:
        """Get paper submit for a vote ID."""
        row = await self.submit_dao.get_paper_submit(vote_id)
        if row is None:
            return PaperSubmitRest(papers_json="{}", meta=SubmitMetadata())
        return PaperSubmitRest(
            papers_json=row["papers_json"],
            meta=scrub_metadata(
                SubmitMetadata(
                    vote_id=row["vote_id"],
                    attempt=row["attempt"],
                    created_at=row["created_at"],
                    user_ip=row["user_ip"],
                    additional_fingreprint=row["additional_fingreprint"],
                )
            ),
        )

    async def submit_dojin(self, data: DojinSubmitRest) -> int:
        """Submit dojin votes."""
        validated = self.validator.validate_dojin(data)
        row_data = {
            "vote_id": validated.meta.vote_id,
            "attempt": validated.meta.attempt,
            "created_at": validated.meta.created_at,
            "user_ip": validated.meta.user_ip,
            "additional_fingreprint": validated.meta.additional_fingreprint,
            "payload": [x.model_dump() for x in validated.dojins],
        }
        return await self.submit_dao.create_dojin_submit(row_data)

    async def get_dojin_submit(self, vote_id: str) -> DojinSubmitRest:
        """Get dojin submit for a vote ID."""
        row = await self.submit_dao.get_dojin_submit(vote_id)
        if row is None:
            return DojinSubmitRest(dojins=[], meta=SubmitMetadata())
        return DojinSubmitRest(
            dojins=row["payload"],
            meta=scrub_metadata(
                SubmitMetadata(
                    vote_id=row["vote_id"],
                    attempt=row["attempt"],
                    created_at=row["created_at"],
                    user_ip=row["user_ip"],
                    additional_fingreprint=row["additional_fingreprint"],
                )
            ),
        )

    async def get_voting_status(self, vote_id: str) -> VotingStatus:
        """Get voting status for a vote ID."""
        status = await self.submit_dao.has_submit(vote_id)
        return VotingStatus(**status)

    async def get_voting_statistics(self) -> VotingStatistics:
        """Get voting statistics."""
        stats = await self.submit_dao.get_statistics()
        return VotingStatistics(**stats)
