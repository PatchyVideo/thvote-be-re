"""Scraper Bilibili utilities.

Provides Bilibili-specific functionality like BV ID conversion
and HTTP headers configuration.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import timedelta

from src.apps.scraper.utils.cache import get_cache, set_cache
from src.apps.scraper.utils.network import request_api

logger = logging.getLogger(__name__)

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

    Bilibili's public API returns HTTP 412 + an HTML challenge when the
    request carries a browser User-Agent (without WBI signature), but accepts
    non-browser clients.  Verified on the test host: Chrome UA -> 412 HTML,
    curl UA -> 200 JSON with the same headers/cookies.  Keep the default
    non-browser UA; BILIBILI_USER_AGENT can override it if needed.
    """
    import os

    user_agent = os.getenv("BILIBILI_USER_AGENT", "curl/8.5.0")
    return {
        "User-Agent": user_agent,
        "Referer": "https://www.bilibili.com",
        "Origin": "https://www.bilibili.com",
        "Accept-Language": "en,zh-CN;q=0.9,zh;q=0.8",
    }


# 访客 Cookie（不依赖 B 站账号）：
# /x/frontend/finger/spi 会签发 b_3/b_4，分别作为 buvid3/buvid4；
# 加上 b_nut 时间戳后，公开的 view 接口即可返回 JSON，无需 SESSDATA。
_GUEST_CACHE_KEY = "bilibili_guest_cookies"
_GUEST_CACHE_TTL = timedelta(hours=12)
_SPI_URL = "https://api.bilibili.com/x/frontend/finger/spi"


def _cookies_from_env() -> dict[str, str]:
    """Old-deployment override: SESSDATA / buvid3 / b_nut from env."""
    cookies: dict[str, str] = {}
    mapping = {
        "BILIBILI_SESSDATA": "SESSDATA",
        "BILIBILI_B_LSID": "b_lsid",
        "BILIBILI_B_NUT": "b_nut",
        "BILIBILI_BUVID3": "buvid3",
    }
    for env_name, cookie_name in mapping.items():
        value = os.getenv(env_name, "")
        if value:
            cookies[cookie_name] = value
    return cookies


async def _fetch_guest_cookies() -> dict[str, str]:
    """Ask Bilibili for a guest buvid pair and add a fresh b_nut."""
    try:
        response = await request_api(_SPI_URL, headers=get_header(), timeout=10.0)
    except Exception as exc:  # noqa: BLE001 - degrade to random buvid3 below
        logger.warning("Bilibili guest cookie bootstrap failed: %s", exc)
        return {}
    data = response.get("data") or {}
    buvid3 = data.get("b_3")
    buvid4 = data.get("b_4")
    if not buvid3:
        logger.warning("Bilibili SPI response missing b_3: %r", response.get("code"))
        return {}
    cookies = {"buvid3": str(buvid3), "b_nut": str(int(time.time()))}
    if buvid4:
        cookies["buvid4"] = str(buvid4)
    return cookies


async def get_cookies() -> dict[str, str]:
    """Get cookies for Bilibili API requests.

    Priority:
    1. explicit env cookies (old deployment compatibility):
       BILIBILI_SESSDATA / BILIBILI_BUVID3 / BILIBILI_B_NUT / BILIBILI_B_LSID;
    2. cached guest cookies (12h TTL);
    3. freshly issued guest cookies via /x/frontend/finger/spi.

    No Bilibili account is required for the normal path.
    """
    env_cookies = _cookies_from_env()
    if env_cookies:
        return env_cookies

    try:
        cached = await get_cache(_GUEST_CACHE_KEY)
    except Exception:  # noqa: BLE001 - Redis outage must not break scraping
        cached = None
    if cached:
        return dict(cached)

    cookies = await _fetch_guest_cookies()
    if cookies:
        try:
            await set_cache(_GUEST_CACHE_KEY, cookies, ex=_GUEST_CACHE_TTL)
        except Exception:  # noqa: BLE001 - cache is optional
            logger.warning("Failed to cache Bilibili guest cookies", exc_info=True)
        return cookies

    # Last resort: the old random-UUID behavior. It usually gets blocked, but
    # keeps the request shape valid and surfaces as a normal apierr.
    logger.warning("Using random Bilibili buvid3 fallback (guest bootstrap failed)")
    return {"buvid3": str(uuid.uuid4()).upper()}
