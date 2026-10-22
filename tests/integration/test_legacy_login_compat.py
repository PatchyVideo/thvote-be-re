"""End-to-end legacy password compatibility through ``UserService``.

Covers the imported-account shapes:
- Argon2i (old Rust default) logs in and is upgraded to Argon2id;
- bcrypt+salt logs in, is upgraded, and keeps working for update/remove;
- wrong passwords stay ``INCORRECT_PASSWORD``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import bcrypt
import pytest
from argon2.low_level import Type, hash_secret

from src.apps.user.schemas import (
    LoginEmailPasswordRequest,
    Meta,
    RemoveVoterRequest,
    UpdatePasswordRequest,
)
from src.common.exceptions import ValidationError
from src.common.security.password import verify_password
from src.db_model.user import User
from src.db_model.user_identity import UserIdentity

META = Meta(user_ip="203.0.113.7", additional_fingureprint="device-legacy")
PASSWORD = "legacy-pass-123"


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


async def _make_user(
    session,
    *,
    email: str,
    password_hash: str,
    salt: str | None = None,
) -> User:
    now = datetime.now(UTC)
    user = User(
        id=f"legacy-{email.split('@')[0]}",
        nickname="legacy",
        password_hash=password_hash,
        legacy_salt=salt,
        removed=False,
        register_date=now,
        register_ip_address="198.51.100.9",
        register_device_id="",
    )
    user.identities.append(
        UserIdentity(
            provider="email",
            subject=email,
            verified=True,
            verified_at=now,
            created_at=now,
            created_ip="198.51.100.9",
            created_device_id="",
        )
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _request(email: str) -> LoginEmailPasswordRequest:
    return LoginEmailPasswordRequest(
        email=email, password=PASSWORD, meta=META
    )


@pytest.mark.asyncio
async def test_argon2i_login_upgrades_to_argon2id(user_service, session):
    email = "argon2i@example.com"
    user = await _make_user(session, email=email, password_hash=_argon2i(PASSWORD))

    response = await user_service.login_with_email_password(_request(email))

    assert response.session_token
    assert response.vote_token
    assert response.user.email == email
    assert response.user.password is True
    await session.refresh(user)
    assert user.password_hash.startswith("$argon2id$")
    assert user.legacy_salt is None


@pytest.mark.asyncio
async def test_bcrypt_login_upgrades_and_clears_salt(user_service, session):
    email = "bcrypt@example.com"
    salt = "GBtTzcxg"
    user = await _make_user(
        session,
        email=email,
        password_hash=_bcrypt_hash(PASSWORD, salt),
        salt=salt,
    )

    response = await user_service.login_with_email_password(_request(email))

    assert response.session_token
    await session.refresh(user)
    assert user.password_hash.startswith("$argon2id$")
    assert user.legacy_salt is None
    assert verify_password(PASSWORD, user.password_hash).valid is True

    # Second login goes through the Argon2 branch and still works.
    again = await user_service.login_with_email_password(_request(email))
    assert again.session_token


@pytest.mark.asyncio
async def test_bcrypt_wrong_password_is_rejected(user_service, session):
    email = "bcrypt-wrong@example.com"
    salt = "GBtTzcxg"
    await _make_user(
        session,
        email=email,
        password_hash=_bcrypt_hash(PASSWORD, salt),
        salt=salt,
    )
    request = LoginEmailPasswordRequest(
        email=email, password="wrong-pass", meta=META
    )
    with pytest.raises(ValidationError) as exc:
        await user_service.login_with_email_password(request)
    assert exc.value.message == "INCORRECT_PASSWORD"


@pytest.mark.asyncio
async def test_update_password_accepts_legacy_bcrypt_old_password(
    user_service, session
):
    email = "bcrypt-update@example.com"
    salt = "GBtTzcxg"
    user = await _make_user(
        session,
        email=email,
        password_hash=_bcrypt_hash(PASSWORD, salt),
        salt=salt,
    )
    token = user_service.auth.create_session_token(user.id)

    await user_service.update_password(
        UpdatePasswordRequest(
            user_token=token,
            old_password=PASSWORD,
            new_password="brand-new-pass",
            meta=META,
        )
    )

    await session.refresh(user)
    assert user.legacy_salt is None
    assert verify_password("brand-new-pass", user.password_hash).valid is True


@pytest.mark.asyncio
async def test_remove_voter_accepts_legacy_bcrypt_old_password(
    user_service, session
):
    email = "bcrypt-remove@example.com"
    salt = "GBtTzcxg"
    user = await _make_user(
        session,
        email=email,
        password_hash=_bcrypt_hash(PASSWORD, salt),
        salt=salt,
    )
    token = user_service.auth.create_session_token(user.id)

    await user_service.remove_voter(
        RemoveVoterRequest(
            user_token=token, old_password=PASSWORD, meta=META
        )
    )

    await session.refresh(user)
    assert user.removed is True
    assert user.password_hash is None
    assert user.legacy_salt is None
    assert user.identities == []
