"""JWT helpers: session + vote token round-trip and window enforcement."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from freezegun import freeze_time

from src.common.security.jwt import (
    JWTValidationError,
    create_session_token,
    create_vote_token,
    decode_session_token,
    decode_vote_token,
)


def test_session_token_roundtrip() -> None:
    token = create_session_token("user-123")
    payload = decode_session_token(token)
    assert payload.user_id == "user-123"


def test_session_token_invalid() -> None:
    with pytest.raises(JWTValidationError):
        decode_session_token("not.a.token")


def test_vote_token_subject_is_user_id() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 12, 31, tzinfo=UTC)
    with freeze_time("2026-06-01"):
        token = create_vote_token("user-7", start, end)
        payload = decode_vote_token(token)
    assert payload.user_id == "user-7"


def test_vote_token_rejected_before_window() -> None:
    start = datetime(2030, 1, 1, tzinfo=UTC)
    end = datetime(2030, 12, 31, tzinfo=UTC)
    with freeze_time("2030-01-01"):
        token = create_vote_token("user-x", start, end)
    # Decode before window opens
    with freeze_time("2026-01-01"):
        with pytest.raises(JWTValidationError):
            decode_vote_token(token)


def test_vote_token_rejected_after_window() -> None:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    end = datetime(2020, 1, 2, tzinfo=UTC)
    with freeze_time("2020-01-01T12:00:00"):
        token = create_vote_token("user-y", start, end)
    with freeze_time("2030-01-01"):
        with pytest.raises(JWTValidationError):
            decode_vote_token(token)
