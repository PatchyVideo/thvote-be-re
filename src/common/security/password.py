"""Password hashing and legacy password compatibility.

New accounts always store Argon2 hashes.  Accounts imported from the old Mongo
user store may still carry a legacy ``bcrypt(password + salt)`` hash; those are
verified only while ``legacy_salt`` is present and are upgraded to Argon2 on
the first successful password login (same behaviour as the Rust user-manager).
"""

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


def verify_legacy_password(
    password: str,
    password_hashed: str,
    legacy_salt: str,
) -> PasswordVerificationResult:
    """Verify a legacy ``bcrypt(password + salt)`` hash.

    Mirrors the Rust user-manager's legacy path: the 8-character salt is
    concatenated to the plaintext (the bcrypt salt is already inside the hash),
    and a successful match always schedules an Argon2 upgrade.
    """
    try:
        valid = bcrypt.checkpw(
            f"{password}{legacy_salt}".encode("utf-8"),
            password_hashed.encode("utf-8"),
        )
    except (ValueError, TypeError):
        # Malformed hash/salt: fail closed, never surface a 500 to the login
        # endpoint because of one bad imported row.
        return PasswordVerificationResult(valid=False)
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
    """Verify either a legacy bcrypt+salt hash or an Argon2 hash.

    ``legacy_salt`` is the routing signal, exactly like the old Rust backend:
    present -> bcrypt path; absent -> Argon2 path.
    """
    if legacy_salt:
        return verify_legacy_password(password, password_hashed, legacy_salt)
    return verify_password(password, password_hashed)
