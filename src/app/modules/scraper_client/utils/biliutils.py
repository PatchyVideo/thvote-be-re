"""Scraper Bilibili utilities.

Provides Bilibili-specific functionality like BV ID conversion
and HTTP headers configuration.
"""

from __future__ import annotations

import os
import uuid

TABLE = "fZodR9XQDSUm21yCkr6zBqiveYah8bt4xsWpHnJE7jL5VG3guMTKNPAwcF"
TR: dict[str, int] = {TABLE[i]: i for i in range(58)}
SALT_LIST = (0, 10, 7, 8, 1, 6, 2, 9, 4, 3)
TABLE_LEN = len(TABLE)


def bv2av(bv: str) -> int:
    """Convert BV ID to AV ID."""
    if not bv or len(bv) < 10:
        return 0
    value = 0
    for index in range(6):
        value += TR.get(bv[SALT_LIST[index]], 0) * (58**index)
    return abs((value - 8728348608) ^ 177451812)


def av2bv(av: int) -> str:
    """Convert AV ID to BV ID."""
    x = (av ^ 177451812) + 8728348608
    result: list[str] = ["B", "V", "1", " ", " ", "4", " ", "1", " ", "7", " "]

    for i in range(6):
        result[SALT_LIST[i]] = TABLE[(x // (58**i)) % TABLE_LEN]

    return "".join(result)


async def bvid_converter(bvid: str | None = None, aid: int | None = None) -> str:
    """Convert between BV ID and AV ID."""
    if bvid:
        return str(bv2av(bvid))
    if aid:
        return av2bv(aid)
    return ""


def get_header() -> dict[str, str]:
    user_agent = os.getenv(
        "BILIBILI_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )
    return {
        "User-Agent": user_agent,
        "Referer": "https://www.bilibili.com",
        "Origin": "https://www.bilibili.com",
        "Accept-Language": "en,zh-CN;q=0.9,zh;q=0.8",
    }


def get_cookies() -> dict[str, str]:
    cookies: dict[str, str] = {}
    if sessdata := os.getenv("BILIBILI_SESSDATA", ""):
        cookies["SESSDATA"] = sessdata
    if b_lsid := os.getenv("BILIBILI_B_LSID", ""):
        cookies["b_lsid"] = b_lsid
    if b_nut := os.getenv("BILIBILI_B_NUT", ""):
        cookies["b_nut"] = b_nut
    if buvid3 := os.getenv("BILIBILI_BUVID3", ""):
        cookies["buvid3"] = buvid3
    if dedeuserid := os.getenv("BILIBILI_DEDEUSERID", ""):
        cookies["DedeUserID"] = dedeuserid
    if bili_jct := os.getenv("BILIBILI_BILI_JCT", ""):
        cookies["bili_jct"] = bili_jct
    if not cookies:
        cookies["buvid3"] = str(uuid.uuid4()).upper()
    return cookies
