"""Submit resolvers for GraphQL API."""

import uuid
from datetime import datetime, timezone
from typing import Optional

import strawberry

from src.api.graphql.types import (
    CharacterSubmitMutationInput,
    CharacterSubmitResult,
    CPSubmitMutationInput,
    CPSubmitResult,
    DojinSubmitMutationInput,
    DojinSubmitResult,
    MusicSubmitMutationInput,
    MusicSubmitResult,
    PaperSubmitMutationInput,
    SubmitSuccess,
    VotingStatistics,
    VotingStatus,
    pydantic_to_graphql_characters,
    pydantic_to_graphql_cps,
    pydantic_to_graphql_dojins,
    pydantic_to_graphql_meta,
    pydantic_to_graphql_musics,
    pydantic_to_graphql_voting_status,
    pydantic_to_graphql_voting_statistics,
)
from src.apps.submit.schemas import (
    CPSubmitRest,
    CharacterSubmitRest,
    DojinSubmitRest,
    MusicSubmitRest,
    PaperSubmitRest,
    SubmitMetadata,
)
from src.apps.submit.service import SubmitService
from src.common.database import get_db_session
from src.common.middleware.rate_limit import get_redis_client, rate_limit


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


async def _acquire_vote_lock(vote_id: str) -> tuple[str, str]:
    redis_client = await get_redis_client()
    lock_key = f"lock-submit-{vote_id}"
    lock_value = str(uuid.uuid4())
    acquired = await redis_client.set(lock_key, lock_value, nx=True, px=10_000)
    if not acquired:
        raise Exception("SUBMIT_LOCKED")
    return lock_key, lock_value


async def _release_vote_lock(lock_key: str, lock_value: str) -> None:
    redis_client = await get_redis_client()
    current = await redis_client.get(lock_key)
    if current == lock_value:
        await redis_client.delete(lock_key)


def _build_character_rest(input: CharacterSubmitMutationInput) -> CharacterSubmitRest:
    from src.apps.submit.schemas import CharacterSubmit as CharacterSubmitPydantic

    return CharacterSubmitRest(
        characters=[
            CharacterSubmitPydantic(id=c.id, reason=c.reason, first=c.first)
            for c in input.characters
        ],
        meta=SubmitMetadata(
            vote_id=input.meta.vote_id,
            attempt=input.meta.attempt,
            created_at=input.meta.created_at or utcnow(),
            user_ip=input.meta.user_ip,
            additional_fingreprint=input.meta.additional_fingreprint,
        ),
    )


def _build_music_rest(input: MusicSubmitMutationInput) -> MusicSubmitRest:
    from src.apps.submit.schemas import MusicSubmit as MusicSubmitPydantic

    return MusicSubmitRest(
        music=[
            MusicSubmitPydantic(id=m.id, reason=m.reason, first=m.first)
            for m in input.music
        ],
        meta=SubmitMetadata(
            vote_id=input.meta.vote_id,
            attempt=input.meta.attempt,
            created_at=input.meta.created_at or utcnow(),
            user_ip=input.meta.user_ip,
            additional_fingreprint=input.meta.additional_fingreprint,
        ),
    )


def _build_cp_rest(input: CPSubmitMutationInput) -> CPSubmitRest:
    from src.apps.submit.schemas import CPSubmit as CPSubmitPydantic

    return CPSubmitRest(
        cps=[
            CPSubmitPydantic(
                id_a=c.id_a,
                id_b=c.id_b,
                id_c=c.id_c,
                active=c.active,
                first=c.first,
                reason=c.reason,
            )
            for c in input.cps
        ],
        meta=SubmitMetadata(
            vote_id=input.meta.vote_id,
            attempt=input.meta.attempt,
            created_at=input.meta.created_at or utcnow(),
            user_ip=input.meta.user_ip,
            additional_fingreprint=input.meta.additional_fingreprint,
        ),
    )


def _build_paper_rest(input: PaperSubmitMutationInput) -> PaperSubmitRest:
    return PaperSubmitRest(
        papers_json=input.papers_json,
        meta=SubmitMetadata(
            vote_id=input.meta.vote_id,
            attempt=input.meta.attempt,
            created_at=input.meta.created_at or utcnow(),
            user_ip=input.meta.user_ip,
            additional_fingreprint=input.meta.additional_fingreprint,
        ),
    )


def _build_dojin_rest(input: DojinSubmitMutationInput) -> DojinSubmitRest:
    from src.apps.submit.schemas import DojinSubmit as DojinSubmitPydantic

    return DojinSubmitRest(
        dojins=[
            DojinSubmitPydantic(
                dojin_type=d.dojin_type,
                url=d.url,
                title=d.title,
                author=d.author,
                reason=d.reason,
                image_url=d.image_url,
            )
            for d in input.dojins
        ],
        meta=SubmitMetadata(
            vote_id=input.meta.vote_id,
            attempt=input.meta.attempt,
            created_at=input.meta.created_at or utcnow(),
            user_ip=input.meta.user_ip,
            additional_fingreprint=input.meta.additional_fingreprint,
        ),
    )


