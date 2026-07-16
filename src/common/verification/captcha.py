"""CAPTCHA gate for verification-code sending (B-043).

``CaptchaService.verify_or_raise`` is the single choke point: both the
GraphQL mutations (requestPhoneCode/requestEmailCode) and the REST
endpoints (send-sms-code/send-email-code) reach it through
``UserService.send_*_code``, so enabling the gate closes every entrance
at once.

Behaviour matrix (see docs/superpowers/specs/2026-07-16-captcha-anti-abuse-design.md):
- ALIYUN_CAPTCHA_ENABLED=false  -> no-op (pre-captcha behaviour).
- enabled, param missing        -> ValidationError CAPTCHA_REQUIRED.
- enabled, Aliyun says fail     -> ValidationError CAPTCHA_FAILED.
- enabled, Aliyun unreachable   -> FAIL_MODE closed (default): CAPTCHA_UNAVAILABLE;
                                   FAIL_MODE open: admit with a warning log.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING, Optional

from src.common.config import get_settings
from src.common.exceptions import (
    AppException,
    ServiceUnavailableError,
    ValidationError,
)

if TYPE_CHECKING:  # pragma: no cover
    from src.common.aliyun.captcha_client import AliyunCaptchaClient
    from src.common.config import Settings

logger = logging.getLogger(__name__)


class CaptchaService:
    """Enforce human verification before sending a verification code."""

    def __init__(
        self,
        settings: "Settings | None" = None,
        client: "AliyunCaptchaClient | None" = None,
    ) -> None:
        self._settings = settings or get_settings()
        if client is None:
            from src.common.aliyun.captcha_client import get_captcha_client

            client = get_captcha_client()
        self._client = client

    async def verify_or_raise(self, captcha_verify_param: Optional[str]) -> None:
        s = self._settings
        if not s.aliyun_captcha_enabled:
            return

        if not captcha_verify_param:
            raise ValidationError("CAPTCHA_REQUIRED", details=400)

        try:
            outcome = await self._client.verify_intelligent_captcha(
                captcha_verify_param
            )
        except AppException as exc:
            # Transport failure / API-level error / misconfiguration — the
            # human was never judged.  closed(默认): reject; open: admit.
            if s.aliyun_captcha_fail_mode == "open":
                logger.warning(
                    "CAPTCHA unavailable (%s); FAIL_MODE=open admits request",
                    exc.message,
                )
                return
            raise ServiceUnavailableError("CAPTCHA_UNAVAILABLE", details=503) from exc

        if not outcome.passed:
            raise ValidationError(
                "CAPTCHA_FAILED", details=400,
                upstream_response_string=outcome.verify_code,
            )


@lru_cache(maxsize=1)
def get_captcha_service() -> CaptchaService:
    """Return the process-wide CaptchaService singleton."""
    return CaptchaService()
