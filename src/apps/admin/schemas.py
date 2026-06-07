"""Admin endpoint schemas."""

from typing import Literal, Optional

from pydantic import BaseModel




class CandidateItem(BaseModel):
    name: str
    name_jp: str = ""
    origin: str = ""
    type: str = ""
    first_appearance: Optional[str] = None
    album: Optional[str] = None


class ImportCandidatesRequest(BaseModel):
    vote_year: int
    category: Literal["character", "music"]
    items: list[CandidateItem]


class ImportCandidatesResponse(BaseModel):
    ok: bool = True
    imported: int


class ComputeResultsResponse(BaseModel):
    ok: bool
    vote_year: int
    duration_seconds: float
    counts: dict


class FinalizeRankingResponse(BaseModel):
    ok: bool = True
    vote_year: int
    saved: int


# ── User admin schemas ─────────────────────────────────────────────────────────

class UserAdminItem(BaseModel):
    id: str
    nickname: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    email_verified: bool = False
    phone_verified: bool = False
    register_date: Optional[str] = None
    removed: bool = False


class UserListResponse(BaseModel):
    items: list[UserAdminItem]
    total: int


class UserDetailResponse(BaseModel):
    user: UserAdminItem
    vote_submitted: dict[str, bool]


class BanResponse(BaseModel):
    ok: bool = True
    removed: bool


# ── Stats schemas ──────────────────────────────────────────────────────────────

class VoteWindowStatus(BaseModel):
    status: str  # open / closed / upcoming
    start: str
    end: str


class StatsResponse(BaseModel):
    vote_year: int
    total_users: int
    vote_window: VoteWindowStatus
    submissions: dict[str, int]


# ── Candidate admin schemas ────────────────────────────────────────────────────

class CandidateAdminItem(BaseModel):
    id: int
    vote_year: int
    name: str
    name_jp: str = ""
    type: str = ""
    origin: Optional[str] = None
    first_appearance: Optional[str] = None
    album: Optional[str] = None


class CandidateListResponse(BaseModel):
    items: list[CandidateAdminItem]
    total: int


# ── Activity log + export schemas ─────────────────────────────────────────────

class ActivityLogItem(BaseModel):
    id: int
    event_type: str
    user_id: Optional[str] = None
    requester_ip: Optional[str] = None
    created_at: str


class ActivityLogResponse(BaseModel):
    items: list[ActivityLogItem]
    total: int
