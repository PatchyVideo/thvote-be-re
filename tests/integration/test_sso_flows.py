"""SSO binding flows against the user_identity table (sqlite + fakeredis)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.apps.user.dao import ActivityLogDAO, UserDAO
from src.apps.user.schemas import LoginEmailRequest, Meta, RemoveVoterRequest
from src.apps.user.service import UserService
from src.apps.user.sso_session import create_sso_session
from src.apps.user.utils.security import AuthProvider
from src.common.exceptions import AppException
from src.db_model.user_identity import UserIdentity
from tests.helpers.users import make_user


def _service(session, session_maker, redis) -> UserService:
    return UserService(
        user_dao=UserDAO(session),
        activity_dao=ActivityLogDAO(session_maker),
        email_code_service=None,
        sms_code_service=None,
        redis=redis,
    )


@pytest.mark.asyncio
async def test_bind_sso_creates_qq_identity(session, session_maker, patch_redis):
    user = await make_user(session, email="bind_test@example.com")
    token = AuthProvider.create_session_token(user.id)
    svc = _service(session, session_maker, patch_redis)

    fe = await svc.bind_sso(
        token,
        {"qq_openid": "test-openid-123"},
        Meta(user_ip="9.9.9.9", additional_fingureprint="dev-1"),
    )

    assert fe.email == "bind_test@example.com"
    row = (
        await session.execute(
            select(UserIdentity).where(
                UserIdentity.provider == "qq", UserIdentity.subject == "test-openid-123"
            )
        )
    ).scalar_one()
    assert row.user_id == user.id
    assert row.verified is True
    assert row.created_ip == "9.9.9.9"
    assert row.created_device_id == "dev-1"


@pytest.mark.asyncio
async def test_bind_sso_409_when_openid_taken(session, session_maker, patch_redis):
    await make_user(session, email="owner@example.com", qq="taken-openid")
    thief = await make_user(session, email="thief@example.com")
    svc = _service(session, session_maker, patch_redis)

    with pytest.raises(AppException) as exc_info:
        await svc.bind_sso(
            AuthProvider.create_session_token(thief.id), {"qq_openid": "taken-openid"}
        )
    assert "SSO_ID_ALREADY_BOUND" in str(exc_info.value)
    assert exc_info.value.details == 409


@pytest.mark.asyncio
async def test_bind_sso_is_idempotent_for_same_user(session, session_maker, patch_redis):
    user = await make_user(session, email="same@example.com", qq="mine")
    svc = _service(session, session_maker, patch_redis)

    fe = await svc.bind_sso(AuthProvider.create_session_token(user.id), {"qq_openid": "mine"})

    assert fe.email == "same@example.com"
    rows = (
        await session.execute(select(UserIdentity).where(UserIdentity.provider == "qq"))
    ).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_removed_account_frees_its_sso_identity(user_service, session, patch_redis):
    """Bug fix: soft delete used to leave thbwiki_uid/qq_openid on the row,
    blocking anyone from ever binding that id again."""
    await patch_redis.set("email-verify-gone@example.com", "123456", ex=3600)
    login = await user_service.login_with_email_code(
        LoginEmailRequest(email="gone@example.com", verify_code="123456", meta=Meta())
    )
    user_service.redis = patch_redis
    await user_service.bind_sso(login.session_token, {"thbwiki_uid": "wiki-7"})
    await user_service.remove_voter(
        RemoveVoterRequest(user_token=login.session_token, meta=Meta())
    )

    newcomer = await make_user(session, email="new@example.com")
    fe = await user_service.bind_sso(
        AuthProvider.create_session_token(newcomer.id), {"thbwiki_uid": "wiki-7"}
    )
    assert fe.thbwiki is True


@pytest.mark.asyncio
async def test_login_merges_pending_sso_session(user_service, patch_redis):
    user_service.redis = patch_redis
    sid = await create_sso_session(patch_redis, {"qq_openid": "from-oauth"})
    await patch_redis.set("email-verify-m@example.com", "123456", ex=3600)

    resp = await user_service.login_with_email_code(
        LoginEmailRequest(email="m@example.com", verify_code="123456", meta=Meta(), sid=sid)
    )

    assert resp.session_token
    from src.apps.user.identity import IdentityProvider

    user = await user_service.identities.resolve(IdentityProvider.EMAIL, "m@example.com")
    assert user.identity("qq").subject == "from-oauth"
    assert await patch_redis.get(f"sso-session:{sid}") is None, "sid must be one-shot"


@pytest.mark.asyncio
async def test_login_sso_merge_conflict_does_not_block_login(
    user_service, session, patch_redis
):
    """Spec §5.3: an openid owned by someone else is skipped with a warning
    (previously an IntegrityError → 500 after the sid was already consumed)."""
    user_service.redis = patch_redis
    await make_user(session, email="owner2@example.com", qq="owned")
    sid = await create_sso_session(patch_redis, {"qq_openid": "owned"})
    await patch_redis.set("email-verify-late@example.com", "123456", ex=3600)

    resp = await user_service.login_with_email_code(
        LoginEmailRequest(email="late@example.com", verify_code="123456", meta=Meta(), sid=sid)
    )

    assert resp.session_token
    from src.apps.user.identity import IdentityProvider

    user = await user_service.identities.resolve(IdentityProvider.EMAIL, "late@example.com")
    assert user.identity("qq") is None
