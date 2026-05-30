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
