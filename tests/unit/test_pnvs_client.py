"""PNVS response-parsing unit tests (no SDK calls).

We bypass _ensure_client by patching it; the real test target is the
_parse_send_response / _parse_check_response logic and the dispatcher
that translates Aliyun error codes into our domain exceptions.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.common.aliyun.pnvs_client import (
    AliyunPnvsClient,
    PnvsResult,
    _parse_check_response,
    _parse_send_response,
)
from src.common.exceptions import ExternalAPIError, RateLimitError, ValidationError


def _ok_send_response(biz_id: str = "BIZ123") -> SimpleNamespace:
    return SimpleNamespace(
        body=SimpleNamespace(
            code="OK",
            request_id="req-1",
            message="ok",
            model=SimpleNamespace(biz_id=biz_id),
        )
    )


def _failed_send_response(code: str) -> SimpleNamespace:
    return SimpleNamespace(
        body=SimpleNamespace(
            code=code,
            request_id="req-1",
            message="failure",
            model=None,
        )
    )


def test_parse_send_ok() -> None:
    result = _parse_send_response(_ok_send_response("BIZ-77"))
    assert result.biz_id == "BIZ-77"
    assert result.request_id == "req-1"


def test_parse_send_invalid_phone() -> None:
    with pytest.raises(ValidationError) as exc:
        _parse_send_response(_failed_send_response("isv.MOBILE_NUMBER_ILLEGAL"))
    assert exc.value.message == "INVALID_PHONE"


def test_parse_send_rate_limited() -> None:
    with pytest.raises(RateLimitError) as exc:
        _parse_send_response(_failed_send_response("isv.BUSINESS_LIMIT_CONTROL"))
    assert exc.value.message == "REQUEST_TOO_FREQUENT"


def test_parse_send_unknown_failure() -> None:
    with pytest.raises(ExternalAPIError) as exc:
        _parse_send_response(_failed_send_response("isv.UNKNOWN_INTERNAL"))
    assert exc.value.message == "SMS_SEND_FAILED"


def test_parse_check_pass() -> None:
    response = SimpleNamespace(
        body=SimpleNamespace(
            code="OK",
            request_id="req-2",
            message="",
            model=SimpleNamespace(verify_result="PASS"),
        )
    )
    result: PnvsResult = _parse_check_response(response)
    assert result.passed is True


def test_parse_check_unknown_returns_failed_passed() -> None:
    response = SimpleNamespace(
        body=SimpleNamespace(
            code="OK",
            request_id="req-3",
            message="",
            model=SimpleNamespace(verify_result="UNKNOWN"),
        )
    )
    assert _parse_check_response(response).passed is False


def test_parse_check_api_failure_raises() -> None:
    response = SimpleNamespace(
        body=SimpleNamespace(
            code="isv.SOMETHING_WRONG",
            request_id="req-4",
            message="oops",
            model=None,
        )
    )
    with pytest.raises(ExternalAPIError):
        _parse_check_response(response)


@pytest.mark.asyncio
async def test_send_sms_verify_code_dispatches(monkeypatch) -> None:
    """Smoke test the orchestration: build request, call client, parse."""
    from src.common.config import get_settings

    s = get_settings()
    s_with_keys = s.model_copy(
        update={
            "aliyun_pnvs_access_key_id": "id",
            "aliyun_pnvs_access_key_secret": "secret",
            "aliyun_pnvs_endpoint": "host",
            "aliyun_pnvs_sms_sign_name": "sign",
            "aliyun_pnvs_sms_template_code": "tpl",
        }
    )
    client = AliyunPnvsClient(s_with_keys)
    captured = {}

    def fake_send_sms_verify_code(request):
        captured["request"] = request
        return _ok_send_response("BIZ-OK")

    fake_inner = SimpleNamespace(send_sms_verify_code=fake_send_sms_verify_code)
    monkeypatch.setattr(client, "_ensure_client", lambda: fake_inner)

    result = await client.send_sms_verify_code("13800000000")

    assert result.biz_id == "BIZ-OK"
    req = captured["request"]
    assert req.phone_number == "13800000000"
    assert req.return_verify_code is False
