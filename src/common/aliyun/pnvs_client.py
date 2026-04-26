"""Aliyun Phone Number Verification Service (PNVS) client.

Wraps SendSmsVerifyCode + CheckSmsVerifyCode from the PNVS API
(alibabacloud_dypnsapi20170525).  The verification code lifecycle, TTL,
and per-phone send interval are managed entirely by Aliyun — nothing is
stored in our Redis.

References:
- https://help.aliyun.com/zh/pnvs/developer-reference/api-dypnsapi-2017-05-25-sendsmsverifycode
- https://help.aliyun.com/zh/pnvs/developer-reference/api-dypnsapi-2017-05-25-checksmsverifycode
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from src.common.config import Settings, get_settings
from src.common.exceptions import (
    AppException,
    ExternalAPIError,
    RateLimitError,
    ValidationError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PnvsSendResult:
    """Outcome of a SendSmsVerifyCode call."""

    biz_id: str | None
    request_id: str | None


@dataclass(frozen=True)
class PnvsResult:
    """Outcome of a CheckSmsVerifyCode call."""

    passed: bool
    request_id: str | None


class AliyunPnvsClient:
    """Thin wrapper around the alibabacloud_dypnsapi20170525 SDK.

    Construct via ``get_pnvs_client()``; tests should patch that getter
    or the methods on this class.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Any | None = None  # lazy-init to avoid SDK import at import-time

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client

        if not (
            self._settings.aliyun_pnvs_access_key_id
            and self._settings.aliyun_pnvs_access_key_secret
            and self._settings.aliyun_pnvs_endpoint
        ):
            raise AppException("ALIYUN_NOT_CONFIGURED", details=500)

        # Lazy import so the SDK isn't required at module-load time
        # (e.g. for unit tests that mock this whole class).
        from alibabacloud_dypnsapi20170525.client import Client as DypnsapiClient
        from alibabacloud_tea_openapi import models as open_api_models

        config = open_api_models.Config(
            access_key_id=self._settings.aliyun_pnvs_access_key_id,
            access_key_secret=self._settings.aliyun_pnvs_access_key_secret,
            endpoint=self._settings.aliyun_pnvs_endpoint,
        )
        if self._settings.aliyun_pnvs_region_id:
            config.region_id = self._settings.aliyun_pnvs_region_id
        self._client = DypnsapiClient(config)
        return self._client

    async def send_sms_verify_code(self, phone: str) -> PnvsSendResult:
        """Send a verification code to *phone* via PNVS.

        Raises ValidationError("INVALID_PHONE") for malformed numbers,
        RateLimitError("REQUEST_TOO_FREQUENT") for Aliyun-side throttling,
        ExternalAPIError("SMS_SEND_FAILED") for transport / unknown errors.
        """
        s = self._settings
        if not (s.aliyun_pnvs_sms_sign_name and s.aliyun_pnvs_sms_template_code):
            raise AppException("ALIYUN_NOT_CONFIGURED", details=500)

        from alibabacloud_dypnsapi20170525 import models as dypnsapi_models

        request = dypnsapi_models.SendSmsVerifyCodeRequest(
            phone_number=phone,
            sign_name=s.aliyun_pnvs_sms_sign_name,
            template_code=s.aliyun_pnvs_sms_template_code,
            template_param='{"code":"##code##"}',
            scheme_name=s.aliyun_pnvs_scheme_name or None,
            code_length=s.aliyun_pnvs_code_length,
            valid_time=s.aliyun_pnvs_valid_time,
            interval=s.aliyun_pnvs_interval,
            return_verify_code=False,
        )

        client = self._ensure_client()
        try:
            response = await _async_call(client.send_sms_verify_code, request)
        except Exception as exc:  # SDK / network failures
            logger.exception("PNVS send_sms_verify_code transport failure")
            raise ExternalAPIError("SMS_SEND_FAILED", details=502) from exc

        return _parse_send_response(response)

    async def check_sms_verify_code(self, phone: str, code: str) -> PnvsResult:
        """Verify *code* against PNVS.

        Returns PnvsResult(passed=True/False).  passed=False covers wrong
        code / expired / already-consumed (Aliyun returns VerifyResult="UNKNOWN").
        Raises ExternalAPIError on transport-level failures.
        """
        from alibabacloud_dypnsapi20170525 import models as dypnsapi_models

        request = dypnsapi_models.CheckSmsVerifyCodeRequest(
            phone_number=phone,
            verify_code=code,
            scheme_name=self._settings.aliyun_pnvs_scheme_name or None,
        )
        client = self._ensure_client()
        try:
            response = await _async_call(client.check_sms_verify_code, request)
        except Exception as exc:
            logger.exception("PNVS check_sms_verify_code transport failure")
            raise ExternalAPIError("SMS_SEND_FAILED", details=502) from exc

        return _parse_check_response(response)


def _parse_send_response(response: Any) -> PnvsSendResult:
    """Map a raw SDK response into PnvsSendResult, raising on failure codes."""
    body = getattr(response, "body", None) or response
    code = _attr(body, "code")
    request_id = _attr(body, "request_id")

    if code == "OK":
        model = _attr(body, "model")
        return PnvsSendResult(biz_id=_attr(model, "biz_id"), request_id=request_id)

    message = _attr(body, "message") or "unknown"
    logger.error(
        "PNVS send failed: code=%s message=%s request_id=%s",
        code, message, request_id,
    )
    if code in {"isv.MOBILE_NUMBER_ILLEGAL", "isv.MOBILE_COUNTRY_NOT_SUPPORTED"}:
        raise ValidationError("INVALID_PHONE", details=400)
    if code in {
        "isv.BUSINESS_LIMIT_CONTROL",
        "isv.OUT_OF_SERVICE",
        "isv.SMS_TEST_NUMBER_NOT_LOGIN",
    } or (code or "").endswith("_LIMIT_CONTROL"):
        raise RateLimitError("REQUEST_TOO_FREQUENT", details=429)
    raise ExternalAPIError("SMS_SEND_FAILED", details=502)


def _parse_check_response(response: Any) -> PnvsResult:
    """Map a raw SDK response into PnvsResult."""
    body = getattr(response, "body", None) or response
    code = _attr(body, "code")
    request_id = _attr(body, "request_id")

    if code != "OK":
        message = _attr(body, "message") or "unknown"
        logger.error(
            "PNVS check API failed: code=%s message=%s request_id=%s",
            code, message, request_id,
        )
        raise ExternalAPIError("SMS_SEND_FAILED", details=502)

    model = _attr(body, "model")
    verify_result = _attr(model, "verify_result")
    return PnvsResult(passed=(verify_result == "PASS"), request_id=request_id)


def _attr(obj: Any, name: str) -> Any:
    """Read attribute or dict key, returning None if absent."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


async def _async_call(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a (possibly sync) SDK call without blocking the event loop.

    The PNVS SDK exposes both sync (``send_sms_verify_code``) and async
    (``send_sms_verify_code_async``) variants on the same class.  We
    detect which we got and dispatch accordingly: coroutine functions
    are awaited directly, plain callables run in a worker thread.
    """
    import asyncio
    import inspect

    if inspect.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    return await asyncio.to_thread(func, *args, **kwargs)


@lru_cache(maxsize=1)
def get_pnvs_client() -> AliyunPnvsClient:
    """Return the process-wide PNVS client singleton."""
    return AliyunPnvsClient(get_settings())
