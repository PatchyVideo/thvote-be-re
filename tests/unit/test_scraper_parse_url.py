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


# ── 全站点 URL 路由 ───────────────────────────────────────────────────
# 每个站点至少钉一个真实形态的链接，防止正则退化后静默落到 "no content found"。

ALL_ROUTES = [
    # Bilibili
    ("https://www.bilibili.com/video/BV1xx411c7mD", "BV1xx411c7mD", "bilidata"),
    ("https://www.bilibili.com/video/av170001", "170001", "bilidata"),
    ("https://www.bilibili.com/read/cv123456", "123456", "biliarticledata"),
    ("https://www.bilibili.com/read/mobile/123456", "123456", "biliarticledata"),
    # Twitter / X
    ("https://twitter.com/someone/status/1234567890", "1234567890", "twidata"),
    ("https://x.com/someone/status/1234567890", "1234567890", "twidata"),
    # Pixiv
    ("https://www.pixiv.net/artworks/123456", "123456", "pixdata"),
    ("https://www.pixiv.net/i/123456", "123456", "pixdata"),
    ("https://www.pixiv.net/novel/show.php?id=123456", "123456", "pixndata"),
    # NicoNico
    ("https://www.nicovideo.jp/watch/sm10916109", "10916109", "nicovideodata"),
    ("https://seiga.nicovideo.jp/seiga/im123456", "123456", "nicoseigadata"),
    # YouTube
    ("https://youtu.be/abc123", "abc123", "ytbdata"),
    ("https://www.youtube.com/watch?v=abc123", "abc123", "ytbdata"),
    # Weibo
    ("https://m.weibo.cn/status/1234567890", "1234567890", "wbdata"),
    ("https://m.weibo.cn/detail/1234567890", "1234567890", "wbdata"),
    # Tieba
    ("https://tieba.baidu.com/p/1234567890", "1234567890", "tiebadata"),
    # PatchyVideo
    ("https://thvideo.tv/#/video?id=abc123", "abc123", "patchydata"),
    ("https://platinum.vercel.app/video/abc123", "abc123", "patchydata"),
    # Steam
    ("https://store.steampowered.com/app/851100/", "851100", "steamdata"),
    # DLsite
    (
        "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html",
        "RJ123456",
        "dlsitedata",
    ),
    # Melonbooks
    (
        "https://www.melonbooks.co.jp/detail/detail.php?product_id=123456",
        "123456",
        "melondata",
    ),
    # Dizzylab
    ("https://www.dizzylab.net/d/ABC-001/", "ABC-001", "dizzydata"),
    # AcFun
    ("https://www.acfun.cn/v/ac123456", "123456", "acdata"),
    ("https://www.acfun.cn/a/ac123456", "123456", "acadata"),
]


@pytest.mark.parametrize("url,expected_wid,parser_name", ALL_ROUTES)
def test_parse_url_routes_every_site(url, expected_wid, parser_name):
    from src.apps.scraper import process

    wid, parser = asyncio.run(process.parse_url(url))
    assert wid == expected_wid
    assert parser is getattr(process, parser_name)
