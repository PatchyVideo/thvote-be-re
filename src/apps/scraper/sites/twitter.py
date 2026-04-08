"""Twitter/X scraper site module.

Handles scraping data from Twitter/X tweets.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import httpx

from src.apps.scraper.schemas import RespBody, ScrapeData
from src.apps.scraper.utils.cache import get_cache, set_cache
from src.apps.scraper.utils.network import wait_for_rate_limit

if TYPE_CHECKING:
    pass


async def twidata(twid: str, udid: str | None = None) -> RespBody:
    """Scrape Twitter/X tweet data.

    Args:
        twid: Tweet ID
        udid: Optional unique ID for caching

    Returns:
        RespBody with tweet data
    """
    site = "twitter"
    await wait_for_rate_limit(site, limit=1.0)

    if udid is None:
        udid = f"{site}:{twid}"

    cached = await get_cache(udid)
    if cached:
        return cached

    bearer_token = os.getenv("TWITTER_BEARER_TOKEN", "")

    if not bearer_token:
        return RespBody(status="err", msg="Twitter API token not configured")

    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "User-Agent": "v2TweetLookupPython",
    }

    api_url = f"https://api.twitter.com/2/tweets/{twid}"
    params = {
        "expansions": "author_id,attachments.media_keys",
        "tweet.fields": "created_at,text,lang,possibly_sensitive",
        "user.fields": "name,username,profile_image_url",
        "media.fields": "url,preview_image_url,type",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                api_url, headers=headers, params=params, timeout=30.0
            )
            data = response.json()
    except Exception as e:
        return RespBody(status="apierr", msg=f"请求失败: {str(e)}")

    if "errors" in data:
        error_msg = data["errors"][0].get("detail", "Unknown error")
        return RespBody(status="apierr", msg=f"Twitter API error: {error_msg}")

    if "data" not in data:
        return RespBody(status="err", msg="Tweet not found")

    tweet = data["data"]
    includes = data.get("includes", {})
    users = includes.get("users", [])
    media = includes.get("media", [])

    author_id = tweet.get("author_id", "")
    author_name = ""
    author_username = ""

    for user in users:
        if user.get("id") == author_id:
            author_name = user.get("name", "")
            author_username = user.get("username", "")
            break

    author = [f"twitter-author:{author_id}"] if author_id else []
    author_name_list = [author_name] if author_name else []

    if author_username:
        author_name_list = [f"@{author_username}"] if author_name_list else [f"@{author_username}"]

    media_urls = []
    for m in media:
        if m.get("type") == "photo":
            url = m.get("url") or m.get("preview_image_url")
            if url:
                media_urls.append(url)

    cover_url = media_urls[0] if media_urls else None

    scrape_data = ScrapeData(
        title=f"@{author_username}: {tweet.get('text', '')[:50]}...",
        udid=udid,
        cover=cover_url,
        media=media_urls if media_urls else None,
        desc=tweet.get("text", ""),
        ptime=tweet.get("created_at", ""),
        author=author,
        author_name=author_name_list,
        tname="TWEET",
        repost=None,
    )

    result = RespBody(status="ok", msg="", data=scrape_data)
    await set_cache(udid, result)

    return result
