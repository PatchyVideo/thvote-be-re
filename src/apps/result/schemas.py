"""Result query schemas for request/response validation."""

from typing import Literal, Optional

from pydantic import BaseModel


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


class RankingCharacterMusic(BaseModel):
    """Ranking for character and music."""

    rankings: list[RankingEntity]


class TrendItem(BaseModel):
    """Trend item data."""

    name: str
    vote_count: int
    percentage: float
    favorite_count: int
    favorite_percentage: float


class Trends(BaseModel):
    """Trends response."""

    trends: list[TrendItem]


class GlobalStats(BaseModel):
    """Global statistics response."""

    num_vote: int = 0
    num_finished_voting: int = 0
    num_finished_paper: int = 0
    num_char: int = 0
    num_cp: int = 0
    num_music: int = 0
    num_doujin: int = 0
    num_male: int = 0
    num_female: int = 0


class Reasons(BaseModel):
    """Reasons for voting."""

    reasons: list[str]


class VotableBase(BaseModel):
    """Base votable entity."""

    name: str
    type: str
    origin: str
    first_appearance: Optional[str] = None
    album: Optional[str] = None
    name_jp: Optional[str] = None


# ── Query types ────────────────────────────────────────────────────────

class RankingQuery(BaseModel):
    vote_year: Optional[int] = None
    category: Literal["character", "music", "cp"] = "character"
    names: list[str] = []


class TrendQuery(BaseModel):
    vote_year: Optional[int] = None
    category: Literal["character", "music", "cp"] = "character"
    name: str


class ReasonQuery(BaseModel):
    vote_year: Optional[int] = None
    category: Literal["character", "music", "cp"] = "character"
    name: str


class SingleQuery(BaseModel):
    vote_year: Optional[int] = None
    category: Literal["character", "music", "cp"] = "character"
    name: str


class CovoteQuery(BaseModel):
    vote_year: Optional[int] = None
    category: Literal["character", "music"] = "character"


class GlobalStatsQuery(BaseModel):
    vote_year: Optional[int] = None


class CompletionRatesQuery(BaseModel):
    vote_year: Optional[int] = None


class QuestionnaireQuery(BaseModel):
    vote_year: Optional[int] = None
    question_id: str


class QuestionnaireTrendQuery(BaseModel):
    vote_year: Optional[int] = None
    question_id: str
