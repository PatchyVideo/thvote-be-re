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


# ── Sync schemas ──────────────────────────────────────────────────────────────

class SyncStartRequest(BaseModel):
    collections: list[str] = []  # empty = all collections
    batch_size: int = 500


class SyncStartResponse(BaseModel):
    ok: bool = True
    run_id: str
    message: str


class SyncStatusResponse(BaseModel):
    run_id: Optional[str] = None
    status: str  # running / idle / no_run
    current_collection: Optional[str] = None
    processed: int = 0
    total: int = 0
    inserted: int = 0
    skipped: int = 0
    errors: int = 0


class SyncHistoryItem(BaseModel):
    id: int
    run_id: str
    started_at: str
    completed_at: Optional[str] = None
    status: str
    collections: list[str]
    total_docs: int
    inserted: int
    skipped: int
    errors: int
    initiated_by: str


class SyncHistoryResponse(BaseModel):
    items: list[SyncHistoryItem]
    total: int


# ── Candidate management schemas ───────────────────────────────────────────────

class CandidateFieldSpec(BaseModel):
    name: str
    required: bool


class CandidateFieldsResponse(BaseModel):
    category: str
    fields: list[CandidateFieldSpec]


class CandidateImportRequest(BaseModel):
    vote_year: int
    category: Literal["character", "music"]
    format: Literal["auto", "csv", "json"] = "auto"
    content: str
    dry_run: bool = True


class CandidateRejected(BaseModel):
    line: int
    reason: str


class CandidateImportResponse(BaseModel):
    ok: bool = True
    valid_count: int
    imported: int = 0
    valid: list[dict] = []
    rejected: list[CandidateRejected] = []


class CandidateUpdateRequest(BaseModel):
    category: Literal["character", "music"]
    fields: dict
