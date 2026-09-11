"""#29 归一化后登录链路的回归（review 复核，2026-09-12）。

覆盖四条：迁移回填出来的未验证身份在验证码登录后必须被提升为已验证
（否则永远拿不到 vote_token）、密码登录不得在校验口令前泄露封禁状态、
SSO 顺带合并不得静默顶掉已有绑定、Argon2 rehash 必须显式落库。
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from src.apps.user.schemas import (
    LoginEmailPasswordRequest,
    LoginEmailRequest,
    Meta,
)
from src.apps.user.sso_session import create_sso_session
from src.apps.user.utils.security import AuthProvider
from src.common.exceptions import UnauthorizedError, ValidationError
from src.db_model.user import User
from src.db_model.user_identity import UserIdentity
from tests.helpers.users import make_user

META = Meta(user_ip="203.0.113.7", additional_fingureprint="device-A")


async def _login_email_code(user_service, patch_redis, email):
    await patch_redis.set(f"email-verify-{email}", "123456", ex=3600)
    return await user_service.login_with_email_code(
        LoginEmailRequest(email=email, verify_code="123456", meta=META)
    )


@pytest.mark.asyncio
async def test_code_login_promotes_unverified_identity(
    user_service, patch_redis, session
):
    """迁移 0018 从 legacy email_verified=false 回填出的身份，验证码登录后
    必须变成已验证——否则 _maybe_sign_vote_token 永远返回 ""，账号能登录
    但静默投不了票，且任何地方都不报错。"""
    user = await make_user(
        session, email="unverified@example.com", nickname="n", verified=False
    )
    assert user.identity("email").verified is False

    resp = await _login_email_code(user_service, patch_redis, "unverified@example.com")

    identity = (await session.execute(
        select(UserIdentity)
        .where(UserIdentity.user_id == user.id, UserIdentity.provider == "email")
        .execution_options(populate_existing=True)
    )).scalar_one()
    assert identity.verified is True, "验证码登录已证明该邮箱可达，必须提升为已验证"
    assert identity.verified_at is not None
    assert resp.vote_token, "已验证的 email 身份应当拿得到 vote_token"


@pytest.mark.asyncio
async def test_password_login_does_not_leak_ban_status(user_service, session):
    """封禁账号 + 错误口令，必须与"邮箱不存在"给出同样的 INCORRECT_PASSWORD，
    否则未认证的攻击者能在不知道口令的前提下枚举出哪些邮箱属于封禁账号。"""
    await make_user(
        session, email="banned@example.com", password="correct-horse", removed=True
    )

    with pytest.raises(ValidationError) as got:
        await user_service.login_with_email_password(
            LoginEmailPasswordRequest(
                email="banned@example.com", password="wrong", meta=META
            )
        )
    assert got.value.message == "INCORRECT_PASSWORD"

    with pytest.raises(ValidationError) as unknown:
        await user_service.login_with_email_password(
            LoginEmailPasswordRequest(
                email="nobody@example.com", password="wrong", meta=META
            )
        )
    assert unknown.value.message == got.value.message


@pytest.mark.asyncio
async def test_password_login_reports_ban_when_password_correct(user_service, session):
    """口令正确时才允许告知封禁——这是账号主人应得的信息。"""
    await make_user(
        session, email="banned2@example.com", password="correct-horse", removed=True
    )
    with pytest.raises(UnauthorizedError) as got:
        await user_service.login_with_email_password(
            LoginEmailPasswordRequest(
                email="banned2@example.com", password="correct-horse", meta=META
            )
        )
    assert got.value.message == "USER_REMOVED"


@pytest.mark.asyncio
async def test_sso_merge_does_not_replace_existing_binding(
    user_service, patch_redis, session
):
    """登录顺带的 SSO 合并是"补绑"，不是"改绑"：账号已有 qq 绑定时，
    带着另一个 openid 的 sid 登录不得把原绑定顶掉（原 openid 会被释放，
    任何人都能去认领），而 bind() 的语义恰恰是替换。"""
    user = await make_user(session, email="sso@example.com", qq="openid-original")
    user_service.redis = patch_redis
    sid = await create_sso_session(patch_redis, {"qq_openid": "openid-hijack"})

    await patch_redis.set("email-verify-sso@example.com", "123456", ex=3600)
    await user_service.login_with_email_code(
        LoginEmailRequest(
            email="sso@example.com", verify_code="123456", meta=META, sid=sid
        )
    )

    identity = (await session.execute(
        select(UserIdentity)
        .where(UserIdentity.user_id == user.id, UserIdentity.provider == "qq")
        .execution_options(populate_existing=True)
    )).scalar_one()
    assert identity.subject == "openid-original", "已有 qq 绑定被登录路径静默顶掉了"


@pytest.mark.asyncio
async def test_sso_merge_still_binds_when_slot_is_free(
    user_service, patch_redis, session
):
    """没有已有绑定时，补绑照常发生（不要把修复做成"整个不绑了"）。"""
    user = await make_user(session, email="sso2@example.com")
    user_service.redis = patch_redis
    sid = await create_sso_session(patch_redis, {"qq_openid": "openid-new"})

    await patch_redis.set("email-verify-sso2@example.com", "123456", ex=3600)
    await user_service.login_with_email_code(
        LoginEmailRequest(
            email="sso2@example.com", verify_code="123456", meta=META, sid=sid
        )
    )

    identity = (await session.execute(
        select(UserIdentity)
        .where(UserIdentity.user_id == user.id, UserIdentity.provider == "qq")
        .execution_options(populate_existing=True)
    )).scalar_one()
    assert identity.subject == "openid-new"


@pytest.mark.asyncio
async def test_password_rehash_is_persisted(user_service, session, monkeypatch):
    """Argon2 参数升级后重算的 hash 必须显式落库，不能指望
    touch_login 顺手 save（它在 identity 缺失时会提前 return）。"""
    from src.common.security.password import PasswordVerificationResult

    user = await make_user(session, email="rehash@example.com", password="pw")
    old_hash = user.password_hash
    new_hash = AuthProvider.hash_password("pw-upgraded-params")

    monkeypatch.setattr(
        AuthProvider,
        "verify_password",
        staticmethod(
            lambda password, hashed: PasswordVerificationResult(
                valid=True, needs_rehash=True, upgraded_hash=new_hash
            )
        ),
    )

    await user_service.login_with_email_password(
        LoginEmailPasswordRequest(email="rehash@example.com", password="pw", meta=META)
    )

    row = (await session.execute(
        select(User).where(User.id == user.id)
        .execution_options(populate_existing=True)
    )).scalar_one()
    assert row.password_hash == new_hash != old_hash
