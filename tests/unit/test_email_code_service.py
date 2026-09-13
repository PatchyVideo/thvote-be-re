"""EmailCodeService unit tests with an in-memory fake Redis."""

from __future__ import annotations

import pytest

from src.common.exceptions import RateLimitError, ValidationError
from src.common.verification.email_code import (
    CODE_TTL_SECONDS,
    GUARD_TTL_SECONDS,
    MAX_WRONG_ATTEMPTS,
    EmailCodeService,
)


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, tuple[str, int | None]] = {}

    async def get(self, key):
        v = self.store.get(key)
        return None if v is None else v[0]

    async def set(self, key, value, ex=None, nx=False):
        # Mirror redis-py: SET NX returns True on success, None on collision
        if nx and key in self.store:
            return None
        self.store[key] = (value, ex)
        return True

    async def delete(self, key):
        self.store.pop(key, None)

    async def incr(self, key):
        current = int(self.store.get(key, ("0", None))[0]) + 1
        self.store[key] = (str(current), self.store.get(key, ("0", None))[1])
        return current

    async def expire(self, key, seconds):
        if key in self.store:
            self.store[key] = (self.store[key][0], seconds)


class _FakeSmtp:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.fail = False

    async def send_verification_email(self, *, recipient: str, code: str) -> None:
        if self.fail:
            raise RuntimeError("smtp boom")
        self.calls.append((recipient, code))


@pytest.fixture
def fake_redis(monkeypatch):
    fake = _FakeRedis()

    async def _get_redis_stub():
        return fake

    monkeypatch.setattr("src.common.verification.email_code.get_redis", _get_redis_stub)
    return fake


@pytest.mark.asyncio
async def test_send_writes_code_and_guard(fake_redis):
    smtp = _FakeSmtp()
    svc = EmailCodeService(smtp_client=smtp)

    await svc.send("a@example.com")

    code_value, code_ttl = fake_redis.store["email-verify-a@example.com"]
    guard_value, guard_ttl = fake_redis.store["email-verify-guard-a@example.com"]
    assert len(code_value) == 6 and code_value.isdigit()
    assert code_ttl == CODE_TTL_SECONDS
    assert guard_value == "guard"
    assert guard_ttl == GUARD_TTL_SECONDS
    assert smtp.calls == [("a@example.com", code_value)]


@pytest.mark.asyncio
async def test_send_rate_limited_when_guard_present(fake_redis):
    fake_redis.store["email-verify-guard-a@example.com"] = ("guard", 120)
    svc = EmailCodeService(smtp_client=_FakeSmtp())

    with pytest.raises(RateLimitError):
        await svc.send("a@example.com")


@pytest.mark.asyncio
async def test_send_rolls_back_code_on_smtp_failure(fake_redis):
    smtp = _FakeSmtp()
    smtp.fail = True
    svc = EmailCodeService(smtp_client=smtp)

    with pytest.raises(RuntimeError):
        await svc.send("a@example.com")

    # code should be removed; guard remains (anti-spam still wanted)
    assert "email-verify-a@example.com" not in fake_redis.store


@pytest.mark.asyncio
async def test_consume_one_shot(fake_redis):
    fake_redis.store["email-verify-a@example.com"] = ("123456", 3600)
    svc = EmailCodeService(smtp_client=_FakeSmtp())

    await svc.consume("a@example.com", "123456")
    assert "email-verify-a@example.com" not in fake_redis.store

    # Re-using the same code now fails
    with pytest.raises(ValidationError):
        await svc.consume("a@example.com", "123456")


@pytest.mark.asyncio
async def test_consume_wrong_code(fake_redis):
    fake_redis.store["email-verify-a@example.com"] = ("000000", 3600)
    svc = EmailCodeService(smtp_client=_FakeSmtp())

    with pytest.raises(ValidationError):
        await svc.consume("a@example.com", "000001")


@pytest.mark.asyncio
async def test_consume_unknown_email(fake_redis):
    svc = EmailCodeService(smtp_client=_FakeSmtp())
    with pytest.raises(ValidationError):
        await svc.consume("nobody@example.com", "000000")


@pytest.mark.asyncio
async def test_consume_invalidates_code_after_max_wrong_attempts(fake_redis):
    """A brute-forcer gets MAX_WRONG_ATTEMPTS guesses, then the code is dead
    even if the next guess is right."""
    fake_redis.store["email-verify-a@example.com"] = ("123456", 3600)
    svc = EmailCodeService(smtp_client=_FakeSmtp())

    for _ in range(MAX_WRONG_ATTEMPTS):
        with pytest.raises(ValidationError):
            await svc.consume("a@example.com", "000000")

    assert "email-verify-a@example.com" not in fake_redis.store
    with pytest.raises(ValidationError):
        await svc.consume("a@example.com", "123456")


@pytest.mark.asyncio
async def test_consume_succeeds_below_attempt_limit(fake_redis):
    """Control: one fewer wrong guess must NOT kill the code."""
    fake_redis.store["email-verify-a@example.com"] = ("123456", 3600)
    svc = EmailCodeService(smtp_client=_FakeSmtp())

    for _ in range(MAX_WRONG_ATTEMPTS - 1):
        with pytest.raises(ValidationError):
            await svc.consume("a@example.com", "000000")

    await svc.consume("a@example.com", "123456")
    assert "email-verify-a@example.com" not in fake_redis.store
    assert "email-verify-attempts-a@example.com" not in fake_redis.store


@pytest.mark.asyncio
async def test_send_resets_wrong_attempt_counter(fake_redis):
    """A fresh code starts with a fresh budget of guesses."""
    fake_redis.store["email-verify-attempts-a@example.com"] = ("4", 3600)
    svc = EmailCodeService(smtp_client=_FakeSmtp())

    await svc.send("a@example.com")
    assert "email-verify-attempts-a@example.com" not in fake_redis.store