@strawberry.type
class SubmitQuery:
    @strawberry.field
    async def get_character_submit(self, vote_id: str) -> CharacterSubmitResult:
        async for db in get_db_session():
            service = SubmitService(db)
            data = await service.get_character_submit(vote_id)
            return CharacterSubmitResult(
                characters=pydantic_to_graphql_characters(data.characters),
                meta=pydantic_to_graphql_meta(data.meta),
            )

    @strawberry.field
    async def get_music_submit(self, vote_id: str) -> MusicSubmitResult:
        async for db in get_db_session():
            service = SubmitService(db)
            data = await service.get_music_submit(vote_id)
            return MusicSubmitResult(
                music=pydantic_to_graphql_musics(data.music),
                meta=pydantic_to_graphql_meta(data.meta),
            )

    @strawberry.field
    async def get_cp_submit(self, vote_id: str) -> CPSubmitResult:
        async for db in get_db_session():
            service = SubmitService(db)
            data = await service.get_cp_submit(vote_id)
            return CPSubmitResult(
                cps=pydantic_to_graphql_cps(data.cps),
                meta=pydantic_to_graphql_meta(data.meta),
            )

    @strawberry.field
    async def get_paper_submit(self, vote_id: str) -> Optional[str]:
        async for db in get_db_session():
            service = SubmitService(db)
            data = await service.get_paper_submit(vote_id)
            return (
                data.papers_json
                if data.papers_json and data.papers_json != "{}"
                else None
            )

    @strawberry.field
    async def get_dojin_submit(self, vote_id: str) -> DojinSubmitResult:
        async for db in get_db_session():
            service = SubmitService(db)
            data = await service.get_dojin_submit(vote_id)
            return DojinSubmitResult(
                dojins=pydantic_to_graphql_dojins(data.dojins),
                meta=pydantic_to_graphql_meta(data.meta),
            )

    @strawberry.field
    async def get_voting_status(self, vote_id: str) -> VotingStatus:
        async for db in get_db_session():
            service = SubmitService(db)
            data = await service.get_voting_status(vote_id)
            return pydantic_to_graphql_voting_status(data)

    @strawberry.field
    async def get_voting_statistics(self) -> VotingStatistics:
        async for db in get_db_session():
            service = SubmitService(db)
            data = await service.get_voting_statistics()
            return pydantic_to_graphql_voting_statistics(data)


@strawberry.type
class SubmitMutation:
    @strawberry.mutation
    async def submit_character(
        self, input: CharacterSubmitMutationInput
    ) -> SubmitSuccess:
        redis_client = await get_redis_client()
        await rate_limit(input.meta.vote_id, redis_client)
        lock_key, lock_value = await _acquire_vote_lock(input.meta.vote_id)
        try:
            async for db in get_db_session():
                service = SubmitService(db)
                body = _build_character_rest(input)
                await service.submit_character(body)
        finally:
            await _release_vote_lock(lock_key, lock_value)
        return SubmitSuccess(ok=True)

    @strawberry.mutation
    async def submit_music(self, input: MusicSubmitMutationInput) -> SubmitSuccess:
        redis_client = await get_redis_client()
        await rate_limit(input.meta.vote_id, redis_client)
        lock_key, lock_value = await _acquire_vote_lock(input.meta.vote_id)
        try:
            async for db in get_db_session():
                service = SubmitService(db)
                body = _build_music_rest(input)
                await service.submit_music(body)
        finally:
            await _release_vote_lock(lock_key, lock_value)
        return SubmitSuccess(ok=True)

    @strawberry.mutation
    async def submit_cp(self, input: CPSubmitMutationInput) -> SubmitSuccess:
        redis_client = await get_redis_client()
        await rate_limit(input.meta.vote_id, redis_client)
        lock_key, lock_value = await _acquire_vote_lock(input.meta.vote_id)
        try:
            async for db in get_db_session():
                service = SubmitService(db)
                body = _build_cp_rest(input)
                await service.submit_cp(body)
        finally:
            await _release_vote_lock(lock_key, lock_value)
        return SubmitSuccess(ok=True)

    @strawberry.mutation
    async def submit_paper(self, input: PaperSubmitMutationInput) -> SubmitSuccess:
        redis_client = await get_redis_client()
        await rate_limit(input.meta.vote_id, redis_client)
        lock_key, lock_value = await _acquire_vote_lock(input.meta.vote_id)
        try:
            async for db in get_db_session():
                service = SubmitService(db)
                body = _build_paper_rest(input)
                await service.submit_paper(body)
        finally:
            await _release_vote_lock(lock_key, lock_value)
        return SubmitSuccess(ok=True)

    @strawberry.mutation
    async def submit_dojin(self, input: DojinSubmitMutationInput) -> SubmitSuccess:
        redis_client = await get_redis_client()
        await rate_limit(input.meta.vote_id, redis_client)
        lock_key, lock_value = await _acquire_vote_lock(input.meta.vote_id)
        try:
            async for db in get_db_session():
                service = SubmitService(db)
                body = _build_dojin_rest(input)
                await service.submit_dojin(body)
        finally:
            await _release_vote_lock(lock_key, lock_value)
        return SubmitSuccess(ok=True)
