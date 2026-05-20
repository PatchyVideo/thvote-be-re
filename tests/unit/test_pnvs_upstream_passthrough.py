import pytest

from src.common.aliyun.pnvs_client import _parse_send_response
from src.common.exceptions import ExternalAPIError, RateLimitError, ValidationError


class _Body:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Resp:
    def __init__(self, body):
        self.body = body


def test_rate_limit_failure_passes_upstream_code():
    resp = _Resp(_Body(code="isv.BUSINESS_LIMIT_CONTROL", message="too many", request_id="r1"))
    with pytest.raises(RateLimitError) as ei:
        _parse_send_response(resp)
    assert ei.value.message == "REQUEST_TOO_FREQUENT"
    assert ei.value.upstream_response_string == "isv.BUSINESS_LIMIT_CONTROL"
    assert ei.value.error_message == "too many"


def test_biz_frequency_maps_to_rate_limit():
    # PNVS 同号码发送频控码 biz.FREQUENCY → REQUEST_TOO_FREQUENT(前端显示"请求过于频繁")
    resp = _Resp(_Body(code="biz.FREQUENCY", message="check frequency failed", request_id="r9"))
    with pytest.raises(RateLimitError) as ei:
        _parse_send_response(resp)
    assert ei.value.message == "REQUEST_TOO_FREQUENT"
    assert ei.value.upstream_response_string == "biz.FREQUENCY"
    assert ei.value.error_message == "check frequency failed"


def test_invalid_phone_passes_upstream_code():
    resp = _Resp(_Body(code="isv.MOBILE_NUMBER_ILLEGAL", message="bad", request_id="r2"))
    with pytest.raises(ValidationError) as ei:
        _parse_send_response(resp)
    assert ei.value.message == "INVALID_PHONE"
    assert ei.value.upstream_response_string == "isv.MOBILE_NUMBER_ILLEGAL"


def test_unknown_failure_is_sms_send_failed_with_upstream():
    resp = _Resp(_Body(code="isv.SOMETHING_ELSE", message="boom", request_id="r3"))
    with pytest.raises(ExternalAPIError) as ei:
        _parse_send_response(resp)
    assert ei.value.message == "SMS_SEND_FAILED"
    assert ei.value.upstream_response_string == "isv.SOMETHING_ELSE"
    assert ei.value.error_message == "boom"


@pytest.mark.asyncio
async def test_transport_failure_does_not_leak_exception_detail(monkeypatch):
    """A raw SDK/network exception must NOT be surfaced to API consumers.

    The provider `code`/`message` (test above) is safe to pass through, but
    the raw transport exception string can contain internal URLs / SDK
    diagnostics — it belongs only in logs, not in error extensions.
    """
    from types import SimpleNamespace

    from src.common.aliyun.pnvs_client import AliyunPnvsClient
    from src.common.config import get_settings

    settings = get_settings().model_copy(
        update={
            "aliyun_pnvs_access_key_id": "id",
            "aliyun_pnvs_access_key_secret": "secret",
            "aliyun_pnvs_endpoint": "host",
            "aliyun_pnvs_sms_sign_name": "sign",
            "aliyun_pnvs_sms_template_code": "tpl",
        }
    )
    client = AliyunPnvsClient(settings)

    def boom(request):
        raise RuntimeError("internal-host://secret-sdk-detail")

    monkeypatch.setattr(
        client, "_ensure_client", lambda: SimpleNamespace(send_sms_verify_code=boom)
    )

    with pytest.raises(ExternalAPIError) as ei:
        await client.send_sms_verify_code("13800000000")
    assert ei.value.message == "SMS_SEND_FAILED"
    assert ei.value.error_message is None
    assert "secret-sdk-detail" not in (ei.value.error_message or "")
