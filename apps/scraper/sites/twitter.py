"""Twitter scraper site."""

import re
from typing import Optional

from apps.scraper.schemas import RespBody


async def match_twitter(url: str) -> Optional[str]:
    """Match Twitter/X post URL and extract tweet ID."""
    pattern = r"(twitter|x)\.com/\w+/status/(\d+)"
    if match := re.search(pattern, url):
        return match.group(2)
    return None


async def twidata(wid: str) -> RespBody:
    """Scrape data from Twitter post."""
    # TODO: Implement actual Twitter scraping
    return RespBody(status='ok', msg='not implemented')
