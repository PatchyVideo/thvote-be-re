"""TEST_LOGIN_BYPASS——测试登录旁路(白名单固定验证码)。

⚠️ 临时测试设施,**公开上线前必须整体移除**(本模块、两个 consume 的短路行、
config.py 两个字段、测试 Nacos 两个 key)。全量定位:``grep -r TEST_LOGIN_BYPASS``。
移除条件与安全边界见设计稿:
docs/superpowers/specs/2026-08-14-test-login-bypass-design.md

激活条件(fail-closed):``TEST_LOGIN_BYPASS_ACCOUNTS``(JSON 数组)与
``TEST_LOGIN_BYPASS_CODE`` **同时**非空;默认双空 = 功能不存在。生产
Nacos dataId 永不配置这两个 key。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.common.config import get_settings

if TYPE_CHECKING:  # pragma: no cover
    from src.common.config import Settings

logger = logging.getLogger(__name__)


def _mask(identifier: str) -> str:
    """脱敏:手机号留前3后2,邮箱留首字符+域名。日志禁止出现完整标识。"""
    if "@" in identifier:
        local, _, domain = identifier.partition("@")
        return f"{local[:1]}****@{domain}"
    if len(identifier) >= 6:
        return f"{identifier[:3]}{'*' * (len(identifier) - 5)}{identifier[-2:]}"
    return "*" * len(identifier)


def is_test_login_bypass(
    identifier: str,
    submitted_code: str,
    settings: "Settings | None" = None,
) -> bool:
    """白名单账号提交固定码 → True(调用方据此跳过真实验证码校验)。"""
    s = settings or get_settings()
    accounts = s.test_login_bypass_accounts
    code = s.test_login_bypass_code
    if not accounts or not code:
        return False
    if identifier not in accounts or submitted_code != code:
        return False
    logger.warning("TEST LOGIN BYPASS used for %s", _mask(identifier))
    return True
