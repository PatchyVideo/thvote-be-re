"""Send-code rate limiting wiring (B-043): per-IP before captcha, per-phone after.

The choke is in UserService.send_*_code so both the GraphQL mutations and the
REST endpoints are covered at once. rate_limit raises HTTPException(429,
REQUEST_TOO_FREQUENT), which map_app_errors turns into the error_kind the
frontend expects.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

import src.apps.user.service as service_mod
from src.apps.user.schemas import SendEmailCodeRequest, SendSmsCodeRequest
from src.apps.user.service import UserService


def _service(captcha=None):
    sms = SimpleNamespace(send=AsyncMock(return_value=SimpleNamespace(biz_id="b")))
    return UserService(
        user_dao=AsyncMock(),
        activity_dao=AsyncMock(),
        email_code_service=SimpleNamespace(send=AsyncMock()),
        sms_code_service=sms,
        captcha_service=captcha or SimpleNamespace(verify_or_raise=AsyncMock()),
    )


def _sms_req(ip="1.2.3.4", phone="13800000000"):
    return SendSmsCodeRequest(
        phone=phone, captcha_verify_param="cvp", meta={"user_ip": ip}
    )


def _email_req(ip="1.2.3.4"):
    return SendEmailCodeRequest(
        email="a@b.cc", captcha_verify_param="cvp", meta={"user_ip": ip}
    )


@pytest.mark.asyncio
async def test_sms_order_ip_then_captcha_then_phone(monkeypatch):
    calls = []
    monkeypatch.setattr(
        service_mod, "rate_limit",
        AsyncMock(side_effect=lambda uid, **kw: calls.append(("ratelimit", uid))),
    )
    captcha = SimpleNamespace(
        verify_or_raise=AsyncMock(side_effect=lambda p: calls.append(("captcha", p)))
    )
    svc = _service(captcha)
    await svc.send_sms_code(_sms_req())
    kinds = [c[0] for c in calls]
    # per-IP limit BEFORE captcha (protects Aliyun captcha cost), per-phone AFTER
    assert kinds == ["ratelimit", "captcha", "ratelimit"]
    assert calls[0][1] == "sendcode-ip-1.2.3.4"
    assert calls[2][1] == "sendcode-phone-13800000000"


@pytest.mark.asyncio
async def test_email_ip_limit_before_captcha(monkeypatch):
    calls = []
    monkeypatch.setattr(
        service_mod, "rate_limit",
        AsyncMock(side_effect=lambda uid, **kw: calls.append(("ratelimit", uid))),
    )
    captcha = SimpleNamespace(
        verify_or_raise=AsyncMock(side_effect=lambda p: calls.append(("captcha", p)))
    )
    svc = _service(captcha)
    await svc.send_email_code(_email_req())
    assert [c[0] for c in calls] == ["ratelimit", "captcha"]
    assert calls[0][1] == "sendcode-ip-1.2.3.4"


@pytest.mark.asyncio
async def test_ip_flood_blocked_before_captcha_and_send(monkeypatch):
    """An IP over its budget is rejected without a captcha call or an SMS send."""
    monkeypatch.setattr(
        service_mod, "rate_limit",
        AsyncMock(side_effect=HTTPException(429, detail="REQUEST_TOO_FREQUENT")),
    )
    captcha = SimpleNamespace(verify_or_raise=AsyncMock())
    svc = _service(captcha)
    with pytest.raises(HTTPException) as exc:
        await svc.send_sms_code(_sms_req(ip="9.9.9.9"))
    assert exc.value.status_code == 429
    assert exc.value.detail == "REQUEST_TOO_FREQUENT"
    captcha.verify_or_raise.assert_not_called()
    svc.sms_code_service.send.assert_not_called()


@pytest.mark.asyncio
async def test_missing_ip_uses_unknown_bucket(monkeypatch):
    seen = []
    monkeypatch.setattr(
        service_mod, "rate_limit",
        AsyncMock(side_effect=lambda uid, **kw: seen.append(uid)),
    )
    svc = _service()
    await svc.send_email_code(SendEmailCodeRequest(email="a@b.cc"))
    assert seen[0] == "sendcode-ip-unknown"
