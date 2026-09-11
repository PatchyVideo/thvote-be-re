"""``VOTE_ELIGIBLE_PROVIDERS`` 的解析韧性（#29 review 复核，2026-09-12）。

`src/common/nacos.py` 把 Nacos 的值原样塞进 ``os.environ``（都是字符串），
而 pydantic-settings 对 ``list[str]`` 字段默认按 JSON 解析。配置里写
``"phone"`` 或 ``"email,phone"``——旁边那些字符串型键就长这样——会让
``Settings()`` 在构造期抛 SettingsError，整个进程起不来。

identity.py 的 ``vote_eligible_providers()`` 承诺"Nacos 里写错只会收窄
资格而不是让登录崩掉"，那条承诺必须在容器格式上也成立，不能只覆盖
"数组里有个不认识的成员"。
"""
from __future__ import annotations

import pytest

from src.apps.user.identity import IdentityProvider, vote_eligible_providers
from src.common.config import Settings


@pytest.mark.parametrize(
    "raw, expected",
    [
        ('["phone"]', ["phone"]),                  # 文档写法
        ('["email", "phone"]', ["email", "phone"]),
        ("phone", ["phone"]),                      # 裸字符串（最自然的笔误）
        ("email,phone", ["email", "phone"]),       # 逗号分隔
        ("email, phone", ["email", "phone"]),      # 带空格
    ],
)
def test_settings_accepts_common_nacos_spellings(monkeypatch, raw, expected):
    monkeypatch.setenv("VOTE_ELIGIBLE_PROVIDERS", raw)
    assert Settings().vote_eligible_providers == expected


def test_settings_falls_back_to_default_on_garbage(monkeypatch):
    """彻底写坏时回到默认值并留日志，而不是让进程起不来。"""
    monkeypatch.setenv("VOTE_ELIGIBLE_PROVIDERS", "{not valid at all")
    assert Settings().vote_eligible_providers == ["email", "phone"]


def test_unknown_member_still_narrows_instead_of_crashing(monkeypatch):
    """原有承诺不变：数组里的未知名字被忽略。"""
    from types import SimpleNamespace

    monkeypatch.setattr(
        "src.apps.user.identity.get_settings",
        lambda: SimpleNamespace(vote_eligible_providers=["phone", "telepathy"]),
    )
    assert vote_eligible_providers() == {IdentityProvider.PHONE}
