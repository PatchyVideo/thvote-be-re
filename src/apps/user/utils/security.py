"""Security utilities for the user module."""

from dataclasses import dataclass

from src.common.security.jwt import (
    SessionTokenPayload,
    create_session_token,
    decode_session_token,
    create_vote_token,
    decode_vote_token,
)
from src.common.security.password import (
    PasswordVerificationResult,
    hash_password,
    verify_any_password,
    verify_legacy_password,
    verify_password,
)


@dataclass(frozen=True)
class AuthProvider:
    """Provider for authentication-related external integrations.

    Encapsulates password hashing, JWT token management, and other
    authentication-related operations.
    """

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password with Argon2."""
        return hash_password(password)

    @staticmethod
    def verify_password(
        password: str, password_hashed: str
    ) -> PasswordVerificationResult:
        """Verify an Argon2 password hash."""
        return verify_password(password, password_hashed)

    @staticmethod
    def verify_legacy_password(
        password: str,
        password_hashed: str,
        legacy_salt: str,
    ) -> PasswordVerificationResult:
        """Verify a legacy bcrypt+salt hash and prepare Argon2 upgrade."""
        return verify_legacy_password(password, password_hashed, legacy_salt)

    @staticmethod
    def verify_any_password(
        password: str,
        password_hashed: str,
        legacy_salt: str | None = None,
    ) -> PasswordVerificationResult:
        """Verify either an Argon2 hash or a legacy bcrypt+salt hash."""
        return verify_any_password(password, password_hashed, legacy_salt)

    @staticmethod
    def create_session_token(user_id: str) -> str:
        """Create a userspace session token."""
        return create_session_token(user_id)

    @staticmethod
    def decode_session_token(token: str) -> SessionTokenPayload:
        """Decode and validate a userspace session token."""
        return decode_session_token(token)

    @staticmethod
    def create_vote_token(
        vote_id: str,
        vote_start,
        vote_end,
    ) -> str:
        """Create a vote token constrained by the configured vote window."""
        return create_vote_token(vote_id, vote_start, vote_end)

    @staticmethod
    def decode_vote_token(token: str):
        """Decode and validate a vote token."""
        return decode_vote_token(token)
