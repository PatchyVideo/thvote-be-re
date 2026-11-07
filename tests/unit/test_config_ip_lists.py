"""``TRUSTED_PROXY_IPS`` / ``ADMIN_ALLOWED_IPS`` 的宽容解析。

Nacos 把配置原样写进环境变量,值都是字符串。pydantic-settings 对 ``list[str]``
默认在 source 层按 JSON 预解析,于是把这两个键写成 ``""``(文档里的"留空"写法)
会让 ``Settings()`` 在 import 期直接抛 SettingsError、进程起不来——2026-10-29
生产首次部署就是卡在这里。这两个键现在接受 ``""``、JSON 数组、逗号分隔三种写法。
"""

from __future__ import annotations

import pytest

from src.common.config import Settings


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("", []),
        ("[]", []),
        ('["10.0.0.0/8"]', ["10.0.0.0/8"]),
        ("10.0.0.0/8, 192.168.0.0/16", ["10.0.0.0/8", "192.168.0.0/16"]),
        ("1.2.3.4", ["1.2.3.4"]),
    ],
)
def test_ip_lists_accept_nacos_strings(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: list[str]
) -> None:
    monkeypatch.setenv("TRUSTED_PROXY_IPS", raw)
    monkeypatch.setenv("ADMIN_ALLOWED_IPS", raw)

    settings = Settings()

    assert settings.trusted_proxy_ips == expected
    assert settings.admin_allowed_ips == expected


def test_ip_lists_default_to_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)
    monkeypatch.delenv("ADMIN_ALLOWED_IPS", raising=False)

    settings = Settings()

    assert settings.trusted_proxy_ips == []
    assert settings.admin_allowed_ips == []
