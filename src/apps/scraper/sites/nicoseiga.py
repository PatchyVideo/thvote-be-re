"""NicoNico Seiga scraper."""

from __future__ import annotations

import datetime as dt

from lxml import etree

from src.apps.scraper.schemas import RespBody, ScrapeData
from src.apps.scraper.utils.cache import get_cache, set_cache
from src.apps.scraper.utils.network import request_abroad_website, wait_for_rate_limit


async def nicoseigadata(imid: str, udid: str | None = None) -> RespBody:
    """Scrape NicoSeiga image data by im ID."""
    site = "nicoseiga"
    await wait_for_rate_limit(site, limit=0.2)
    if udid is None:
        udid = f"{site}:{imid}"
    cached = await get_cache(udid)
    if cached:
        return cached

    url = f"https://seiga.nicovideo.jp/seiga/im{imid}"
    r = await request_abroad_website(url)
    html = r.content.decode("utf-8")
    try:
        page = etree.HTML(html)
        title = page.xpath('//div[@class="lg_ttl_illust"]/h1')
        if not title:
            return RespBody(status="parsererr", msg="nicoseiga: title not found")
        title = title[0].text
        uid_el = page.xpath('//*[@id="header"]/div[2]/ul[1]/li[2]/a')
        uid = uid_el[0].attrib["href"][13:] if uid_el else "unknown"
        cover_el = page.xpath('//a[@id="link_thumbnail_main"]/img')
        cover = cover_el[0].attrib["src"] if cover_el else None
        desc_el = page.xpath('//table[@id="illust_area"]/tr[2]/td/div[3]')
        desc = desc_el[0].text if desc_el else None
        ptime_el = page.xpath('//table[@id="illust_area"]/tr[2]/td/div[4]')
        ptime_str = ptime_el[0].text[:-3] if ptime_el else None
        author_el = page.xpath('//table[@id="illust_area"]/tr[2]/td/div[2]/strong')
        author_name = author_el[0].text if author_el else "unknown"
    except Exception as exc:
        return RespBody(status="parsererr", msg=f"seigaparsererr: {repr(exc)}")

    resp = RespBody(
        data=ScrapeData(
            title=title,
            udid=udid,
            cover=cover,
            media=[cover] if cover else None,
            desc=desc,
            ptime=_seiga_ptime(ptime_str) if ptime_str else None,
            author=[f"nicoseiga-author:{uid}"],
            author_name=[author_name],
            tname="DRAWING",
        )
    )
    await set_cache(udid, resp)
    return resp


def _seiga_ptime(post_time: str) -> str:
    from zoneinfo import ZoneInfo
    fmt_in = "%Y年%m月%d日 %H:%M:%S"
    fmt_out = "%Y-%m-%d %H:%M:%S %z"
    d = dt.datetime.strptime(post_time, fmt_in)
    d = d.replace(tzinfo=ZoneInfo("Asia/Tokyo")).astimezone(ZoneInfo("Asia/Shanghai"))
    return d.strftime(fmt_out)
