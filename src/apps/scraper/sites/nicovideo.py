"""NicoNico Video scraper."""

from __future__ import annotations

import datetime as dt
import json
import re

from lxml import etree

from src.apps.scraper.schemas import RespBody, ScrapeData
from src.apps.scraper.utils.cache import get_cache, set_cache
from src.apps.scraper.utils.network import request_abroad_website, wait_for_rate_limit


async def nicovideodata(smid: str, udid: str | None = None) -> RespBody:
    """Scrape NicoNico video data by sm ID."""
    site = "nicovideo"
    await wait_for_rate_limit(site, limit=0.2)
    if udid is None:
        udid = f"{site}:{smid}"
    cached = await get_cache(udid)
    if cached:
        return cached

    url = f"https://www.nicovideo.jp/watch/sm{smid}"
    r = await request_abroad_website(url)
    html = r.content.decode("utf-8")
    try:
        page = etree.HTML(html)
        data = _video_metadata(page)
        if data is None:
            return RespBody(status="parsererr", msg="nicovideo: no video JSON-LD")
        author = data["author"]
        author_name = author["name"]
        uid_match = re.search(r"user/(\d+)", author.get("url", ""))
        thumbnails = data.get("thumbnailUrl")
        cover = (
            next(iter(thumbnails), None) if isinstance(thumbnails, list) else thumbnails
        )
        ptime = _nico_ptime(data["uploadDate"]) if data.get("uploadDate") else None
    except Exception as exc:
        return RespBody(status="parsererr", msg=f"nicoparsererr: {repr(exc)}")

    resp = RespBody(
        data=ScrapeData(
            title=data.get("name"),
            udid=udid,
            cover=cover,
            desc=data.get("description"),
            ptime=ptime,
            author=[f"nicovideo-author:{uid_match.group(1)}"] if uid_match else None,
            author_name=[author_name],
            tname="VIDEO",
        )
    )
    await set_cache(udid, resp)
    return resp


def _video_metadata(page: etree._Element | None) -> dict | None:
    if page is None:
        return None
    for script in page.xpath(
        '//script[@type="application/ld+json" or @class="LdJson"]'
    ):
        try:
            data = json.loads(script.text or "")
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        is_legacy = script.get("class") == "LdJson" and "@type" not in data
        if (data.get("@type") == "VideoObject" or is_legacy) and data.get("name"):
            return data
    return None


def _nico_ptime(upload_date: str) -> str:
    fmt_in = "%Y-%m-%dT%H:%M:%S%z"
    fmt_out = "%Y-%m-%d %H:%M:%S %z"
    from zoneinfo import ZoneInfo

    d = dt.datetime.strptime(upload_date, fmt_in).astimezone(ZoneInfo("Asia/Shanghai"))
    return d.strftime(fmt_out)
