"""Service layer for submit operations."""

from ...models.dto.submit import (
    CPSubmitRequest,
    CharacterSubmitRequest,
    DojinSubmitRequest,
    MusicSubmitRequest,
    PaperSubmitRequest,
    SubmitMetadata,
    VotingStatistics,
    VotingStatus,
    scrub_metadata,
)
from ...common.errors import ValidationError
from .repository import SubmitRepository


class SubmitValidator:
    """Validator for submit payloads."""

    def validate_character(self, data: CharacterSubmitRequest) -> CharacterSubmitRequest:
        ids: set[str] = set()
        first_set = False
        if len(data.characters) < 1 or len(data.characters) > 8:
            raise ValidationError(f"数量{len(data.characters)}不在范围内[1,8]")
        for item in data.characters:
            if item.reason is not None and len(item.reason) > 4096:
                raise ValidationError("理由过长")
            if bool(item.first):
                if first_set:
                    raise ValidationError("多个本命")
                first_set = True
            if item.id in ids:
                raise ValidationError(f"{item.id}已存在")
            ids.add(item.id)
        return data

    def validate_music(self, data: MusicSubmitRequest) -> MusicSubmitRequest:
        ids: set[str] = set()
        first_set = False
        if len(data.music) < 1 or len(data.music) > 12:
            raise ValidationError(f"数量{len(data.music)}不在范围内[1,12]")
        for item in data.music:
            if item.reason is not None and len(item.reason) > 4096:
                raise ValidationError("理由过长")
            if bool(item.first):
                if first_set:
                    raise ValidationError("多个本命")
                first_set = True
            if item.id in ids:
                raise ValidationError(f"{item.id}已存在")
            ids.add(item.id)
        return data

    def validate_cp(self, data: CPSubmitRequest) -> CPSubmitRequest:
        first_set = False
        if len(data.cps) < 1 or len(data.cps) > 4:
            raise ValidationError(f"数量{len(data.cps)}不在范围内[1,4]")
        for item in data.cps:
            if item.reason is not None and len(item.reason) > 4096:
                raise ValidationError("理由过长")
            if bool(item.first):
                if first_set:
                    raise ValidationError("多个本命")
                first_set = True
            if item.active is not None and item.active not in {item.id_a, item.id_b, item.id_c}:
                raise ValidationError(f"主动方{item.active}不存在")
        return data

    def validate_paper(self, data: PaperSubmitRequest) -> PaperSubmitRequest:
        return data

    def validate_dojin(self, data: DojinSubmitRequest) -> DojinSubmitRequest:
        for item in data.dojins:
            if len(item.author) > 4096:
                raise ValidationError("作者名过长")
            if len(item.reason) > 4096:
                raise ValidationError("理由过长")
            if len(item.title) > 4096:
                raise ValidationError("作品名过长")
            if len(item.url) > 4096:
                raise ValidationError("URL过长")
        return data


