from __future__ import annotations

from datetime import datetime

import strawberry

from ...models.dto.submit import (
    CPSubmitRequest,
    CharacterSubmitRequest,
    CPVoteItem,
    CharacterVoteItem,
    DojinSubmitRequest,
    DojinVoteItem,
    MusicSubmitRequest,
    MusicVoteItem,
    PaperSubmitRequest,
    SubmitMetadata as SubmitMetadataDTO,
    VotingStatistics as VotingStatisticsDTO,
    VotingStatus as VotingStatusDTO,
)


@strawberry.type
class SubmitMetadata:
    vote_id: str
    attempt: int | None = None
    created_at: datetime
    user_ip: str
    additional_fingreprint: str | None = None


@strawberry.type
class CharacterSubmit:
    id: str
    reason: str | None = None
    first: bool | None = None


@strawberry.type
class MusicSubmit:
    id: str
    reason: str | None = None
    first: bool | None = None


@strawberry.type
class CPSubmit:
    id_a: str
    id_b: str
    id_c: str | None = None
    active: str | None = None
    first: bool | None = None
    reason: str | None = None


@strawberry.type
class DojinSubmit:
    dojin_type: str
    url: str
    title: str
    author: str
    reason: str
    image_url: str | None = None


@strawberry.type
class CharacterSubmitResult:
    characters: list[CharacterSubmit]
    meta: SubmitMetadata


@strawberry.type
class MusicSubmitResult:
    music: list[MusicSubmit]
    meta: SubmitMetadata


@strawberry.type
class CPSubmitResult:
    cps: list[CPSubmit]
    meta: SubmitMetadata


@strawberry.type
class DojinSubmitResult:
    dojins: list[DojinSubmit]
    meta: SubmitMetadata


@strawberry.type
class VotingStatus:
    characters: bool
    musics: bool
    cps: bool
    papers: bool
    dojin: bool


@strawberry.type
class VotingStatistics:
    num_user: int
    num_finished_paper: int
    num_finished_voting: int
    num_character: int
    num_cp: int
    num_music: int
    num_dojin: int


@strawberry.type
class SubmitSuccess:
    ok: bool = True


@strawberry.input
class SubmitMetadataInput:
    vote_id: str
    attempt: int | None = None
    created_at: datetime | None = None
    user_ip: str = "<unknown>"
    additional_fingreprint: str | None = None


@strawberry.input
class CharacterSubmitInput:
    id: str
    reason: str | None = None
    first: bool | None = None


@strawberry.input
class MusicSubmitInput:
    id: str
    reason: str | None = None
    first: bool | None = None


@strawberry.input
class CPSubmitInput:
    id_a: str
    id_b: str
    id_c: str | None = None
    active: str | None = None
    first: bool | None = None
    reason: str | None = None


@strawberry.input
class DojinSubmitInput:
    dojin_type: str
    url: str
    title: str
    author: str
    reason: str
    image_url: str | None = None


@strawberry.input
class CharacterSubmitMutationInput:
    characters: list[CharacterSubmitInput]
    meta: SubmitMetadataInput


@strawberry.input
class MusicSubmitMutationInput:
    music: list[MusicSubmitInput]
    meta: SubmitMetadataInput


@strawberry.input
class CPSubmitMutationInput:
    cps: list[CPSubmitInput]
    meta: SubmitMetadataInput


@strawberry.input
class PaperSubmitMutationInput:
    papers_json: str
    meta: SubmitMetadataInput


@strawberry.input
class DojinSubmitMutationInput:
    dojins: list[DojinSubmitInput]
    meta: SubmitMetadataInput


def pydantic_to_graphql_meta(meta: SubmitMetadataDTO) -> SubmitMetadata:
    return SubmitMetadata(
        vote_id=meta.vote_id,
        attempt=meta.attempt,
        created_at=meta.created_at,
        user_ip=meta.user_ip,
        additional_fingreprint=meta.additional_fingerprint,
    )


