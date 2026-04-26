"""Update + remove flows: token-gated mutations + soft delete."""

from __future__ import annotations

import pytest

from src.apps.user.schemas import (
    Meta,
    RemoveVoterRequest,
    TokenStatusRequest,
    UpdateEmailRequest,
    UpdateNicknameRequest,
    UpdatePasswordRequest,
    UpdatePhoneRequest,
    LoginEmailRequest,
)
from src.apps.user.utils.security import AuthProvider
from src.common.exceptions import (
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)


@pytest.mark.asyncio
async def test_token_status_passes_for_valid_token(user_service):
    token = AuthProvider.create_session_token("user-123")
    await user_service.token_status(TokenStatusRequest(user_token=token))


@pytest.mark.asyncio
async def test_token_status_rejects_garbage(user_service):
    with pytest.raises(UnauthorizedError):
        await user_service.token_status(TokenStatusRequest(user_token="not.a.token"))


async def _make_user_via_email(user_service, patch_redis, email="u@example.com", nickname="u"):
    await patch_redis.set(f"email-verify-{email}", "123456", ex=3600)
    return await user_service.login_with_email_code(
        LoginEmailRequest(
            email=email, nickname=nickname, verify_code="123456", meta=Meta()
        )
    )


@pytest.mark.asyncio
async def test_update_nickname_writes_change(user_service, patch_redis):
    login = await _make_user_via_email(user_service, patch_redis)

    await user_service.update_nickname(
        UpdateNicknameRequest(
            user_token=login.session_token, nickname="newname", meta=Meta()
        )
    )
    refreshed = await user_service.user_dao.get_by_email("u@example.com")
    assert refreshed.nickname == "newname"


@pytest.mark.asyncio
async def test_update_password_first_time_no_old_password(user_service, patch_redis):
    login = await _make_user_via_email(user_service, patch_redis, "p@example.com", "p")
    await user_service.update_password(
        UpdatePasswordRequest(
            user_token=login.session_token,
            old_password=None,
            new_password="newpass1",
            meta=Meta(),
        )
    )
    user = await user_service.user_dao.get_by_email("p@example.com")
    assert user.password_hash is not None


@pytest.mark.asyncio
async def test_update_password_requires_old_when_set(user_service, patch_redis):
    login = await _make_user_via_email(user_service, patch_redis, "q@example.com", "q")
    # First set a password
    await user_service.update_password(
        UpdatePasswordRequest(
            user_token=login.session_token,
            new_password="firstpass",
            meta=Meta(),
        )
    )

    # Without old_password, second change must fail
    with pytest.raises(ValidationError):
        await user_service.update_password(
            UpdatePasswordRequest(
                user_token=login.session_token,
                new_password="anotherpass",
                meta=Meta(),
            )
        )

    # With wrong old_password
    with pytest.raises(ValidationError):
        await user_service.update_password(
            UpdatePasswordRequest(
                user_token=login.session_token,
                old_password="wrong",
                new_password="anotherpass",
                meta=Meta(),
            )
        )

    # Correct old_password succeeds
    await user_service.update_password(
        UpdatePasswordRequest(
            user_token=login.session_token,
            old_password="firstpass",
            new_password="anotherpass",
            meta=Meta(),
        )
    )


@pytest.mark.asyncio
async def test_update_email_uniqueness_check(user_service, patch_redis):
    a = await _make_user_via_email(user_service, patch_redis, "a@example.com", "a")
    b = await _make_user_via_email(user_service, patch_redis, "b@example.com", "b")

    # b tries to take a's email
    await patch_redis.set("email-verify-a@example.com", "123456", ex=3600)
    with pytest.raises(ValidationError):
        await user_service.update_email(
            UpdateEmailRequest(
                user_token=b.session_token,
                email="a@example.com",
                verify_code="123456",
                meta=Meta(),
            )
        )


@pytest.mark.asyncio
async def test_remove_voter_clears_identifiers_and_blocks_lookup(user_service, patch_redis):
    login = await _make_user_via_email(user_service, patch_redis, "r@example.com", "r")
    await user_service.remove_voter(
        RemoveVoterRequest(user_token=login.session_token, meta=Meta())
    )
    # Subsequent token use should fail because user is now soft-deleted
    with pytest.raises(NotFoundError):
        await user_service.update_nickname(
            UpdateNicknameRequest(
                user_token=login.session_token,
                nickname="x",
                meta=Meta(),
            )
        )
    # Email is freed up — a new signup with the same address must succeed
    fresh = await _make_user_via_email(user_service, patch_redis, "r@example.com", "r2")
    assert fresh.user.email == "r@example.com"
