"""Submit resolvers for GraphQL API."""

from fastapi import HTTPException
import strawberry

from ....common.database.session import SessionLocal
from ....modules.submit.guards import guarded_submit
from ....modules.submit.repository import SubmitRepository
from ....modules.submit.service import SubmitService
from ..types import (
    CPSubmitMutationInput,
    CPSubmitResult,
    CharacterSubmitMutationInput,
    CharacterSubmitResult,
    DojinSubmitMutationInput,
    DojinSubmitResult,
    MusicSubmitMutationInput,
    MusicSubmitResult,
    PaperSubmitMutationInput,
    SubmitSuccess,
    VotingStatistics,
    VotingStatus,
    graphql_to_character_request,
    graphql_to_cp_request,
    graphql_to_dojin_request,
    graphql_to_music_request,
    graphql_to_paper_request,
    pydantic_to_graphql_characters,
    pydantic_to_graphql_cps,
    pydantic_to_graphql_dojins,
    pydantic_to_graphql_meta,
    pydantic_to_graphql_musics,
    pydantic_to_graphql_voting_statistics,
    pydantic_to_graphql_voting_status,
)


async def _use_service(callback):
    async with SessionLocal() as session:
        service = SubmitService(SubmitRepository(session))
        return await callback(service)


async def _guard_graphql_submit(vote_id: str, callback):
    try:
        return await guarded_submit(vote_id, callback)
    except HTTPException as exc:
        raise Exception(exc.detail) from exc


@strawberry.type
class SubmitQuery:
    @strawberry.field
    async def get_character_submit(self, vote_id: str) -> CharacterSubmitResult:
        data = await _use_service(lambda service: service.get_character_submit(vote_id))
        return CharacterSubmitResult(
            characters=pydantic_to_graphql_characters(data),
            meta=pydantic_to_graphql_meta(data.meta),
        )

    @strawberry.field
    async def get_music_submit(self, vote_id: str) -> MusicSubmitResult:
        data = await _use_service(lambda service: service.get_music_submit(vote_id))
        return MusicSubmitResult(
            music=pydantic_to_graphql_musics(data),
            meta=pydantic_to_graphql_meta(data.meta),
        )

    @strawberry.field
    async def get_cp_submit(self, vote_id: str) -> CPSubmitResult:
        data = await _use_service(lambda service: service.get_cp_submit(vote_id))
        return CPSubmitResult(
            cps=pydantic_to_graphql_cps(data),
            meta=pydantic_to_graphql_meta(data.meta),
        )

    @strawberry.field
    async def get_paper_submit(self, vote_id: str) -> str | None:
        data = await _use_service(lambda service: service.get_paper_submit(vote_id))
        return data.papers_json if data.papers_json and data.papers_json != "{}" else None

    @strawberry.field
    async def get_dojin_submit(self, vote_id: str) -> DojinSubmitResult:
        data = await _use_service(lambda service: service.get_dojin_submit(vote_id))
        return DojinSubmitResult(
            dojins=pydantic_to_graphql_dojins(data),
            meta=pydantic_to_graphql_meta(data.meta),
        )

    @strawberry.field
    async def get_voting_status(self, vote_id: str) -> VotingStatus:
        data = await _use_service(lambda service: service.get_voting_status(vote_id))
        return pydantic_to_graphql_voting_status(data)

    @strawberry.field
    async def get_voting_statistics(self) -> VotingStatistics:
        data = await _use_service(lambda service: service.get_voting_statistics())
        return pydantic_to_graphql_voting_statistics(data)


@strawberry.type
class SubmitMutation:
    @strawberry.mutation
    async def submit_character(self, input: CharacterSubmitMutationInput) -> SubmitSuccess:
        await _guard_graphql_submit(
            input.meta.vote_id,
            lambda: _use_service(lambda service: service.submit_character(graphql_to_character_request(input))),
        )
        return SubmitSuccess(ok=True)

    @strawberry.mutation
    async def submit_music(self, input: MusicSubmitMutationInput) -> SubmitSuccess:
        await _guard_graphql_submit(
            input.meta.vote_id,
            lambda: _use_service(lambda service: service.submit_music(graphql_to_music_request(input))),
        )
        return SubmitSuccess(ok=True)

    @strawberry.mutation
    async def submit_cp(self, input: CPSubmitMutationInput) -> SubmitSuccess:
        await _guard_graphql_submit(
            input.meta.vote_id,
            lambda: _use_service(lambda service: service.submit_cp(graphql_to_cp_request(input))),
        )
        return SubmitSuccess(ok=True)

    @strawberry.mutation
    async def submit_paper(self, input: PaperSubmitMutationInput) -> SubmitSuccess:
        await _guard_graphql_submit(
            input.meta.vote_id,
            lambda: _use_service(lambda service: service.submit_paper(graphql_to_paper_request(input))),
        )
        return SubmitSuccess(ok=True)

    @strawberry.mutation
    async def submit_dojin(self, input: DojinSubmitMutationInput) -> SubmitSuccess:
        await _guard_graphql_submit(
            input.meta.vote_id,
            lambda: _use_service(lambda service: service.submit_dojin(graphql_to_dojin_request(input))),
        )
        return SubmitSuccess(ok=True)