class SubmitService:
    """Service for raw submit creation and retrieval."""

    def __init__(self, repository: SubmitRepository) -> None:
        self.repository = repository
        self.validator = SubmitValidator()

    async def submit_character(self, data: CharacterSubmitRequest) -> int:
        validated = self.validator.validate_character(data)
        row_data = {
            "vote_id": validated.meta.vote_id,
            "attempt": validated.meta.attempt,
            "created_at": validated.meta.created_at,
            "user_ip": validated.meta.user_ip,
            "additional_fingerprint": validated.meta.additional_fingerprint,
            "payload": [item.model_dump() for item in validated.characters],
        }
        return await self.repository.create_character_submit(row_data)

    async def get_character_submit(self, vote_id: str) -> CharacterSubmitRequest:
        row = await self.repository.get_character_submit(vote_id)
        if row is None:
            return CharacterSubmitRequest(characters=[], meta=SubmitMetadata())
        return CharacterSubmitRequest(
            characters=row["payload"],
            meta=scrub_metadata(
                SubmitMetadata(
                    vote_id=row["vote_id"],
                    attempt=row["attempt"],
                    created_at=row["created_at"],
                    user_ip=row["user_ip"],
                    additional_fingerprint=row["additional_fingerprint"],
                )
            ),
        )

    async def submit_music(self, data: MusicSubmitRequest) -> int:
        validated = self.validator.validate_music(data)
        row_data = {
            "vote_id": validated.meta.vote_id,
            "attempt": validated.meta.attempt,
            "created_at": validated.meta.created_at,
            "user_ip": validated.meta.user_ip,
            "additional_fingerprint": validated.meta.additional_fingerprint,
            "payload": [item.model_dump() for item in validated.music],
        }
        return await self.repository.create_music_submit(row_data)

    async def get_music_submit(self, vote_id: str) -> MusicSubmitRequest:
        row = await self.repository.get_music_submit(vote_id)
        if row is None:
            return MusicSubmitRequest(music=[], meta=SubmitMetadata())
        return MusicSubmitRequest(
            music=row["payload"],
            meta=scrub_metadata(
                SubmitMetadata(
                    vote_id=row["vote_id"],
                    attempt=row["attempt"],
                    created_at=row["created_at"],
                    user_ip=row["user_ip"],
                    additional_fingerprint=row["additional_fingerprint"],
                )
            ),
        )

    async def submit_cp(self, data: CPSubmitRequest) -> int:
        validated = self.validator.validate_cp(data)
        row_data = {
            "vote_id": validated.meta.vote_id,
            "attempt": validated.meta.attempt,
            "created_at": validated.meta.created_at,
            "user_ip": validated.meta.user_ip,
            "additional_fingerprint": validated.meta.additional_fingerprint,
            "payload": [item.model_dump() for item in validated.cps],
        }
        return await self.repository.create_cp_submit(row_data)

    async def get_cp_submit(self, vote_id: str) -> CPSubmitRequest:
        row = await self.repository.get_cp_submit(vote_id)
        if row is None:
            return CPSubmitRequest(cps=[], meta=SubmitMetadata())
        return CPSubmitRequest(
            cps=row["payload"],
            meta=scrub_metadata(
                SubmitMetadata(
                    vote_id=row["vote_id"],
                    attempt=row["attempt"],
                    created_at=row["created_at"],
                    user_ip=row["user_ip"],
                    additional_fingerprint=row["additional_fingerprint"],
                )
            ),
        )

    async def submit_paper(self, data: PaperSubmitRequest) -> int:
        validated = self.validator.validate_paper(data)
        row_data = {
            "vote_id": validated.meta.vote_id,
            "attempt": validated.meta.attempt,
            "created_at": validated.meta.created_at,
            "user_ip": validated.meta.user_ip,
            "additional_fingerprint": validated.meta.additional_fingerprint,
            "papers_json": validated.papers_json,
        }
        return await self.repository.create_paper_submit(row_data)

    async def get_paper_submit(self, vote_id: str) -> PaperSubmitRequest:
        row = await self.repository.get_paper_submit(vote_id)
        if row is None:
            return PaperSubmitRequest(papers_json="{}", meta=SubmitMetadata())
        return PaperSubmitRequest(
            papers_json=row["papers_json"],
            meta=scrub_metadata(
                SubmitMetadata(
                    vote_id=row["vote_id"],
                    attempt=row["attempt"],
                    created_at=row["created_at"],
                    user_ip=row["user_ip"],
                    additional_fingerprint=row["additional_fingerprint"],
                )
            ),
        )

    async def submit_dojin(self, data: DojinSubmitRequest) -> int:
        validated = self.validator.validate_dojin(data)
        row_data = {
            "vote_id": validated.meta.vote_id,
            "attempt": validated.meta.attempt,
            "created_at": validated.meta.created_at,
            "user_ip": validated.meta.user_ip,
            "additional_fingerprint": validated.meta.additional_fingerprint,
            "payload": [item.model_dump() for item in validated.dojins],
        }
        return await self.repository.create_dojin_submit(row_data)

    async def get_dojin_submit(self, vote_id: str) -> DojinSubmitRequest:
        row = await self.repository.get_dojin_submit(vote_id)
        if row is None:
            return DojinSubmitRequest(dojins=[], meta=SubmitMetadata())
        return DojinSubmitRequest(
            dojins=row["payload"],
            meta=scrub_metadata(
                SubmitMetadata(
                    vote_id=row["vote_id"],
                    attempt=row["attempt"],
                    created_at=row["created_at"],
                    user_ip=row["user_ip"],
                    additional_fingerprint=row["additional_fingerprint"],
                )
            ),
        )

    async def get_voting_status(self, vote_id: str) -> VotingStatus:
        return VotingStatus(**(await self.repository.has_submit(vote_id)))

    async def get_voting_statistics(self) -> VotingStatistics:
        return VotingStatistics(**(await self.repository.get_statistics()))
