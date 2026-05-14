"""Melonbooks scraper."""

from __future__ import annotations

import datetime as dt
import re

from lxml import etree

from src.apps.scraper.schemas import RespBody, ScrapeData
from src.apps.scraper.utils.cache import get_cache, set_cache
from src.apps.scraper.utils.network import request_abroad_website, wait_for_rate_limit

_HEADER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
}


async def melondata(wid: str, udid: str | None = None) -> RespBody:
    """Scrape Melonbooks product page by product ID."""
    site = "melonbooks"
    await wait_for_rate_limit(site, limit=0.2)
    if udid is None:
        udid = f"{site}:{wid}"
    cached = await get_cache(udid)
    if cached:
        return cached

    url = f"https://www.melonbooks.co.jp/detail/detail.php?product_id={wid}"
    r = await request_abroad_website(url, headers=_HEADER)
    html = r.content.decode("utf-8")
    try:
        page = etree.HTML(html)
        title_el = page.xpath("/html/head/title")
        if title_el:
            raw_title = title_el[0].text or ""
            if "年齢認証" in raw_title:
                return RespBody(status="r18")
            title = raw_title.replace("の通販・購入", "").strip()
        else:
            return RespBody(status="parsererr", msg="melon: title not found")
        media_els = page.xpath('//div[@id="thumbs"]/ul/li/div/a')
        media: list[str] | None = [f"https:{a.attrib['href']}" for a in media_els if a.attrib.get("href")]
        if not media:
            media = None
        cover_el = page.xpath('/html/head/meta[@property="og:image"]')
        cover = cover_el[0].attrib["content"] if cover_el else None
        desc_el = page.xpath('/html/head/meta[@property="og:description"]')
        desc = desc_el[0].attrib["content"] if desc_el else None
        author_el = page.xpath('//*[@id="contents"]/div[2]/div[1]/p/a')
        if not author_el:
            return RespBody(status="parsererr", msg="melon: author not found")
        author_href = author_el[0].attrib.get("href", "")
        m = re.search(r"_id=(\d+)", author_href)
        if not m:
            return RespBody(status="parsererr", msg="melon: no circle_id or maker_id")
        author = f"melonbooks-author:{m.group(1)}"
        author_name = author_el[0].text or "unknown"
        ptime = None
        for xpath in (
            '//*[@id="title"]/div/div/div[1]/div/em/span',
            '//*[@id="contents"]/div[2]/div[2]/div[2]/div[3]/div[5]',
        ):
            time_els = page.xpath(xpath)
            if time_els:
                time_str = (time_els[0].text or "").replace("発売日：", "").strip()
                try:
                    dt_struct = dt.datetime.strptime(time_str, "%Y年%m月%d日")
                    ptime = dt_struct.strftime("%Y-%m-%d %H:%M:%S +0800")
                    break
                except ValueError:
                    continue
    except Exception as exc:
        return RespBody(status="parsererr", msg=f"melonparsererr: {repr(exc)}")

    result = RespBody(
        data=ScrapeData(
            title=title,
            udid=udid,
            cover=cover,
            media=media,
            desc=desc,
            ptime=ptime,
            author=[author],
            author_name=[author_name],
            tname=None,
        )
    )
    await set_cache(udid, result)
    return result
