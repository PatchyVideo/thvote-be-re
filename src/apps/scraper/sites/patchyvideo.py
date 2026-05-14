"""PatchyVideo scraper using GraphQL API."""

from __future__ import annotations

import datetime as dt

from src.apps.scraper.schemas import RespBody, ScrapeData
from src.apps.scraper.utils.cache import get_cache, set_cache
from src.apps.scraper.utils.network import request_abroad_api, wait_for_rate_limit

_API = "https://patchyvideo.com/graphql"
_GQL = """
query ($vid: String!) {
  getVideo(para: { vid: $vid, lang: "CHS" }) {
    item {
      title site url coverImage desc repostType uploadTime userSpaceUrls
    }
    tagByCategory(lang: "CHS") { key value }
  }
}
"""


async def patchydata(vid: str, udid: str | None = None) -> RespBody:
    """Scrape PatchyVideo video data by video ID."""
    site = "patchyvideo"
    await wait_for_rate_limit(site, limit=0.1)
    if udid is None:
        udid = f"{site}:{vid}"
    cached = await get_cache(udid)
    if cached:
        return cached

    resp = await request_abroad_api(_API, json={"query": _GQL, "variables": {"vid": vid}})
    data = resp.get("data")
    if not data:
        return RespBody(status="apierr", msg=f"patchyapierr: {resp.get('errors')}")

    item = data["getVideo"]["item"]
    tags = data["getVideo"]["tagByCategory"]

    # Redirect to native parser for known platforms
    if item["site"] in ("bilibili", "nicovideo", "youtube", "twitter", "acfun", "weibo"):
        return RespBody(status="rematch", msg=item["url"])

    authors = None
    for tag in tags:
        if tag["key"] == "AUTHOR":
            authors = tag["value"]
            break

    repost = item.get("repostType") == "original"

    result = RespBody(
        data=ScrapeData(
            title=item["title"],
            udid=udid,
            cover=item.get("coverImage"),
            desc=item.get("desc"),
            ptime=_patchy_ptime(item["uploadTime"]) if item.get("uploadTime") else None,
            author_name=authors,
            repost=repost,
            tname="VIDEO",
        )
    )
    await set_cache(udid, result)
    return result


def _patchy_ptime(upload_time: str) -> str:
    from zoneinfo import ZoneInfo
    d = dt.datetime.strptime(upload_time, "%Y-%m-%dT%H:%M:%S%z")
    d = d.astimezone(ZoneInfo("Asia/Shanghai"))
    return d.strftime("%Y-%m-%d %H:%M:%S %z")
