"""Legacy ``/user-token-status`` compat endpoint — parity with the old Rust
gateway handler (``thvote-be/gateway/src/main.rs::user_token_status``).

The frontend logs the user out unless the response is ``{"status": "valid"}``,
so these tests pin the exact branching: invalid token -> "invalid"; valid token
-> "valid" (+ voting_status / papers_json only when a usable vote_token is
present).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from freezegun import freeze_time

from src.api.rest.legacy.router import TokenStatusInputs, user_token_status
from src.apps.submit.schemas import PaperSubmitRest, SubmitMetadata, VotingStatus
from src.common.security.jwt import create_session_token, create_vote_token


class _FakeSubmitService:
    """Records the vote_id used to query, so we can assert it's the vote
    token's user_id (not the request body)."""

    def __init__(self, voting_status: VotingStatus, papers_json: str = "{}") -> None:
        self._vs = voting_status
        self._papers_json = papers_json
        self.voting_status_calls: list[str] = []
        self.paper_calls: list[str] = []

    async def get_voting_status(self, vote_id: str) -> VotingStatus:
        self.voting_status_calls.append(vote_id)
        return self._vs

    async def get_paper_submit(self, vote_id: str) -> PaperSubmitRest:
        self.paper_calls.append(vote_id)
        return PaperSubmitRest(papers_json=self._papers_json, meta=SubmitMetadata())


def _vs(**over: bool) -> VotingStatus:
    base = dict(characters=False, musics=False, cps=False, papers=False, dojin=False)
    base.update(over)
    return VotingStatus(**base)


@pytest.mark.asyncio
async def test_invalid_user_token_returns_invalid() -> None:
    svc = _FakeSubmitService(_vs())
    out = await user_token_status(TokenStatusInputs(user_token="not.a.token"), svc)
    assert out.status == "invalid"
    assert out.voting_status is None
    assert svc.voting_status_calls == []  # submissions never queried


@pytest.mark.asyncio
async def test_session_token_in_user_field_only() -> None:
    """A vote token in the user_token slot must be rejected (wrong audience)."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 12, 31, tzinfo=UTC)
    with freeze_time("2026-06-01"):
        vote = create_vote_token("user-1", start, end)
        out = await user_token_status(
            TokenStatusInputs(user_token=vote), _FakeSubmitService(_vs())
        )
    assert out.status == "invalid"


@pytest.mark.asyncio
async def test_valid_user_no_vote_token_is_valid_without_status() -> None:
    svc = _FakeSubmitService(_vs())
    token = create_session_token("user-1")
    out = await user_token_status(
        TokenStatusInputs(user_token=token, vote_token=""), svc
    )
    assert out.status == "valid"
    assert out.voting_status is None
    assert svc.voting_status_calls == []


@pytest.mark.asyncio
async def test_valid_user_invalid_vote_token_is_valid_without_status() -> None:
    svc = _FakeSubmitService(_vs())
    token = create_session_token("user-1")
    out = await user_token_status(
        TokenStatusInputs(user_token=token, vote_token="garbage"), svc
    )
    assert out.status == "valid"
    assert out.voting_status is None


@pytest.mark.asyncio
async def test_valid_tokens_attach_voting_status_no_papers() -> None:
    svc = _FakeSubmitService(_vs(characters=True, papers=False))
    session = create_session_token("user-9")
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 12, 31, tzinfo=UTC)
    with freeze_time("2026-06-01"):
        vote = create_vote_token("user-9", start, end)
        out = await user_token_status(
            TokenStatusInputs(user_token=session, vote_token=vote), svc
        )
    assert out.status == "valid"
    assert out.voting_status is not None
    assert out.voting_status.characters is True
    assert out.papers_json is None  # papers not done -> not fetched
    assert svc.voting_status_calls == ["user-9"]  # queried by vote token's user_id
    assert svc.paper_calls == []


@pytest.mark.asyncio
async def test_valid_tokens_with_papers_include_papers_json() -> None:
    svc = _FakeSubmitService(_vs(papers=True), papers_json='{"q":1}')
    session = create_session_token("user-9")
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 12, 31, tzinfo=UTC)
    with freeze_time("2026-06-01"):
        vote = create_vote_token("user-9", start, end)
        out = await user_token_status(
            TokenStatusInputs(user_token=session, vote_token=vote), svc
        )
    assert out.status == "valid"
    assert out.papers_json == '{"q":1}'
    assert svc.paper_calls == ["user-9"]
