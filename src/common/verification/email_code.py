"""Email verification code service.

Mirrors Rust user-manager behavior:
    code key:   email-verify-{email}        TTL 3600s
    guard key:  email-verify-guard-{email}  TTL 120s

The guard prevents resends within 120s; the code itself lives for 1 hour
to give users time to switch tabs / open mail clients.

Codes are 6 random digits with leading zeros preserved.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from functools import lru_cache

from src.common.aliyun.dm_smtp_client import AliyunDmSmtpClient, get_dm_smtp_client
from src.common.exceptions import RateLimitError, ValidationError
from src.common.redis import get_redis

logger = logging.getLogger(__name__)

CODE_TTL_SECONDS = 3600
GUARD_TTL_SECONDS = 120
CODE_LENGTH = 6


def _code_key(email: str) -> str:
    return f"email-verify-{email}"


def _guard_key(email: str) -> str:
    return f"email-verify-guard-{email}"


def _generate_code() -> str:
    """Return a 6-digit numeric code with leading zeros preserved."""
    return f"{secrets.randbelow(10 ** CODE_LENGTH):0{CODE_LENGTH}d}"


@dataclass
class EmailCodeService:
    """Generate / send / consume email verification codes via Redis + Aliyun DM."""

    smtp_client: AliyunDmSmtpClient

    async def send(self, email: str) -> None:
        """Generate a code, persist to Redis, and dispatch via SMTP.

        Raises:
            RateLimitError("REQUEST_TOO_FREQUENT") if guard key still alive.
            ExternalAPIError("EMAIL_SEND_FAILED") if SMTP delivery fails;
                in that case the freshly written code is removed from
                Redis to avoid ghost codes.
        """
        redis = await get_redis()
        if await redis.get(_guard_key(email)):
            raise RateLimitError("REQUEST_TOO_FREQUENT", details=429)

        code = _generate_code()
        await redis.set(_code_key(email), code, ex=CODE_TTL_SECONDS)
        await redis.set(_guard_key(email), "guard", ex=GUARD_TTL_SECONDS)

        try:
            await self.smtp_client.send_verification_email(recipient=email, code=code)
        except Exception:
            # SMTP failed -- drop the code so the user is not locked out
            # with a phantom "valid" code they can never see.
            try:
                await redis.delete(_code_key(email))
            except Exception:
                logger.exception("failed to roll back email code key after SMTP error")
            raise

    async def consume(self, email: str, submitted_code: str) -> None:
        """Validate and consume a previously sent code.

        Successful validation deletes the code (one-shot).  Mismatch /
        absence raises ValidationError("INCORRECT_VERIFY_CODE").
        """
        redis = await get_redis()
        expected = await redis.get(_code_key(email))
        if expected is None or expected != submitted_code:
            raise ValidationError("INCORRECT_VERIFY_CODE", details=400)
        await redis.delete(_code_key(email))


@lru_cache(maxsize=1)
def get_email_code_service() -> EmailCodeService:
    """Return the process-wide EmailCodeService singleton."""
    return EmailCodeService(smtp_client=get_dm_smtp_client())
