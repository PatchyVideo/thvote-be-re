"""测试登录旁路(白名单固定验证码)——临时测试设施,上线前随功能一并移除。

设计稿: docs/superpowers/specs/2026-08-14-test-login-bypass-design.md
定位标记: TEST_LOGIN_BYPASS
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.common.exceptions import ValidationError
from src.common.verification import test_bypass as tb
from src.common.verification.sms_code import SmsCodeService


def _settings(accounts=None, code=""):
    return SimpleNamespace(
        test_login_bypass_accounts=accounts or [],
        test_login_bypass_code=code,
    )


ARMED = _settings(accounts=["19900000001", "test1@example.com"], code="888888")


# ---------- helper 本体 ----------

def test_hit_when_armed_and_account_and_code_match():
    assert tb.is_test_login_bypass("19900000001", "888888", settings=ARMED)
    assert tb.is_test_login_bypass("test1@example.com", "888888", settings=ARMED)


def test_miss_on_wrong_code_or_unlisted_account():
    assert not tb.is_test_login_bypass("19900000001", "000000", settings=ARMED)
    assert not tb.is_test_login_bypass("13800138000", "888888", settings=ARMED)


def test_disarmed_by_default_empty_config():
    assert not tb.is_test_login_bypass(
        "19900000001", "888888", settings=_settings()
    )
    # 只配了账号没配码 / 只配码没配账号 —— 均不激活
    assert not tb.is_test_login_bypass(
        "19900000001", "", settings=_settings(accounts=["19900000001"])
    )
    assert not tb.is_test_login_bypass(
        "19900000001", "888888", settings=_settings(code="888888")
    )


# ---------- consume 短路 ----------

@pytest.mark.asyncio
async def test_sms_consume_short_circuits_without_pnvs(monkeypatch):
    monkeypatch.setattr(tb, "get_settings", lambda: ARMED)
    pnvs = SimpleNamespace(
        check_sms_verify_code=AsyncMock(
            side_effect=AssertionError("must not call PNVS")
        )
    )
    svc = SmsCodeService(pnvs_client=pnvs)
    await svc.consume("19900000001", "888888")  # 放行且不打阿里云
    pnvs.check_sms_verify_code.assert_not_called()


@pytest.mark.asyncio
async def test_sms_consume_wrong_code_still_goes_to_pnvs(monkeypatch):
    monkeypatch.setattr(tb, "get_settings", lambda: ARMED)
    outcome = SimpleNamespace(passed=False)
    pnvs = SimpleNamespace(check_sms_verify_code=AsyncMock(return_value=outcome))
    svc = SmsCodeService(pnvs_client=pnvs)
    with pytest.raises(ValidationError):
        await svc.consume("19900000001", "000000")
    pnvs.check_sms_verify_code.assert_called_once()


@pytest.mark.asyncio
async def test_email_consume_short_circuits_without_redis(monkeypatch):
    from src.common.verification.email_code import EmailCodeService
    import src.common.verification.email_code as email_mod

    monkeypatch.setattr(tb, "get_settings", lambda: ARMED)
    monkeypatch.setattr(
        email_mod, "get_redis",
        AsyncMock(side_effect=AssertionError("must not touch redis")),
    )
    svc = EmailCodeService(smtp_client=SimpleNamespace())
    await svc.consume("test1@example.com", "888888")


def test_masking_never_logs_full_identifier():
    assert tb._mask("19900000001") == "199******01"
    assert tb._mask("test1@example.com") == "t****@example.com"
    assert "19900000001" not in tb._mask("19900000001")
