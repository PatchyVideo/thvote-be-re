"""user_identity semantics end-to-end through UserService (sqlite + fakeredis).

Covers spec 2026-09-06 §5 / §8: register metadata, rebind-as-replace,
conflict 409, removed-then-re-register, banned accounts, case normalisation,
vote eligibility by provider.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.apps.user.identity import IdentityProvider
from src.apps.user.schemas import (
    LoginEmailPasswordRequest,
    LoginEmailRequest,
    LoginPhoneRequest,
    Meta,
    RemoveVoterRequest,
    UpdateEmailRequest,
    UpdatePhoneRequest,
)
from src.common.exceptions import UnauthorizedError, ValidationError
from src.db_model.user import User
from src.db_model.user_identity import UserIdentity
from tests.helpers.users import make_user

META = Meta(user_ip="203.0.113.7", additional_fingureprint="device-A")


async def _login_email(user_service, patch_redis, email, *, meta=META, nickname=None):
    await patch_redis.set(f"email-verify-{email}", "123456", ex=3600)
    return await user_service.login_with_email_code(
        LoginEmailRequest(email=email, nickname=nickname, verify_code="123456", meta=meta)
    )


async def _login_phone(user_service, phone, *, meta=META):
    return await user_service.login_with_phone_code(
        LoginPhoneRequest(phone=phone, verify_code="999999", meta=meta)
    )


@pytest.mark.asyncio
async def test_first_login_creates_account_and_identity_with_same_meta(
    user_service, patch_redis
):
    await _login_email(user_service, patch_redis, "new@example.com", nickname="n")

    user = await user_service.identities.resolve(IdentityProvider.EMAIL, "new@example.com")
    assert user.register_ip_address == "203.0.113.7"
    assert user.register_device_id == "device-A"
    [identity] = user.identities
    assert (identity.provider, identity.subject) == ("email", "new@example.com")
    assert identity.verified is True and identity.verified_at is not None
    assert identity.created_ip == "203.0.113.7"
    assert identity.created_device_id == "device-A"
    assert identity.last_login_at is not None


@pytest.mark.asyncio
async def test_second_login_reuses_account_and_touches_last_login(
    user_service, patch_redis
):
    first = await _login_email(user_service, patch_redis, "again@example.com")
    user = await user_service.identities.resolve(IdentityProvider.EMAIL, "again@example.com")
    before = user.identity("email").last_login_at

    second = await _login_email(user_service, patch_redis, "again@example.com")
    user = await user_service.identities.resolve(IdentityProvider.EMAIL, "again@example.com")

    assert first.user.created_at == second.user.created_at
    assert len(user.identities) == 1
    assert user.identity("email").last_login_at >= before


@pytest.mark.asyncio
async def test_email_subject_is_case_insensitive(user_service, patch_redis):
    # Only the local part varies: pydantic's EmailStr already lower-cases the
    # domain, and the verification-code key must match what the client sent.
    await _login_email(user_service, patch_redis, "MIXED@example.com")
    await _login_email(user_service, patch_redis, "mixed@example.com")

    user = await user_service.identities.resolve(IdentityProvider.EMAIL, "Mixed@EXAMPLE.COM")
    assert user is not None
    assert user.identity("email").subject == "mixed@example.com"


@pytest.mark.asyncio
async def test_rebind_phone_replaces_row_with_new_meta(user_service, patch_redis, session):
    login = await _login_phone(user_service, "13800000001")
    new_meta = Meta(user_ip="198.51.100.9", additional_fingureprint="device-B")

    await user_service.update_phone(
        UpdatePhoneRequest(
            user_token=login.session_token, phone="13800000002",
            verify_code="999999", meta=new_meta,
        )
    )

    rows = (await session.execute(select(UserIdentity))).scalars().all()
    assert [(r.provider, r.subject) for r in rows] == [("phone", "13800000002")]
    assert rows[0].created_ip == "198.51.100.9"
    assert rows[0].created_device_id == "device-B"
    assert await user_service.identities.resolve(IdentityProvider.PHONE, "13800000001") is None


@pytest.mark.asyncio
async def test_bind_email_to_phone_account_adds_second_identity(user_service, patch_redis):
    login = await _login_phone(user_service, "13800000003")
    await patch_redis.set("email-verify-add@example.com", "123456", ex=3600)

    await user_service.update_email(
        UpdateEmailRequest(
            user_token=login.session_token, email="add@example.com",
            verify_code="123456", meta=META,
        )
    )

    user = await user_service.identities.resolve(IdentityProvider.PHONE, "13800000003")
    assert {i.provider for i in user.identities} == {"phone", "email"}


@pytest.mark.asyncio
async def test_rebind_to_taken_email_is_409(user_service, patch_redis):
    await _login_email(user_service, patch_redis, "taken@example.com")
    other = await _login_phone(user_service, "13800000004")
    await patch_redis.set("email-verify-taken@example.com", "123456", ex=3600)

    with pytest.raises(ValidationError) as exc_info:
        await user_service.update_email(
            UpdateEmailRequest(
                user_token=other.session_token, email="taken@example.com",
                verify_code="123456", meta=META,
            )
        )
    assert exc_info.value.message == "USER_ALREADY_EXIST"
    assert exc_info.value.details == 409


@pytest.mark.asyncio
async def test_removed_account_then_same_email_gets_new_account(
    user_service, patch_redis, session
):
    login = await _login_email(user_service, patch_redis, "re@example.com")
    first_id = (
        await user_service.identities.resolve(IdentityProvider.EMAIL, "re@example.com")
    ).id
    await user_service.remove_voter(
        RemoveVoterRequest(user_token=login.session_token, meta=META)
    )

    await _login_email(user_service, patch_redis, "re@example.com")

    fresh = await user_service.identities.resolve(IdentityProvider.EMAIL, "re@example.com")
    assert fresh.id != first_id
    tombstone = await session.get(User, first_id)
    assert tombstone.removed is True and tombstone.identities == []


@pytest.mark.asyncio
async def test_banned_account_cannot_login_or_reregister(user_service, patch_redis, session):
    """Admin ban keeps identity rows (unban must restore); so the subject is
    neither usable for login nor free for a new account."""
    await make_user(session, email="banned@example.com", removed=True, password="pw")

    with pytest.raises(UnauthorizedError) as exc_info:
        await _login_email(user_service, patch_redis, "banned@example.com")
    assert exc_info.value.message == "USER_REMOVED"
    assert exc_info.value.details == 403

    with pytest.raises(UnauthorizedError):
        await user_service.login_with_email_password(
            LoginEmailPasswordRequest(email="banned@example.com", password="pw", meta=META)
        )


@pytest.mark.asyncio
async def test_password_login_uses_email_identity(user_service, patch_redis, session):
    await make_user(session, email="pw@example.com", password="hunter22")

    resp = await user_service.login_with_email_password(
        LoginEmailPasswordRequest(email="PW@example.com", password="hunter22", meta=META)
    )
    assert resp.user.email == "pw@example.com"
    assert resp.user.password is True

    with pytest.raises(ValidationError):
        await user_service.login_with_email_password(
            LoginEmailPasswordRequest(email="pw@example.com", password="nope", meta=META)
        )


@pytest.mark.asyncio
async def test_vote_token_respects_eligible_provider_config(
    user_service, patch_redis, session, monkeypatch
):
    from types import SimpleNamespace

    email_user = await make_user(session, email="e@example.com")
    phone_user = await make_user(session, phone="13800000005")

    monkeypatch.setattr(
        "src.apps.user.identity.get_settings",
        lambda: SimpleNamespace(vote_eligible_providers=["phone"]),
    )
    assert user_service._maybe_sign_vote_token(email_user) == ""
    assert user_service._maybe_sign_vote_token(phone_user) != ""
