"""JWT helpers for session and vote tokens."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt

from ...common.config import get_settings
from ...common.exceptions import AppException

SESSION_AUDIENCE = "userspace"
VOTE_AUDIENCE = "vote"
SESSION_EXPIRE_DAYS = 7


class JWTConfigurationError(AppException):
    """Raised when JWT settings are incomplete."""

    def __init__(self, message: str) -> None:
        super().__init__(message, details=500)


class JWTValidationError(AppException):
    """Raised when a JWT cannot be validated."""

    def __init__(self, message: str = "INVALID_TOKEN") -> None:
        super().__init__(message, details=401)


@dataclass(frozen=True)
class SessionTokenPayload:
    """Payload carried by a userspace session token."""

    user_id: str


@dataclass(frozen=True)
class VoteTokenPayload:
    """Payload carried by a vote token.

    Subject is the authenticated user_id, not a per-submission id.  A vote
    token signed at login time is reused across the configured vote window.
    Aligned with Rust user-manager behavior.
    """

    user_id: str


def _read_key(path: str | None) -> str | None:
    if not path:
        return None
    return Path(path).read_text(encoding="utf-8")


def _encoding_key() -> tuple[str, str]:
    settings = get_settings()
    if settings.jwt_secret_key:
        return settings.jwt_secret_key, settings.jwt_algorithm

    secret_key_from_file = _read_key(settings.jwt_secret_key_file)
    if secret_key_from_file:
        return secret_key_from_file, settings.jwt_algorithm

    private_key = _read_key(settings.jwt_private_key_path)
    if private_key:
        return private_key, settings.jwt_algorithm

    raise JWTConfigurationError("JWT signing key is not configured")


def _decoding_key() -> tuple[str, str]:
    settings = get_settings()
    if settings.jwt_secret_key:
        return settings.jwt_secret_key, settings.jwt_algorithm

    secret_key_from_file = _read_key(settings.jwt_secret_key_file)
    if secret_key_from_file:
        return secret_key_from_file, settings.jwt_algorithm

    public_key = _read_key(settings.jwt_public_key_path)
    if public_key:
        return public_key, settings.jwt_algorithm

    private_key = _read_key(settings.jwt_private_key_path)
    if private_key:
        return private_key, settings.jwt_algorithm

    raise JWTConfigurationError("JWT verification key is not configured")


def _encode(payload: dict[str, Any]) -> str:
    key, algorithm = _encoding_key()
    return jwt.encode(payload, key, algorithm=algorithm)


def _decode(token: str, audience: str) -> dict[str, Any]:
    key, algorithm = _decoding_key()
    try:
        return jwt.decode(
            token,
            key,
            algorithms=[algorithm],
            audience=audience,
        )
    except jwt.PyJWTError as exc:
        raise JWTValidationError(str(exc)) from exc


def create_session_token(user_id: str) -> str:
    """Create a userspace session token."""
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "aud": SESSION_AUDIENCE,
        "user_id": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=SESSION_EXPIRE_DAYS)).timestamp()),
    }
    return _encode(payload)


def decode_session_token(token: str) -> SessionTokenPayload:
    """Decode and validate a userspace session token."""
    payload = _decode(token, SESSION_AUDIENCE)
    user_id = payload.get("user_id") or payload.get("sub")
    if not user_id:
        raise JWTValidationError("TOKEN_MISSING_USER_ID")
    return SessionTokenPayload(user_id=str(user_id))


def create_vote_token(
    user_id: str,
    vote_start: datetime,
    vote_end: datetime,
) -> str:
    """Create a vote token constrained by the configured vote window.

    Subject is user_id; the token is signed once at login and reused for
    every vote submission within [vote_start, vote_end].
    """
    payload = {
        "sub": user_id,
        "aud": VOTE_AUDIENCE,
        "user_id": user_id,
        "iat": int(datetime.now(UTC).timestamp()),
        "nbf": int(vote_start.timestamp()),
        "exp": int(vote_end.timestamp()),
    }
    return _encode(payload)


def decode_vote_token(token: str) -> VoteTokenPayload:
    """Decode and validate a vote token."""
    payload = _decode(token, VOTE_AUDIENCE)
    user_id = payload.get("user_id") or payload.get("sub")
    if not user_id:
        raise JWTValidationError("TOKEN_MISSING_USER_ID")
    return VoteTokenPayload(user_id=str(user_id))
