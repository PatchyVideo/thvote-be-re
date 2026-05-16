"""YouTube scraper using YouTube Data API v3."""

from __future__ import annotations

import datetime as dt

from src.apps.scraper.schemas import RespBody, ScrapeData
from src.apps.scraper.utils.cache import get_cache, set_cache
from src.apps.scraper.utils.network import request_abroad_api, wait_for_rate_limit


async def ytbdata(vid: str, udid: str | None = None) -> RespBody:
    """Scrape YouTube video data by video ID."""
    from src.common.config import get_settings

    settings = get_settings()
    api_key = settings.youtube_api_key
    if not api_key:
        return RespBody(
            status="apierr", msg="ytbapierr: YOUTUBE_API_KEY not configured"
        )

    site = "youtube"
    await wait_for_rate_limit(site, limit=0.1)
    if udid is None:
        udid = f"{site}:{vid}"
    cached = await get_cache(udid)
    if cached:
        return cached

    api = "https://www.googleapis.com/youtube/v3/videos"
    resp = await request_abroad_api(
        api, params={"key": api_key, "id": vid, "part": "snippet"}
    )
    if not resp.get("items"):
        return RespBody(status="apierr", msg="ytbapierr: no such content")
    snippet = resp["items"][0]["snippet"]
    pic = _best_thumb(snippet["thumbnails"])
    channel_id = snippet["channelId"]

    result = RespBody(
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
    await set_cache(udid, result)
    return result


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
