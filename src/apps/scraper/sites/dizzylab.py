"""Dizzylab scraper."""

from __future__ import annotations

import datetime as dt

from lxml import etree

from src.apps.scraper.schemas import RespBody, ScrapeData
from src.apps.scraper.utils.cache import get_cache, set_cache
from src.apps.scraper.utils.network import request_website, wait_for_rate_limit

_HEADER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36"
}


async def dizzydata(wid: str, udid: str | None = None) -> RespBody:
    """Scrape Dizzylab album page by album slug."""
    site = "dizzylab"
    await wait_for_rate_limit(site, limit=0.2)
    if udid is None:
        udid = f"{site}:{wid}"
    cached = await get_cache(udid)
    if cached:
        return cached

    url = f"https://www.dizzylab.net/d/{wid}/"
    r = await request_website(url, headers=_HEADER)
    html = r.content.decode("utf-8")
    try:
        page = etree.HTML(html)
        page_title_el = page.xpath("/html/head/title")
        if page_title_el and "出错了" in (page_title_el[0].text or ""):
            return RespBody(status="err", msg=f"error when request {url}")
        title_el = page.xpath('//div[@class="col"]/h1')
        title = title_el[0].text if title_el else None
        cover_el = page.xpath('/html/head/link[@rel="shortcut icon"]')
        cover = cover_el[0].attrib["href"] if cover_el else None
        media_els = page.xpath('//ul[@class="playlist--list"]/li')
        media: list[str] | None = [el.attrib.get("data-audio", "") for el in media_els]
        if not media or (len(media) == 1 and not media[0]):
            media = None
        desc_el = page.xpath('/html/head/meta[@name="description"]')
        desc = desc_el[0].attrib["content"] if desc_el else None
        author_el = page.xpath('//div[@class="col"]/h4[1]/a')
        author_name = author_el[0].text.replace("@ ", "") if author_el else "unknown"
        ptime = None
        time_els = page.xpath('//div[@class="col"]/p[@class="text-left"]')
        for tel in time_els:
            t = tel.text or ""
            s = t.find("发布于")
            e = t.find("日")
            if s != -1 and e != -1:
                time_str = t[s + 3 : e + 1]
                try:
                    dt_struct = dt.datetime.strptime(time_str, "%Y年%m月%d日")
                    ptime = dt_struct.strftime("%Y-%m-%d %H:%M:%S +0800")
                except ValueError:
                    pass
                break
    except Exception as exc:
        return RespBody(status="parsererr", msg=f"dizzyparsererr: {repr(exc)}")

    result = RespBody(
        data=ScrapeData(
            title=title,
            udid=udid,
            cover=cover,
            media=media,
            desc=desc,
            ptime=ptime,
            author=[f"dizzylab-author:{author_name}"],
            author_name=[author_name],
            tname="MUSIC",
        )
    )
    await set_cache(udid, result)
    return result
