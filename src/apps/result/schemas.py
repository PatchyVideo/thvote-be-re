"""Result query schemas for request/response validation."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class BaseQuery(BaseModel):
    """Base query model."""

    pass


class RankingEntityData(BaseModel):
    """Ranking entity data for vote counts."""

    rank: int
    vote_count: int
    favorite_vote_count: int
    favorite_percentage: int
    vote_percentage: float


class VoteCountData(BaseModel):
    """Vote count data by gender."""

    vote_count: int
    percentage_per_char: float
    percentage_per_total: float


class RankingEntity(BaseModel):
    """Generic ranking data object."""

    rank: list[RankingEntityData]
    display_rank: int
    name: str
    favorite_vote_count_weighted: int
    type: str
    origin: str
    first_appearance: str
    album: str
    name_jp: str
    favorite_percentage: float
    male_vote_count: VoteCountData
    female_vote_count: VoteCountData
    reasons: list[str]
    reasons_count: int


class RankingEntityCP(BaseModel):
    """CP ranking entity."""

    rank: list[RankingEntityData]
    display_rank: int
    name: str
    favorite_vote_count_weighted: int
    id_a: str
    id_b: str
    id_c: Optional[str] = None
    type: str
    origin: str
    first_appearance: str
    album: str
    name_jp: str
    favorite_percentage: float
    active: Optional[str] = None
    reasons: list[str]
    reasons_count: int


class RankingCharacterMusic(BaseModel):
    """Ranking for character and music."""

    rankings: list[RankingEntity]


class RankingGlobal(BaseModel):
    """Global ranking."""

    rankings: list[RankingEntity]


class TrendItem(BaseModel):
    """Trend item data."""

    name: str
    vote_count: int
    percentage: float
    favorite_count: int
    favorite_percentage: float


class TrendQuery(BaseQuery):
    """Trend query object."""

    vote_starts_at: Optional[datetime] = None
    names: list[str]


class Trends(BaseModel):
    """Trends response."""

    trends: list[TrendItem]


class GlobalStatsQuery(BaseQuery):
    """Global statistics query."""

    pass


class GlobalStats(BaseModel):
    """Global statistics response."""

    num_user: int
    num_finished_voting: int
    num_finished_paper: int
    num_character: int
    num_cp: int
    num_music: int
    num_dojin: int


class QuestionnaireQuery(BaseQuery):
    """Questionnaire query."""

    vote_id: str


class QuestionnaireTrendQuery(BaseQuery):
    """Questionnaire trend query."""

    names: list[str]


class CovoteQuery(BaseQuery):
    """Co-vote query."""

    name_a: str
    name_b: str


class CompletionRatesQuery(BaseQuery):
    """Completion rates query."""

    pass


class RankingQuery(BaseModel):
    """Ranking query."""

    rank_type: str
    names: list[str]


class SingleQuery(BaseModel):
    """Single entity query."""

    name: str


class Reasons(BaseModel):
    """Reasons for voting."""

    reasons: list[str]


class ReasonQuery(BaseModel):
    """Reason query."""

    name: str


class VotableBase(BaseModel):
    """Base votable entity."""

    name: str
    type: str
    origin: str
    first_appearance: Optional[str] = None
    album: Optional[str] = None
    name_jp: Optional[str] = None


class VotableCharacter(VotableBase):
    """Votable character."""

    pass


class VotableMusic(VotableBase):
    """Votable music."""

    pass


class VotableWork(VotableBase):
    """Votable work."""

    pass
