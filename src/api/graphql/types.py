from __future__ import annotations

from datetime import datetime
from typing import Optional

import strawberry
from strawberry.scalars import JSON  # noqa: F401  — re-exported for resolvers

from src.apps.submit.schemas import CharacterSubmit as CharacterSubmitPydantic
from src.apps.submit.schemas import CPSubmit as CPSubmitPydantic
from src.apps.submit.schemas import DojinSubmit as DojinSubmitPydantic
from src.apps.submit.schemas import MusicSubmit as MusicSubmitPydantic
from src.apps.submit.schemas import SubmitMetadata as SubmitMetadataPydantic
from src.apps.submit.schemas import VotingStatistics as VotingStatisticsPydantic
from src.apps.submit.schemas import VotingStatus as VotingStatusPydantic

# ── Custom scalars ────────────────────────────────────────────────────

DateTimeUtc = strawberry.scalar(
    datetime,
    name="DateTimeUtc",
    description="UTC datetime in ISO 8601 format",
    serialize=lambda v: v.isoformat(),
    parse_value=lambda v: datetime.fromisoformat(v.replace("Z", "+00:00")),
)

# ── Result types (align with Rust gateway result_query.rs) ────────────


@strawberry.type
class VotingTrendItem:
    hrs: int
    cnt: int


@strawberry.type
class RankingGlobal:
    total_unique_items: int
    total_first: int
    total_votes: int
    average_votes_per_item: float
    median_votes_per_item: float


@strawberry.type
class RankingEntry:
    rank: int
    rank_last_1: int
    rank_last_2: int
    display_rank: int
    name: str
    vote_count: int
    vote_count_last_1: int
    vote_count_last_2: int
    first_vote_count: int
    first_vote_count_last_1: int
    first_vote_count_last_2: int
    first_vote_percentage: float
    first_vote_percentage_last_1: float
    first_vote_percentage_last_2: float
    first_vote_count_weighted: int
    character_type: str
    character_origin: str
    first_appearance: str
    album: Optional[str]
    name_jpn: str
    vote_percentage: float
    vote_percentage_last_1: float
    vote_percentage_last_2: float
    first_percentage: float
    male_vote_count: int
    male_percentage_per_char: float
    male_percentage_per_total: float
    female_vote_count: int
    female_percentage_per_char: float
    female_percentage_per_total: float
    trend: list[VotingTrendItem]
    trend_first: list[VotingTrendItem]
    reasons: list[str]
    num_reasons: int


@strawberry.type
class CPItem:
    a: str
    b: str
    c: Optional[str]


@strawberry.type
class CPRankingEntry:
    rank: int
    display_rank: int
    cp: CPItem
    a_active: float
    b_active: float
    c_active: float
    none_active: float
    vote_count: int
    first_vote_count: int
    first_vote_percentage: float
    first_vote_count_weighted: int
    vote_percentage: float
    first_percentage: float
    male_vote_count: int
    male_percentage_per_char: float
    male_percentage_per_total: float
    female_vote_count: int
    female_percentage_per_char: float
    female_percentage_per_total: float
    trend: list[VotingTrendItem]
    trend_first: list[VotingTrendItem]
    reasons: list[str]
    num_reasons: int


@strawberry.type
class CharacterOrMusicRanking:
    entries: list[RankingEntry]
    global_: RankingGlobal = strawberry.field(name="global")


@strawberry.type
class CPRanking:
    entries: list[CPRankingEntry]
    global_: RankingGlobal = strawberry.field(name="global")


@strawberry.type
class Trends:
    trend: list[VotingTrendItem]
    trend_first: list[VotingTrendItem]


@strawberry.type
class ResultGlobalStats:
    vote_year: int
    num_vote: int
    num_char: int
    num_music: int
    num_cp: int
    num_doujin: int
    num_male: int
    num_female: int


@strawberry.type
class CompletionRateItem:
    name: str
    rate: float
    num_complete: int
    total: int


@strawberry.type
class CompletionRate:
    vote_year: int
    items: list[CompletionRateItem]


@strawberry.type
class CachedQuestionAnswerItem:
    aid: str
    total_votes: int
    male_votes: int
    female_votes: int


@strawberry.type
class CachedQuestionItem:
    question_id: str
    answers_cat: list[CachedQuestionAnswerItem]
    answers_str: list[str]
    total_answers: int
    total_male: int
    total_female: int


