"""Weibo (mobile) scraper."""

from __future__ import annotations

import datetime as dt
import json

from src.apps.scraper.schemas import RespBody, ScrapeData
from src.apps.scraper.utils.cache import get_cache, set_cache
from src.apps.scraper.utils.network import request_website, wait_for_rate_limit

_HEADER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36"
}


async def wbdata(wid: str, udid: str | None = None) -> RespBody:
    """Scrape Weibo post data by post ID."""
    site = "weibo"
    await wait_for_rate_limit(site, limit=0.2)
    if udid is None:
        udid = f"{site}:{wid}"
    cached = await get_cache(udid)
    if cached:
        return cached

    url = f"https://m.weibo.cn/detail/{wid}"
    r = await request_website(url, headers=_HEADER)
    html = r.content.decode("utf-8")
    try:
        chunk = html[html.find("$render_data") :]
        chunk = chunk[chunk.find("[{") + 1 : chunk.find("}]") + 1]
        data = json.loads(chunk)["status"]
        uid = data["user"]["id"]
        author = f"weibo-author:{uid}"
    except Exception as exc:
        return RespBody(status="parsererr", msg=f"weiboparsererr: {repr(exc)}")

    resp = RespBody(
        data=ScrapeData(
            title=f'{data["user"]["screen_name"]}的微博',
            udid=udid,
            cover=data.get("bmiddle_pic"),
            desc=data.get("text"),
            ptime=_wb_ptime(data["created_at"]),
            author=[author],
            author_name=[data["user"]["screen_name"]],
            tname="DRAWING",
        )
    )
    await set_cache(udid, resp)
    return resp


def _wb_ptime(created_at: str) -> str:
    from zoneinfo import ZoneInfo

    d = dt.datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
    d = d.astimezone(ZoneInfo("Asia/Shanghai"))
    return d.strftime("%Y-%m-%d %H:%M:%S %z")
