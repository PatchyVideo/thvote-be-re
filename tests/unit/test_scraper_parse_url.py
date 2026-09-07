"""parse_url 域名识别契约:thwiki.cc 与镜像域名 thbwiki.cc 必须都命中 THBWiki 解析器。

线上曾出现用户粘贴 thbwiki.cc 链接(镜像域名)解析失败:
`parse_url` 正则只认 thwiki.cc,thbwiki.cc 命中不了 → "no content found"。
本测试钉死两个域名(普通词条 + 短链接)都路由到 thbdata。
"""

from __future__ import annotations

import asyncio

import pytest

from src.apps.scraper.process import parse_url
from src.apps.scraper.sites.thbwiki import thbdata

THB_CASES = [
    # thwiki.cc 官方域名(回归:不能退化)
    (
        "https://thwiki.cc/%22Activity%22_Case%EF%BC%9A01_-Graveyard_Memory-",
        "%22Activity%22_Case%EF%BC%9A01_-Graveyard_Memory-",
    ),
    # thbwiki.cc 镜像域名(本次修复)
    (
        "https://thbwiki.cc/%22Activity%22_Case%EF%BC%9A01_-Graveyard_Memory-",
        "%22Activity%22_Case%EF%BC%9A01_-Graveyard_Memory-",
    ),
    ("https://thwiki.cc/-/abc123", "-/abc123"),
    ("https://thbwiki.cc/-/abc123", "-/abc123"),
]


@pytest.mark.parametrize("url,expected_wid", THB_CASES)
def test_parse_url_thbwiki_domains(url: str, expected_wid: str) -> None:
    wid, parser = asyncio.run(parse_url(url))
    assert wid == expected_wid
    assert parser is thbdata
