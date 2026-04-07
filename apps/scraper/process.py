"""Scraper core processor.

Handles URL matching and dispatches to appropriate site parsers.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from apps.scraper.schemas import RespBody
from apps.scraper.sites.bilibili import biliarticledata, bilidata
from apps.scraper.sites.pixiv import pixdata, pixndata
from apps.scraper.sites.twitter import twidata
from apps.scraper.utils.network import get_redirect_url

# 加载 .env 环境变量
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


async def get_data(url: str) -> RespBody:
    """Process a URL and extract content data.

    This is the main entry point for the scraper. It handles URL parsing
    and calls the appropriate parser to extract data.

    Args:
        url: URL to scrape

    Returns:
        RespBody containing scraped data or error status
    """
    try:
        wid, parser = await parse_url(url)
        if not wid or not parser:
            return RespBody(status="err", msg="no content found")

        try:
            resp: RespBody = await parser(wid)
            if resp.status == "rematch":
                resp = await get_data(resp.msg)
            return resp
        except Exception as e:
            logger.exception(f"Parser error: {e}")
            return RespBody(status="except", msg=str(e))
    except Exception as e:
        logger.exception(f"Scraper error: {e}")
        return RespBody(status="except", msg=repr(e))


async def parse_url(url: str) -> tuple[str | None, Any | None]:
    """Parse URL and return (wid, parser) tuple.

    Args:
        url: URL to parse

    Returns:
        Tuple of (content ID, parser function) or (None, None)
    """
    url = url.strip()

    # Try short URLs first
    if b23_match := re.search(
        r"(?:https?://)?(?:(?:bili(?:22|23|33|2233)\.cn)|(?:b23\.tv))/[\w]+",
        url,
        re.IGNORECASE,
    ):
        redirect_url = await get_redirect_url(b23_match.group(0))
        if redirect_url:
            url = redirect_url

    # Bilibili video (BV or AV)
    if bv_match := re.search(
        r"(?<![a-zA-Z0-9])(BV[a-zA-Z0-9]{10})(?![a-zA-Z0-9])", url, re.IGNORECASE
    ):
        return bv_match.group(1), bilidata  # Keep original case

    if av_match := re.search(r"(?<![a-zA-Z0-9])(?:AV|av)(\d+)", url):
        return av_match.group(1), bilidata

    # Bilibili article (CV)
    if cv_match := re.search(r"(?<![a-zA-Z0-9])(?:CV|cv)(\d+)", url):
        return cv_match.group(1), biliarticledata

    if cv_mobile := re.search(r"bilibili\.com/read/mobile/(\d+)", url, re.IGNORECASE):
        return cv_mobile.group(1), biliarticledata

    # Twitter
    if tw_match := re.search(r"twitter\.com/[^/]+/status/(\d+)", url, re.IGNORECASE):
        return tw_match.group(1), twidata
    if x_match := re.search(r"x\.com/[^/]+/status/(\d+)", url, re.IGNORECASE):
        return x_match.group(1), twidata

    # Pixiv
    if pixiv_match := re.search(
        r"pixiv\.(?:net|pixivdl\.com)/(?:(?:artworks|i)/|member_illust\.php\?.*id=)(\d+)",
        url,
        re.IGNORECASE,
    ):
        return pixiv_match.group(1), pixdata

    # Pixiv novel
    if pixn_match := re.search(r"pixiv\.net/novel/show\.php\?id=(\d+)", url, re.IGNORECASE):
        return pixn_match.group(1), pixndata

    return None, None
