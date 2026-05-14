"""AcFun video scraper."""

from __future__ import annotations

import json
import time

from lxml import etree

from src.apps.scraper.schemas import RespBody, ScrapeData
from src.apps.scraper.utils.cache import get_cache, set_cache
from src.apps.scraper.utils.network import request_website, wait_for_rate_limit

_HEADER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36"
}


async def acdata(acid: str, udid: str | None = None) -> RespBody:
    """Scrape AcFun video data by ac ID."""
    site = "acfun"
    await wait_for_rate_limit(site, limit=0.2)
    if udid is None:
        udid = f"{site}:{acid}"
    cached = await get_cache(udid)
    if cached:
        return cached

    url = f"https://www.acfun.cn/v/ac{acid}"
    r = await request_website(url, headers=_HEADER)
    html = r.content.decode("utf-8")
    try:
        page = etree.HTML(html)
        scripts = page.xpath("/html/body/script")
        if len(scripts) < 7:
            return RespBody(status="parsererr", msg="acfun: script not found")
        script_text = scripts[6].text or ""
        chunk = script_text[script_text.find("{") : script_text.find(";")]
        data = json.loads(chunk)
        ctime = data["currentVideoInfo"]["uploadTime"]
        uid = data["user"]["id"]
        repost = data.get("originalDeclare") != 1
        area = data["channel"]["parentName"]
        sub_area = data["channel"]["name"]
        tname = "VIDEO"
        if area == "音乐":
            tname = "MUSIC"
        elif area == "科技" and sub_area in ("手办模玩", "科技制造"):
            tname = "CRAFT"
    except Exception as exc:
        return RespBody(status="parsererr", msg=f"acparsererr: {repr(exc)}")

    result = RespBody(
        data=ScrapeData(
            title=data["title"],
            udid=udid,
            cover=data["coverImgInfo"]["thumbnailImageCdnUrl"],
            desc=data.get("description"),
            ptime=_ac_ptime(ctime // 1000),
            author=[f"acfun-author:{uid}"],
            author_name=[data["user"]["name"]],
            repost=repost,
            tname=tname,
        )
    )
    await set_cache(udid, result)
    return result


def _ac_ptime(ctime: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S %z", time.localtime(ctime))
