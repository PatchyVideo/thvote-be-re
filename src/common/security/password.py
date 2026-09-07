"""Password hashing (Argon2 only).

The bcrypt+salt path for accounts imported from the legacy Mongo store was
removed on 2026-09-06: the new deployment starts from an empty user table,
so no such hash can exist (identity-model spec §6).
"""

from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_PASSWORD_HASHER = PasswordHasher()


@dataclass(frozen=True)
class PasswordVerificationResult:
    """Result of password verification."""

    valid: bool
    needs_rehash: bool = False
    upgraded_hash: str | None = None


def hash_password(password: str) -> str:
    """Hash a password with Argon2."""
    return _PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hashed: str) -> PasswordVerificationResult:
    """Verify an Argon2 password hash; flags a rehash when parameters changed."""
    try:
        valid = _PASSWORD_HASHER.verify(password_hashed, password)
    except (InvalidHashError, VerifyMismatchError):
        return PasswordVerificationResult(valid=False)
    needs_rehash = _PASSWORD_HASHER.check_needs_rehash(password_hashed)
    return PasswordVerificationResult(
        valid=bool(valid),
        needs_rehash=needs_rehash,
        upgraded_hash=hash_password(password) if needs_rehash else None,
    )
