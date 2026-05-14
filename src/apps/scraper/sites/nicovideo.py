"""NicoNico Video scraper."""

from __future__ import annotations

import datetime as dt
import json

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
        ld_scripts = page.xpath('//script[@class="LdJson"]')
        if not ld_scripts:
            return RespBody(status="parsererr", msg="nicovideo: no LdJson script")
        data = json.loads(ld_scripts[0].text)
        upload_date = data["uploadDate"]
        user_url = data["author"]["url"]
        import re
        uid_match = re.search(r"user/(\d+)", user_url)
        uid = uid_match.group(1) if uid_match else "unknown"
        author = f"nicovideo-author:{uid}"
    except Exception as exc:
        return RespBody(status="parsererr", msg=f"nicoparsererr: {repr(exc)}")

    resp = RespBody(
        data=ScrapeData(
            title=data.get("name"),
            udid=udid,
            cover=data["thumbnailUrl"][0] if isinstance(data.get("thumbnailUrl"), list) else data.get("thumbnailUrl"),
            desc=data.get("description"),
            ptime=_nico_ptime(upload_date),
            author=[author],
            author_name=[data["author"]["name"]],
            tname="VIDEO",
        )
    )
    await set_cache(udid, resp)
    return resp


def _nico_ptime(upload_date: str) -> str:
    fmt_in = "%Y-%m-%dT%H:%M:%S%z"
    fmt_out = "%Y-%m-%d %H:%M:%S %z"
    from zoneinfo import ZoneInfo
    d = dt.datetime.strptime(upload_date, fmt_in).astimezone(ZoneInfo("Asia/Shanghai"))
    return d.strftime(fmt_out)