def pydantic_to_graphql_characters(data: CharacterSubmitRequest) -> list[CharacterSubmit]:
    return [CharacterSubmit(id=item.id, reason=item.reason, first=item.first) for item in data.characters]


def pydantic_to_graphql_musics(data: MusicSubmitRequest) -> list[MusicSubmit]:
    return [MusicSubmit(id=item.id, reason=item.reason, first=item.first) for item in data.music]


def pydantic_to_graphql_cps(data: CPSubmitRequest) -> list[CPSubmit]:
    return [
        CPSubmit(
            id_a=item.id_a,
            id_b=item.id_b,
            id_c=item.id_c,
            active=item.active,
            first=item.first,
            reason=item.reason,
        )
        for item in data.cps
    ]


def pydantic_to_graphql_dojins(data: DojinSubmitRequest) -> list[DojinSubmit]:
    return [
        DojinSubmit(
            dojin_type=item.dojin_type,
            url=item.url,
            title=item.title,
            author=item.author,
            reason=item.reason,
            image_url=item.image_url,
        )
        for item in data.dojins
    ]


def pydantic_to_graphql_voting_status(status: VotingStatusDTO) -> VotingStatus:
    return VotingStatus(
        characters=status.characters,
        musics=status.musics,
        cps=status.cps,
        papers=status.papers,
        dojin=status.dojin,
    )


def pydantic_to_graphql_voting_statistics(stats: VotingStatisticsDTO) -> VotingStatistics:
    return VotingStatistics(
        num_user=stats.num_user,
        num_finished_paper=stats.num_finished_paper,
        num_finished_voting=stats.num_finished_voting,
        num_character=stats.num_character,
        num_cp=stats.num_cp,
        num_music=stats.num_music,
        num_dojin=stats.num_dojin,
    )


def graphql_to_metadata(meta: SubmitMetadataInput) -> SubmitMetadataDTO:
    return SubmitMetadataDTO(
        vote_id=meta.vote_id,
        attempt=meta.attempt,
        created_at=meta.created_at or SubmitMetadataDTO().created_at,
        user_ip=meta.user_ip,
        additional_fingerprint=meta.additional_fingreprint,
    )


def graphql_to_character_request(input_data: CharacterSubmitMutationInput) -> CharacterSubmitRequest:
    return CharacterSubmitRequest(
        characters=[
            CharacterVoteItem(id=item.id, reason=item.reason, first=item.first)
            for item in input_data.characters
        ],
        meta=graphql_to_metadata(input_data.meta),
    )


def graphql_to_music_request(input_data: MusicSubmitMutationInput) -> MusicSubmitRequest:
    return MusicSubmitRequest(
        music=[
            MusicVoteItem(id=item.id, reason=item.reason, first=item.first)
            for item in input_data.music
        ],
        meta=graphql_to_metadata(input_data.meta),
    )


def graphql_to_cp_request(input_data: CPSubmitMutationInput) -> CPSubmitRequest:
    return CPSubmitRequest(
        cps=[
            CPVoteItem(
                id_a=item.id_a,
                id_b=item.id_b,
                id_c=item.id_c,
                active=item.active,
                first=item.first,
                reason=item.reason,
            )
            for item in input_data.cps
        ],
        meta=graphql_to_metadata(input_data.meta),
    )


def graphql_to_paper_request(input_data: PaperSubmitMutationInput) -> PaperSubmitRequest:
    return PaperSubmitRequest(
        papers_json=input_data.papers_json,
        meta=graphql_to_metadata(input_data.meta),
    )


def graphql_to_dojin_request(input_data: DojinSubmitMutationInput) -> DojinSubmitRequest:
    return DojinSubmitRequest(
        dojins=[
            DojinVoteItem(
                dojin_type=item.dojin_type,
                url=item.url,
                title=item.title,
                author=item.author,
                reason=item.reason,
                image_url=item.image_url,
            )
            for item in input_data.dojins
        ],
        meta=graphql_to_metadata(input_data.meta),
    )
