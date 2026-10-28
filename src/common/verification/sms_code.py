"""SMS verification code service — thin layer over Aliyun PNVS.

Aliyun PNVS owns the entire code lifecycle (generation, storage, TTL,
per-phone send-interval throttling).  This service just orchestrates the
two PNVS calls (send / check) and translates the result into our domain
exceptions.

Successfully sent calls return a ``biz_id`` that the caller may write to
ActivityLog for traceability — the plaintext code never enters our
process.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

from src.common.aliyun.pnvs_client import (
    AliyunPnvsClient,
    PnvsSendResult,
    get_pnvs_client,
)
from src.common.exceptions import ValidationError

logger = logging.getLogger(__name__)


@dataclass
class SmsCodeService:
    """Send and verify SMS codes via Aliyun PNVS."""

    pnvs_client: AliyunPnvsClient

    async def send(self, phone: str) -> PnvsSendResult:
        """Trigger PNVS to send a verification code; returns send-result metadata."""
        return await self.pnvs_client.send_sms_verify_code(phone)

    async def consume(self, phone: str, submitted_code: str) -> None:
        """Verify *submitted_code*; raises ValidationError("INCORRECT_VERIFY_CODE")
        on mismatch / expiry / already-consumed.

        PNVS' ``CheckSmsVerifyCode`` is itself one-shot — re-checking the
        same passed code returns UNKNOWN — so no extra bookkeeping needed
        on our side.
        """
        result = await self.pnvs_client.check_sms_verify_code(phone, submitted_code)
        if not result.passed:
            raise ValidationError("INCORRECT_VERIFY_CODE", details=400)


@lru_cache(maxsize=1)
def get_sms_code_service() -> SmsCodeService:
    """Return the process-wide SmsCodeService singleton."""
    return SmsCodeService(pnvs_client=get_pnvs_client())
