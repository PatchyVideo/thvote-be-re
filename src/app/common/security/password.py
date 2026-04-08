"""Password hashing and legacy password verification helpers."""

from dataclasses import dataclass

import bcrypt
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
    """Verify an Argon2 password hash."""
    try:
        valid = _PASSWORD_HASHER.verify(password_hashed, password)
    except (InvalidHashError, VerifyMismatchError):
        return PasswordVerificationResult(valid=False)
    return PasswordVerificationResult(
        valid=bool(valid),
        needs_rehash=_PASSWORD_HASHER.check_needs_rehash(password_hashed),
        upgraded_hash=hash_password(password) if _PASSWORD_HASHER.check_needs_rehash(password_hashed) else None,
    )


def verify_legacy_password(
    password: str,
    password_hashed: str,
    legacy_salt: str,
) -> PasswordVerificationResult:
    """Verify a legacy bcrypt(password + salt) hash and prepare Argon2 upgrade."""
    legacy_plain = f"{password}{legacy_salt}".encode("utf-8")
    legacy_hash = password_hashed.encode("utf-8")
    valid = bcrypt.checkpw(legacy_plain, legacy_hash)
    if not valid:
        return PasswordVerificationResult(valid=False)
    return PasswordVerificationResult(
        valid=True,
        needs_rehash=True,
        upgraded_hash=hash_password(password),
    )


def verify_any_password(
    password: str,
    password_hashed: str,
    legacy_salt: str | None = None,
) -> PasswordVerificationResult:
    """Verify either an Argon2 hash or a legacy bcrypt+salt hash."""
    if legacy_salt:
        return verify_legacy_password(
            password=password,
            password_hashed=password_hashed,
            legacy_salt=legacy_salt,
        )
    return verify_password(password=password, password_hashed=password_hashed)
