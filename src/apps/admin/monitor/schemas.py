"""管理端监控接口输入输出契约(B-049)。显式模型,不返回随意 JSON。"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class OverviewResponse(BaseModel):
    category_totals: dict[str, int]
    distinct_ips: int
    distinct_devices: int
    submissions_by_day: list[dict[str, Any]]


class GroupItem(BaseModel):
    key: str
    voter_count: int


class GroupsResponse(BaseModel):
    kind: str
    items: list[GroupItem]


class SuspectItem(BaseModel):
    vote_id: str
    score: int
    reasons: list[str]


class SuspectsResponse(BaseModel):
    items: list[SuspectItem]
    total: int
    page: int
    page_size: int
    truncated: bool = False


class VoteRow(BaseModel):
    id: int
    vote_id: str
    user_ip: str
    device: Optional[str]
    fill_duration_ms: Optional[int]
    client_env: Optional[dict[str, Any]]
    attempt: Optional[int]
    invalidated: bool
    created_at: Optional[str]


class VotesPage(BaseModel):
    items: list[VoteRow]
    total: int
    page: int
    page_size: int


class AccountDetail(BaseModel):
    vote_id: str
    votes: dict[str, list[dict[str, Any]]]
    review: Optional[dict[str, Any]] = None
    ip_groups: list[str] = []
    device_groups: list[str] = []


class ReviewRequest(BaseModel):
    status: str = ""
    note: str = ""


class ActionResult(BaseModel):
    ok: bool
    detail: str = ""
