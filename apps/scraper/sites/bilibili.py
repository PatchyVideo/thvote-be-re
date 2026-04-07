"""Bilibili scraper site."""

import re
from typing import Optional

import httpx

from apps.scraper.schemas import RespBody


async def match_bilibili(url: str) -> Optional[str]:
    """Match Bilibili video URL and extract video ID."""
    patterns = [
        r"bilibili\.com/video/(BV[\w]+)",
        r"bilibili\.com/video/(av\d+)",
        r"b23\.tv/(\w+)",
    ]
    for pattern in patterns:
        if match := re.search(pattern, url):
            return match.group(1)
    return None


async def bilidata(wid: str) -> RespBody:
    """Scrape data from Bilibili video."""
    # TODO: Implement actual Bilibili scraping
    return RespBody(status='ok', msg='not implemented')