@strawberry.type
class QueryQuestionnaireResponse:
    entries: list[CachedQuestionItem]


@strawberry.type
class CovoteItem:
    a: str
    b: str
    cs: float
    mi: float
    cv: float
    m00: int
    m01: int
    m10: int
    m11: int


@strawberry.type
class CovoteResponse:
    items: list[CovoteItem]


# ── User types ────────────────────────────────────────────────────────


@strawberry.type
class UserGQLType:
    username: Optional[str]
    pfp: Optional[str]
    password: bool
    phone: Optional[str]
    email: Optional[str]
    thbwiki: bool
    patchyvideo: bool
    created_at: datetime


@strawberry.type
class LoginResult:
    user: UserGQLType
    session_token: str
    vote_token: str


# ── Submit types ──────────────────────────────────────────────────────


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


# ── Submit input types (aligned with frontend GQL names) ─────────────


@strawberry.input
class CharacterItemInput:
    id: str
    reason: Optional[str] = None
    first: Optional[bool] = None


@strawberry.input
class MusicItemInput:
    id: str
    reason: Optional[str] = None
    first: Optional[bool] = None


@strawberry.input
class CPItemInput:
    id_a: str
    id_b: str
    id_c: Optional[str] = None
    active: Optional[str] = None
    first: Optional[bool] = None
    reason: Optional[str] = None


@strawberry.input
class DojinItemInput:
    dojin_type: str
    url: str
    title: str
    author: str
    reason: str
    image_url: Optional[str] = None


@strawberry.input
class CharacterSubmitGQL:
    vote_token: str
    characters: list[CharacterItemInput]


@strawberry.input
class MusicSubmitGQL:
    vote_token: str
    musics: list[MusicItemInput]


@strawberry.input
class CPSubmitGQL:
    vote_token: str
    cps: list[CPItemInput]


@strawberry.input
class PaperSubmitGQL:
    vote_token: str
    paper_json: str


@strawberry.input
class DojinSubmitGQL:
    vote_token: str
    dojins: list[DojinItemInput]


def pydantic_to_graphql_meta(meta: SubmitMetadataPydantic) -> SubmitMetadata:
    return SubmitMetadata(
        vote_id=meta.vote_id,
        attempt=meta.attempt,
        created_at=meta.created_at,
        user_ip=meta.user_ip,
        additional_fingreprint=meta.additional_fingreprint,
    )


def pydantic_to_graphql_characters(
    chars: list[CharacterSubmitPydantic],
) -> list[CharacterSubmit]:
    return [CharacterSubmit(id=c.id, reason=c.reason, first=c.first) for c in chars]


def pydantic_to_graphql_musics(musics: list[MusicSubmitPydantic]) -> list[MusicSubmit]:
    return [MusicSubmit(id=m.id, reason=m.reason, first=m.first) for m in musics]


def pydantic_to_graphql_cps(cps: list[CPSubmitPydantic]) -> list[CPSubmit]:
    return [
        CPSubmit(
            id_a=c.id_a,
            id_b=c.id_b,
            id_c=c.id_c,
            active=c.active,
            first=c.first,
            reason=c.reason,
        )
        for c in cps
    ]


def pydantic_to_graphql_dojins(dojins: list[DojinSubmitPydantic]) -> list[DojinSubmit]:
    return [
        DojinSubmit(
            dojin_type=d.dojin_type,
            url=d.url,
            title=d.title,
            author=d.author,
            reason=d.reason,
            image_url=d.image_url,
        )
        for d in dojins
    ]


def pydantic_to_graphql_voting_status(status: VotingStatusPydantic) -> VotingStatus:
    return VotingStatus(
        characters=status.characters,
        musics=status.musics,
        cps=status.cps,
        papers=status.papers,
        dojin=status.dojin,
    )


def pydantic_to_graphql_voting_statistics(
    stats: VotingStatisticsPydantic,
) -> VotingStatistics:
    return VotingStatistics(
        num_user=stats.num_user,
        num_finished_paper=stats.num_finished_paper,
        num_finished_voting=stats.num_finished_voting,
        num_character=stats.num_character,
        num_cp=stats.num_cp,
        num_music=stats.num_music,
        num_dojin=stats.num_dojin,
    )
