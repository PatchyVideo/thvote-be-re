"""Scraper Bilibili utilities.

Provides Bilibili-specific functionality like BV ID conversion
and HTTP headers configuration.
"""

from __future__ import annotations

TABLE = "fZodR9XQDSUm21yCkr6zBqiveYah8bt4xsWpHnJE7jL5VG3guMTKNPAwcF"
TR: dict[str, int] = {TABLE[i]: i for i in range(58)}
SALT = 11
TABLE_LEN = len(TABLE)


def bv2av(bv: str) -> int:
    """Convert BV ID to AV ID.

    Args:
        bv: BV ID (e.g., 'BV1xx411c7mu')

    Returns:
        AV ID as integer
    """
    if not bv or len(bv) < 10:
        return 0

    x = 0
    for i in range(6):
        x += TR.get(bv[SALT_LIST[i]], 0) * (58**i)

    x = (x - 8728348608) ^ 177451812
    return abs(x)


def av2bv(av: int) -> str:
    """Convert AV ID to BV ID.

    Args:
        av: AV ID

    Returns:
        BV ID string
    """
    x = (av ^ 177451812) + 8728348608
    result: list[str] = ["B", "V", "1", " ", " ", "4", " ", "1", " ", "7", " "]

    for i in range(6):
        result[SALT_LIST[i]] = TABLE[(x // (58**i)) % TABLE_LEN]

    return "".join(result)


SALT_LIST = (0, 10, 7, 8, 1, 6, 2, 9, 4, 3)


async def bvid_converter(bvid: str | None = None, aid: int | None = None) -> str:
    """Convert between BV ID and AV ID.

    Args:
        bvid: BV ID to convert to AV
        aid: AV ID to convert to BV

    Returns:
        Converted ID as string
    """
    if bvid:
        return str(bv2av(bvid))
    if aid:
        return av2bv(aid)
    return ""


def get_header() -> dict[str, str]:
    """Get HTTP headers for Bilibili API requests.

    Returns:
        Headers dictionary
    """
    import os

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
    """Get cookies for Bilibili API requests.

    Returns cookies from environment variables or generates a basic buvid3.

    Environment variables:
        BILIBILI_SESSDATA: Session data cookie
        BILIBILI_B_UID: Bilibili user ID
        BILIBILI_B_LSID: LSID cookie
        BILIBILI_B_NUT: Nut cookie
        BILIBILI_BUVID3: Basic user visitor ID

    Returns:
        Cookies dictionary
    """
    import os

    cookies = {}

    sessdata = os.getenv("BILIBILI_SESSDATA", "")
    if sessdata:
        cookies["SESSDATA"] = sessdata

    b_uid = os.getenv("BILIBILI_B_LSID", "")
    if b_uid:
        cookies["b_lsid"] = os.getenv("BILIBILI_B_LSID", "")

    b_nut = os.getenv("BILIBILI_B_NUT", "")
    if b_nut:
        cookies["b_nut"] = b_nut

    buvid3 = os.getenv("BILIBILI_BUVID3", "")
    if buvid3:
        cookies["buvid3"] = buvid3

    if not cookies:
        import uuid

        cookies["buvid3"] = str(uuid.uuid4()).upper()

    return cookies
