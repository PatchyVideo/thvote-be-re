"""JWT helpers: session + vote token round-trip and window enforcement."""

from __future__ import annotations

from datetime import UTC, datetime

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


def _read_exp(token: str) -> int:
    """Read the exp claim of a session token (signature checked, time claims not
    — caller may decode at a frozen time other than the token's iat)."""
    import jwt as pyjwt

    from src.common.config import get_settings

    s = get_settings()
    claims = pyjwt.decode(
        token,
        s.jwt_secret_key,
        algorithms=[s.jwt_algorithm],
        audience="userspace",
        options={"verify_exp": False, "verify_iat": False, "verify_nbf": False},
    )
    return int(claims["exp"])


def test_session_token_default_expiry_is_30_days() -> None:
    with freeze_time("2026-06-01"):
        token = create_session_token("u")
        # 2026-06-01 + 30d = 2026-07-01
        assert _read_exp(token) == int(datetime(2026, 7, 1, tzinfo=UTC).timestamp())


def test_session_token_expiry_is_configurable(monkeypatch) -> None:
    from src.common.config import get_settings

    custom = get_settings().model_copy(update={"session_expire_days": 5})
    monkeypatch.setattr("src.common.security.jwt.get_settings", lambda: custom)
    with freeze_time("2026-06-01"):
        token = create_session_token("u")
        # 2026-06-01 + 5d = 2026-06-06
        assert _read_exp(token) == int(datetime(2026, 6, 6, tzinfo=UTC).timestamp())
