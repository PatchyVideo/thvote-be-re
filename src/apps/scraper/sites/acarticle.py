"""AcFun article scraper."""

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


async def acadata(acid: str, udid: str | None = None) -> RespBody:
    """Scrape AcFun article data by ac ID."""
    site = "acarticle"
    await wait_for_rate_limit(site, limit=0.2)
    if udid is None:
        udid = f"{site}:{acid}"
    cached = await get_cache(udid)
    if cached:
        return cached

    url = f"https://www.acfun.cn/a/ac{acid}"
    r = await request_website(url, headers=_HEADER)
    html = r.content.decode("utf-8")
    try:
        page = etree.HTML(html)
        script_els = page.xpath('//*[@id="main"]/script')
        if not script_els:
            return RespBody(status="parsererr", msg="acarticle: main script not found")
        script_text = script_els[0].text or ""
        # Find the last JSON object before the last semicolon
        positions = [-1, -1, -1]
        pos = -1
        while True:
            pos = script_text.find(";", pos + 1)
            if pos == -1:
                break
            positions = [positions[1], positions[2], pos]
        chunk = script_text[script_text.find("{") : positions[0]]
        data = json.loads(chunk)
        cover = data.get("coverUrl", "")
        if "?" in cover:
            cover = cover[: cover.find("?")]
        ctime = data["createTimeMillis"]
        uid = data["user"]["id"]
        area = data["channel"]["name"]
        sub_area = data["realm"]["realmName"]
        tname = "ARTICLE"
        if area == "二次元画师":
            tname = "DRAWING"
        elif area == "漫画文学" and sub_area == "漫画":
            tname = "DRAWING"
    except Exception as exc:
        return RespBody(status="parsererr", msg=f"acaparsererr: {repr(exc)}")

    result = RespBody(
        data=ScrapeData(
            title=data["title"],
            udid=udid,
            cover=cover or None,
            desc=data.get("description"),
            ptime=_ac_ptime(ctime // 1000),
            author=[f"acfun-author:{uid}"],
            author_name=[data["user"]["name"]],
            tname=tname,
        )
    )
    await set_cache(udid, result)
    return result


def _ac_ptime(ctime: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S %z", time.localtime(ctime))
