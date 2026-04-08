"""Twitter/X scraper site module."""

from __future__ import annotations

import os

import httpx

from ..schemas import RespBody, ScrapeData
from ..utils.cache import get_cache, set_cache
from ..utils.network import wait_for_rate_limit


async def twidata(twid: str, udid: str | None = None) -> RespBody:
    site = "twitter"
    await wait_for_rate_limit(site, limit=1.0)
    udid = udid or f"{site}:{twid}"

    cached = await get_cache(udid)
    if cached:
        return cached

    bearer_token = os.getenv("TWITTER_BEARER_TOKEN", "")
    if not bearer_token:
        return RespBody(status="err", msg="Twitter API token not configured")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.twitter.com/2/tweets/{twid}",
                headers={
                    "Authorization": f"Bearer {bearer_token}",
                    "User-Agent": "v2TweetLookupPython",
                },
                params={
                    "expansions": "author_id,attachments.media_keys",
                    "tweet.fields": "created_at,text,lang,possibly_sensitive",
                    "user.fields": "name,username,profile_image_url",
                    "media.fields": "url,preview_image_url,type",
                },
                timeout=30.0,
            )
            data = response.json()
    except Exception as exc:
        return RespBody(status="apierr", msg=f"请求失败: {exc}")

    if "errors" in data:
        return RespBody(status="apierr", msg=f"Twitter API error: {data['errors'][0].get('detail', 'Unknown error')}")
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

    media_urls = []
    for item in media:
        if item.get("type") == "photo":
            url = item.get("url") or item.get("preview_image_url")
            if url:
                media_urls.append(url)

    display_name = [author_name] if author_name else []
    if author_username:
        display_name = [f"@{author_username}"]

    result = RespBody(
        status="ok",
        msg="",
        data=ScrapeData(
            title=f"@{author_username}: {tweet.get('text', '')[:50]}...",
            udid=udid,
            cover=media_urls[0] if media_urls else None,
            media=media_urls or None,
            desc=tweet.get("text", ""),
            ptime=tweet.get("created_at", ""),
            author=[f"twitter-author:{author_id}"] if author_id else [],
            author_name=display_name,
            tname="TWEET",
            repost=None,
        ),
    )
    await set_cache(udid, result)
    return result
