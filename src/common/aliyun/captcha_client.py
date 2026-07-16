"""Aliyun CAPTCHA 2.0 client (VerifyIntelligentCaptcha).

Server-side second verification for the frontend ``captchaVerifyParam``
(B-043).  The param is single-use with Aliyun-side replay protection
(VerifyCode ``F008``); we only trust ``VerifyResult`` returned by this
API — never the mere presence of the param in a request.

References:
- https://help.aliyun.com/zh/captcha/captcha2-0/user-guide/server-access
- PyPI: alibabacloud-captcha20230305
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from src.common.config import Settings, get_settings
from src.common.exceptions import AppException, ExternalAPIError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CaptchaVerifyOutcome:
    """Outcome of a VerifyIntelligentCaptcha call."""

    passed: bool
    verify_code: str | None  # T001=pass, F001..F025=fail reasons (F008=replay)
    request_id: str | None


class AliyunCaptchaClient:
    """Thin wrapper around the alibabacloud_captcha20230305 SDK.

    Construct via ``get_captcha_client()``; tests should patch that getter
    or the methods on this class.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Any | None = None  # lazy-init to avoid SDK import at import-time

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client

        if not (
            self._settings.aliyun_captcha_access_key_id
            and self._settings.aliyun_captcha_access_key_secret
            and self._settings.aliyun_captcha_endpoint
        ):
            raise AppException("ALIYUN_NOT_CONFIGURED", details=500)

        # Lazy import so the SDK isn't required at module-load time
        # (e.g. for unit tests that mock this whole class).
        from alibabacloud_captcha20230305.client import Client as CaptchaSdkClient
        from alibabacloud_tea_openapi import models as open_api_models

        config = open_api_models.Config(
            access_key_id=self._settings.aliyun_captcha_access_key_id,
            access_key_secret=self._settings.aliyun_captcha_access_key_secret,
            endpoint=self._settings.aliyun_captcha_endpoint,
        )
        self._client = CaptchaSdkClient(config)
        return self._client

    async def verify_intelligent_captcha(
        self, captcha_verify_param: str
    ) -> CaptchaVerifyOutcome:
        """Second-verify a frontend ``captchaVerifyParam`` against Aliyun.

        Returns CaptchaVerifyOutcome(passed=True/False) for a completed
        judgement.  Raises ExternalAPIError("CAPTCHA_UNAVAILABLE") for
        transport failures or malformed API responses — the caller
        (CaptchaService) decides fail-open/closed.
        """
        from alibabacloud_captcha20230305 import models as captcha_models

        request = captcha_models.VerifyIntelligentCaptchaRequest(
            captcha_verify_param=captcha_verify_param,
            scene_id=self._settings.aliyun_captcha_scene_id_send_code or None,
        )
        client = self._ensure_client()
        try:
            response = await _async_call(
                client.verify_intelligent_captcha, request
            )
        except Exception as exc:  # SDK / network failures
            # Log the raw exception for diagnosis; don't surface str(exc)
            # to API consumers (may leak internal URLs / SDK details).
            logger.exception("CAPTCHA verify_intelligent_captcha transport failure")
            raise ExternalAPIError("CAPTCHA_UNAVAILABLE", details=502) from exc

        return _parse_verify_response(response)


def _parse_verify_response(response: Any) -> CaptchaVerifyOutcome:
    """Map a raw SDK response into CaptchaVerifyOutcome."""
    body = getattr(response, "body", None) or response
    request_id = _attr(body, "request_id")
    result = _attr(body, "result")

    if result is None:
        # API-level error (bad AK, unknown scene, quota...) — not a human
        # judgement.  Treat as service unavailability, not a failed check.
        code = _attr(body, "code")
        message = _attr(body, "message") or "unknown"
        logger.error(
            "CAPTCHA verify API failed: code=%s message=%s request_id=%s",
            code,
            message,
            request_id,
        )
        raise ExternalAPIError(
            "CAPTCHA_UNAVAILABLE", details=502,
            error_message=message, upstream_response_string=code,
        )

    verify_code = _attr(result, "verify_code")
    passed = bool(_attr(result, "verify_result"))
    if not passed:
        logger.info(
            "CAPTCHA verify rejected: verify_code=%s request_id=%s",
            verify_code,
            request_id,
        )
    return CaptchaVerifyOutcome(
        passed=passed, verify_code=verify_code, request_id=request_id
    )


def _attr(obj: Any, name: str) -> Any:
    """Read attribute or dict key, returning None if absent."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


async def _async_call(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a (possibly sync) SDK call without blocking the event loop."""
    import asyncio
    import inspect

    if inspect.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    return await asyncio.to_thread(func, *args, **kwargs)


@lru_cache(maxsize=1)
def get_captcha_client() -> AliyunCaptchaClient:
    """Return the process-wide CAPTCHA client singleton."""
    return AliyunCaptchaClient(get_settings())
