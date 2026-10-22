"""Legacy bcrypt+salt password compatibility.

The old Rust user-manager stored ``bcrypt(password + salt)`` for accounts
created before the Argon2 migration.  The import path keeps those hashes and
upgrades them on the first successful login; these tests pin both branches.
"""

from __future__ import annotations

import bcrypt
from argon2.low_level import Type, hash_secret

from src.common.security.password import (
    hash_password,
    verify_any_password,
    verify_legacy_password,
    verify_password,
)


def _argon2i(password: str) -> str:
    return hash_secret(
        password.encode(),
        b"0123456789abcdef",
        time_cost=3,
        memory_cost=4096,
        parallelism=1,
        hash_len=32,
        type=Type.I,
    ).decode()


def _bcrypt_hash(password: str, salt: str) -> str:
    return bcrypt.hashpw(
        f"{password}{salt}".encode(), bcrypt.gensalt(prefix=b"2b")
    ).decode()


def test_argon2i_hash_is_verified_and_marked_for_rehash() -> None:
    hashed = _argon2i("s3cret")
    result = verify_password("s3cret", hashed)
    assert result.valid is True
    assert result.needs_rehash is True
    assert result.upgraded_hash is not None
    assert result.upgraded_hash.startswith("$argon2id$")


def test_argon2i_wrong_password() -> None:
    assert verify_password("wrong", _argon2i("s3cret")).valid is False


def test_legacy_bcrypt_with_salt() -> None:
    salt = "GBtTzcxg"
    hashed = _bcrypt_hash("s3cret", salt)
    result = verify_legacy_password("s3cret", hashed, salt)
    assert result.valid is True
    assert result.needs_rehash is True
    assert result.upgraded_hash is not None
    assert verify_password("s3cret", result.upgraded_hash).valid is True


def test_legacy_bcrypt_wrong_password() -> None:
    salt = "GBtTzcxg"
    hashed = _bcrypt_hash("s3cret", salt)
    assert verify_legacy_password("wrong", hashed, salt).valid is False


def test_legacy_bcrypt_wrong_salt() -> None:
    hashed = _bcrypt_hash("s3cret", "GBtTzcxg")
    assert verify_legacy_password("s3cret", hashed, "othersalt").valid is False


def test_legacy_bcrypt_malformed_hash_fails_closed() -> None:
    assert verify_legacy_password("s3cret", "not-a-hash", "salt").valid is False


def test_verify_any_routes_by_salt_presence() -> None:
    salt = "GBtTzcxg"
    legacy = _bcrypt_hash("s3cret", salt)
    assert verify_any_password("s3cret", legacy, salt).valid is True
    argon = hash_password("s3cret")
    assert verify_any_password("s3cret", argon, None).valid is True
    assert verify_any_password("wrong", argon, None).valid is False
