"""Pixiv scraper site."""

import re
from typing import Optional

from apps.scraper.schemas import RespBody


async def match_pixiv(url: str) -> Optional[str]:
    """Match Pixiv artwork URL and extract artwork ID."""
    pattern = r"pixiv\.net/artworks/(\d+)"
    if match := re.search(pattern, url):
        return match.group(1)
    return None


async def pixdata(wid: str) -> RespBody:
    """Scrape data from Pixiv artwork."""
    # TODO: Implement actual Pixiv scraping
    return RespBody(status='ok', msg='not implemented')
