"""CaptchaService gate behaviour matrix + client response parsing (B-043)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.common.aliyun.captcha_client import (
    CaptchaVerifyOutcome,
    _parse_verify_response,
)
from src.common.exceptions import (
    ExternalAPIError,
    ServiceUnavailableError,
    ValidationError,
)
from src.common.verification.captcha import CaptchaService


def _settings(enabled: bool = True, fail_mode: str = "closed") -> SimpleNamespace:
    return SimpleNamespace(
        aliyun_captcha_enabled=enabled,
        aliyun_captcha_fail_mode=fail_mode,
    )


def _client(outcome: CaptchaVerifyOutcome | None = None, error: Exception | None = None):
    client = SimpleNamespace()
    if error is not None:
        client.verify_intelligent_captcha = AsyncMock(side_effect=error)
    else:
        client.verify_intelligent_captcha = AsyncMock(return_value=outcome)
    return client


PASS = CaptchaVerifyOutcome(passed=True, verify_code="T001", request_id="r1")
FAIL = CaptchaVerifyOutcome(passed=False, verify_code="F008", request_id="r2")


@pytest.mark.asyncio
async def test_disabled_is_noop_and_never_calls_aliyun():
    client = _client(error=AssertionError("must not be called"))
    svc = CaptchaService(settings=_settings(enabled=False), client=client)
    await svc.verify_or_raise(None)
    await svc.verify_or_raise("anything")
    client.verify_intelligent_captcha.assert_not_called()


@pytest.mark.asyncio
async def test_enabled_missing_param_raises_captcha_required():
    svc = CaptchaService(settings=_settings(), client=_client(PASS))
    for missing in (None, ""):
        with pytest.raises(ValidationError) as exc:
            await svc.verify_or_raise(missing)
        assert exc.value.message == "CAPTCHA_REQUIRED"


@pytest.mark.asyncio
async def test_enabled_pass_admits():
    client = _client(PASS)
    svc = CaptchaService(settings=_settings(), client=client)
    await svc.verify_or_raise("param")
    client.verify_intelligent_captcha.assert_awaited_once_with("param")


@pytest.mark.asyncio
async def test_enabled_rejected_raises_captcha_failed_with_verify_code():
    svc = CaptchaService(settings=_settings(), client=_client(FAIL))
    with pytest.raises(ValidationError) as exc:
        await svc.verify_or_raise("param")
    assert exc.value.message == "CAPTCHA_FAILED"
    assert exc.value.upstream_response_string == "F008"


@pytest.mark.asyncio
async def test_transport_error_fail_closed_raises_unavailable():
    error = ExternalAPIError("CAPTCHA_UNAVAILABLE", details=502)
    svc = CaptchaService(settings=_settings(fail_mode="closed"), client=_client(error=error))
    with pytest.raises(ServiceUnavailableError) as exc:
        await svc.verify_or_raise("param")
    assert exc.value.message == "CAPTCHA_UNAVAILABLE"


@pytest.mark.asyncio
async def test_transport_error_fail_open_admits():
    error = ExternalAPIError("CAPTCHA_UNAVAILABLE", details=502)
    svc = CaptchaService(settings=_settings(fail_mode="open"), client=_client(error=error))
    await svc.verify_or_raise("param")  # must not raise


# ── client response parsing ──────────────────────────────────────────


def test_parse_pass_response():
    outcome = _parse_verify_response(
        {"result": {"verify_result": True, "verify_code": "T001"}, "request_id": "r1"}
    )
    assert outcome == CaptchaVerifyOutcome(True, "T001", "r1")


def test_parse_rejected_response():
    outcome = _parse_verify_response(
        {"result": {"verify_result": False, "verify_code": "F008"}, "request_id": "r2"}
    )
    assert outcome.passed is False
    assert outcome.verify_code == "F008"


def test_parse_api_error_raises_unavailable():
    with pytest.raises(ExternalAPIError) as exc:
        _parse_verify_response(
            {"code": "InvalidAccessKeyId", "message": "bad ak", "request_id": "r3"}
        )
    assert exc.value.message == "CAPTCHA_UNAVAILABLE"
    assert exc.value.upstream_response_string == "InvalidAccessKeyId"


# ── UserService wiring: gate runs before any code is sent ────────────


@pytest.mark.asyncio
async def test_send_sms_code_gates_before_sending():
    from src.apps.user.schemas import SendSmsCodeRequest
    from src.apps.user.service import UserService

    captcha = SimpleNamespace(
        verify_or_raise=AsyncMock(side_effect=ValidationError("CAPTCHA_REQUIRED"))
    )
    sms = SimpleNamespace(send=AsyncMock())
    service = UserService(
        user_dao=AsyncMock(),
        activity_dao=AsyncMock(),
        email_code_service=SimpleNamespace(send=AsyncMock()),
        sms_code_service=sms,
        captcha_service=captcha,
    )
    with pytest.raises(ValidationError):
        await service.send_sms_code(SendSmsCodeRequest(phone="13800000000"))
    sms.send.assert_not_called()
    captcha.verify_or_raise.assert_awaited_once_with(None)


@pytest.mark.asyncio
async def test_send_email_code_passes_param_through():
    from src.apps.user.schemas import SendEmailCodeRequest
    from src.apps.user.service import UserService

    captcha = SimpleNamespace(verify_or_raise=AsyncMock())
    email = SimpleNamespace(send=AsyncMock())
    service = UserService(
        user_dao=AsyncMock(),
        activity_dao=AsyncMock(),
        email_code_service=email,
        sms_code_service=SimpleNamespace(send=AsyncMock()),
        captcha_service=captcha,
    )
    req = SendEmailCodeRequest(email="a@b.cc", captcha_verify_param="cvp-123")
    await service.send_email_code(req)
    captcha.verify_or_raise.assert_awaited_once_with("cvp-123")
    email.send.assert_awaited_once_with("a@b.cc")
