"""Email verification code service.

Mirrors Rust user-manager behavior:
    code key:     email-verify-{email}           TTL 3600s
    guard key:    email-verify-guard-{email}     TTL 120s
    attempts key: email-verify-attempts-{email}  TTL 3600s (added 2026-09-13)

The guard prevents resends within 120s; the code itself lives for 1 hour
to give users time to switch tabs / open mail clients.

The attempts counter is a Python-side addition (Rust had none): a 6-digit
code that lives an hour and is only guarded by a per-IP login limit can be
brute-forced from many IPs.  After MAX_WRONG_ATTEMPTS mismatches the code is
invalidated and the user must request a new one.

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
from src.common.verification.test_bypass import is_test_login_bypass

logger = logging.getLogger(__name__)

CODE_TTL_SECONDS = 3600
GUARD_TTL_SECONDS = 120
CODE_LENGTH = 6
MAX_WRONG_ATTEMPTS = 5


def _code_key(email: str) -> str:
    return f"email-verify-{email}"


def _guard_key(email: str) -> str:
    return f"email-verify-guard-{email}"


def _attempts_key(email: str) -> str:
    return f"email-verify-attempts-{email}"


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

        Concurrency: the guard key is written with ``SET NX EX`` so two
        concurrent sends to the same address resolve to one winner; the
        loser sees its NX fail and raises ``REQUEST_TOO_FREQUENT``.
        Without this, a fast double-tap would generate two codes, send
        two emails (paying twice) and the second code would silently
        overwrite the first in Redis.
        """
        redis = await get_redis()
        won_guard = await redis.set(
            _guard_key(email), "guard", ex=GUARD_TTL_SECONDS, nx=True
        )
        if not won_guard:
            raise RateLimitError("REQUEST_TOO_FREQUENT", details=429)

        code = _generate_code()
        await redis.set(_code_key(email), code, ex=CODE_TTL_SECONDS)
        await redis.delete(_attempts_key(email))  # fresh code, fresh guess budget

        try:
            await self.smtp_client.send_verification_email(recipient=email, code=code)
        except Exception:
            # SMTP failed -- drop the code so the user is not locked out
            # with a phantom "valid" code they can never see.  Keep the
            # guard alive: anti-spam still wanted, and the failure may
            # be transient (next attempt after 120s succeeds).
            try:
                await redis.delete(_code_key(email))
            except Exception:
                logger.exception("failed to roll back email code key after SMTP error")
            raise

    async def consume(self, email: str, submitted_code: str) -> None:
        """Validate and consume a previously sent code.

        Successful validation deletes the code (one-shot).  Mismatch /
        absence raises ValidationError("INCORRECT_VERIFY_CODE").  The
        MAX_WRONG_ATTEMPTS-th mismatch also invalidates the code, so a
        later correct guess fails too; the error code stays the same so
        the client contract is unchanged.
        """
        if is_test_login_bypass(email, submitted_code):  # TEST_LOGIN_BYPASS 上线前移除
            return
        redis = await get_redis()
        expected = await redis.get(_code_key(email))
        if expected is None:
            raise ValidationError("INCORRECT_VERIFY_CODE", details=400)
        if expected != submitted_code:
            await self._record_wrong_attempt(redis, email)
            raise ValidationError("INCORRECT_VERIFY_CODE", details=400)
        await redis.delete(_code_key(email))
        await redis.delete(_attempts_key(email))

    async def _record_wrong_attempt(self, redis, email: str) -> None:
        """Count a mismatch; on the last allowed one, burn the code."""
        attempts = await redis.incr(_attempts_key(email))
        if attempts == 1:
            await redis.expire(_attempts_key(email), CODE_TTL_SECONDS)
        if attempts >= MAX_WRONG_ATTEMPTS:
            await redis.delete(_code_key(email))
            await redis.delete(_attempts_key(email))
            logger.warning("email code invalidated after %d wrong attempts", attempts)


@lru_cache(maxsize=1)
def get_email_code_service() -> EmailCodeService:
    """Return the process-wide EmailCodeService singleton."""
    return EmailCodeService(smtp_client=get_dm_smtp_client())
