from __future__ import annotations

from datetime import datetime
from typing import Optional

import strawberry

from src.apps.submit.schemas import (
    CharacterSubmit as CharacterSubmitPydantic,
    CPSubmit as CPSubmitPydantic,
    DojinSubmit as DojinSubmitPydantic,
    MusicSubmit as MusicSubmitPydantic,
    SubmitMetadata as SubmitMetadataPydantic,
    VotingStatus as VotingStatusPydantic,
    VotingStatistics as VotingStatisticsPydantic,
)


@strawberry.type
class SubmitMetadata:
    vote_id: str
    attempt: Optional[int] = None
    created_at: datetime
    user_ip: str
    additional_fingreprint: Optional[str] = None


@strawberry.type
class CharacterSubmit:
    id: str
    reason: Optional[str] = None
    first: Optional[bool] = None


@strawberry.type
class MusicSubmit:
    id: str
    reason: Optional[str] = None
    first: Optional[bool] = None


@strawberry.type
class CPSubmit:
    id_a: str
    id_b: str
    id_c: Optional[str] = None
    active: Optional[str] = None
    first: Optional[bool] = None
    reason: Optional[str] = None


@strawberry.type
class DojinSubmit:
    dojin_type: str
    url: str
    title: str
    author: str
    reason: str
    image_url: Optional[str] = None


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
    attempt: Optional[int] = None
    created_at: Optional[datetime] = None
    user_ip: str = "<unknown>"
    additional_fingreprint: Optional[str] = None


@strawberry.input
class CharacterSubmitInput:
    id: str
    reason: Optional[str] = None
    first: Optional[bool] = None


@strawberry.input
class MusicSubmitInput:
    id: str
    reason: Optional[str] = None
    first: Optional[bool] = None


@strawberry.input
class CPSubmitInput:
    id_a: str
    id_b: str
    id_c: Optional[str] = None
    active: Optional[str] = None
    first: Optional[bool] = None
    reason: Optional[str] = None


@strawberry.input
class DojinSubmitInput:
    dojin_type: str
    url: str
    title: str
    author: str
    reason: str
    image_url: Optional[str] = None


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


def pydantic_to_graphql_meta(meta: SubmitMetadataPydantic) -> SubmitMetadata:
    return SubmitMetadata(
        vote_id=meta.vote_id,
        attempt=meta.attempt,
        created_at=meta.created_at,
        user_ip=meta.user_ip,
        additional_fingreprint=meta.additional_fingreprint,
    )


def pydantic_to_graphql_characters(chars: list[CharacterSubmitPydantic]) -> list[CharacterSubmit]:
    return [CharacterSubmit(id=c.id, reason=c.reason, first=c.first) for c in chars]


def pydantic_to_graphql_musics(musics: list[MusicSubmitPydantic]) -> list[MusicSubmit]:
    return [MusicSubmit(id=m.id, reason=m.reason, first=m.first) for m in musics]


def pydantic_to_graphql_cps(cps: list[CPSubmitPydantic]) -> list[CPSubmit]:
    return [CPSubmit(id_a=c.id_a, id_b=c.id_b, id_c=c.id_c, active=c.active, first=c.first, reason=c.reason) for c in cps]


def pydantic_to_graphql_dojins(dojins: list[DojinSubmitPydantic]) -> list[DojinSubmit]:
    return [DojinSubmit(
        dojin_type=d.dojin_type, url=d.url, title=d.title,
        author=d.author, reason=d.reason, image_url=d.image_url
    ) for d in dojins]


def pydantic_to_graphql_voting_status(status: VotingStatusPydantic) -> VotingStatus:
    return VotingStatus(
        characters=status.characters,
        musics=status.musics,
        cps=status.cps,
        papers=status.papers,
        dojin=status.dojin,
    )


def pydantic_to_graphql_voting_statistics(stats: VotingStatisticsPydantic) -> VotingStatistics:
    return VotingStatistics(
        num_user=stats.num_user,
        num_finished_paper=stats.num_finished_paper,
        num_finished_voting=stats.num_finished_voting,
        num_character=stats.num_character,
        num_cp=stats.num_cp,
        num_music=stats.num_music,
        num_dojin=stats.num_dojin,
    )
