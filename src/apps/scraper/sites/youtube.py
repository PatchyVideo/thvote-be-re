"""YouTube scraper using Data API v3 or public oEmbed metadata."""

from __future__ import annotations

import datetime as dt

from src.apps.scraper.schemas import RespBody, ScrapeData
from src.apps.scraper.utils.cache import get_cache, set_cache
from src.apps.scraper.utils.network import (
    request_abroad_api,
    request_abroad_website,
    wait_for_rate_limit,
)


async def ytbdata(vid: str, udid: str | None = None) -> RespBody:
    """Scrape YouTube video data by video ID."""
    from src.common.config import get_settings

    api_key = get_settings().youtube_api_key
    await wait_for_rate_limit("youtube", limit=0.1)
    if udid is None:
        udid = f"youtube:{vid}"
    # Keep the richer Data API result independent of the oEmbed cache.
    cache_key = udid if api_key else f"oembed:{udid}"
    cached = await get_cache(cache_key)
    if cached:
        return cached

    result = await (
        _from_data_api(vid, udid, api_key) if api_key else _from_oembed(vid, udid)
    )
    if result.status == "ok":
        await set_cache(cache_key, result)
    return result


async def _from_data_api(vid: str, udid: str, api_key: str) -> RespBody:
    api = "https://www.googleapis.com/youtube/v3/videos"
    resp = await request_abroad_api(
        api, params={"key": api_key, "id": vid, "part": "snippet"}
    )
    if not resp.get("items"):
        return RespBody(status="apierr", msg="ytbapierr: no such content")
    snippet = resp["items"][0]["snippet"]
    pic = _best_thumb(snippet["thumbnails"])
    channel_id = snippet["channelId"]

    return RespBody(
        data=ScrapeData(
            title=snippet["title"],
            udid=udid,
            cover=pic,
            desc=snippet["description"],
            ptime=_ytb_ptime(snippet["publishedAt"]),
            author=[f"youtube-author:{channel_id}"],
            author_name=[snippet["channelTitle"]],
            tname="VIDEO",
        )
    )


async def _from_oembed(vid: str, udid: str) -> RespBody:
    response = await request_abroad_website(
        "https://www.youtube.com/oembed",
        params={"url": f"https://www.youtube.com/watch?v={vid}", "format": "json"},
    )
    if not response.is_success:
        return RespBody(
            status="apierr", msg=f"youtube: oEmbed returned HTTP {response.status_code}"
        )
    try:
        metadata = response.json()
    except ValueError:
        return RespBody(status="parsererr", msg="youtube: invalid oEmbed response")
    if not isinstance(metadata, dict) or not all(
        isinstance(metadata.get(field), str) and metadata[field].strip()
        for field in ("title", "author_name", "thumbnail_url")
    ):
        return RespBody(status="parsererr", msg="youtube: incomplete oEmbed metadata")

    return RespBody(
        data=ScrapeData(
            title=metadata["title"],
            udid=udid,
            cover=metadata["thumbnail_url"],
            author_name=[metadata["author_name"]],
            tname="VIDEO",
        )
    )


def _best_thumb(thumbnails: dict) -> str | None:
    for res in ("maxres", "standard", "high", "medium", "default"):
        if pic := thumbnails.get(res):
            return pic["url"]
    return None


def _ytb_ptime(published_at: str) -> str:
    from zoneinfo import ZoneInfo

    fmt_out = "%Y-%m-%d %H:%M:%S %z"
    d = dt.datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ")
    d = d.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Asia/Shanghai"))
    return d.strftime(fmt_out)
