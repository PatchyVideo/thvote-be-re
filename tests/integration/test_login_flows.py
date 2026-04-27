"""End-to-end-ish login tests against an in-memory sqlite + fakeredis.

Aliyun is mocked at the client level (see conftest.fake_pnvs / fake_smtp).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.apps.user.schemas import (
    LoginEmailPasswordRequest,
    LoginEmailRequest,
    LoginPhoneRequest,
    Meta,
    SendEmailCodeRequest,
    SendSmsCodeRequest,
)
from src.common.exceptions import RateLimitError, ValidationError
from src.db_model.activity_log import ActivityLog
from src.db_model.user import User


@pytest.mark.asyncio
async def test_send_email_code_writes_redis_and_logs(user_service, patch_redis, session_maker):
    await user_service.send_email_code(
        SendEmailCodeRequest(email="alice@example.com", meta=Meta(user_ip="1.1.1.1"))
    )

    code = await patch_redis.get("email-verify-alice@example.com")
    assert code is not None and code.isdigit() and len(code) == 6
    guard = await patch_redis.get("email-verify-guard-alice@example.com")
    assert guard == "guard"

    # Audit row exists
    async with session_maker() as s:
        rows = (await s.execute(select(ActivityLog))).scalars().all()
    assert any(r.event_type == "send_email" for r in rows)


@pytest.mark.asyncio
async def test_send_email_code_guard_blocks_duplicate(user_service):
    req = SendEmailCodeRequest(email="alice@example.com", meta=Meta())
    await user_service.send_email_code(req)
    with pytest.raises(RateLimitError):
        await user_service.send_email_code(req)


@pytest.mark.asyncio
async def test_login_email_creates_new_user_then_logs_existing(user_service, patch_redis):
    # Simulate the code being sent
    await patch_redis.set("email-verify-bob@example.com", "111111", ex=3600)

    response = await user_service.login_with_email_code(
        LoginEmailRequest(
            email="bob@example.com",
            nickname="bob",
            verify_code="111111",
            meta=Meta(user_ip="2.2.2.2"),
        )
    )
    assert response.user.email == "bob@example.com"
    assert response.user.username == "bob"
    assert response.session_token  # non-empty
    assert response.user.password is False  # never set a password

    # Second login: must reuse the same user_id
    await patch_redis.set("email-verify-bob@example.com", "222222", ex=3600)
    response2 = await user_service.login_with_email_code(
        LoginEmailRequest(
            email="bob@example.com",
            nickname="ignored",
            verify_code="222222",
            meta=Meta(),
        )
    )
    assert response2.user.email == "bob@example.com"


@pytest.mark.asyncio
async def test_login_email_wrong_code_rejected(user_service, patch_redis):
    await patch_redis.set("email-verify-x@example.com", "111111", ex=3600)
    with pytest.raises(ValidationError):
        await user_service.login_with_email_code(
            LoginEmailRequest(
                email="x@example.com",
                verify_code="222222",
                meta=Meta(),
            )
        )


@pytest.mark.asyncio
async def test_login_phone_creates_user_via_pnvs(user_service, fake_pnvs):
    req = SendSmsCodeRequest(phone="13800000001", meta=Meta())
    await user_service.send_sms_code(req)
    fake_pnvs.send_sms_verify_code.assert_awaited_once()

    response = await user_service.login_with_phone_code(
        LoginPhoneRequest(
            phone="13800000001",
            nickname="carol",
            verify_code="999999",
            meta=Meta(),
        )
    )
    fake_pnvs.check_sms_verify_code.assert_awaited_once()
    assert response.user.phone == "13800000001"


@pytest.mark.asyncio
async def test_login_email_password_rejects_unknown_account(user_service):
    with pytest.raises(ValidationError):
        await user_service.login_with_email_password(
            LoginEmailPasswordRequest(
                email="ghost@example.com",
                password="anything",
                meta=Meta(),
            )
        )
