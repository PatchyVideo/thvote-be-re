"""Steam store page scraper."""

from __future__ import annotations

import datetime as dt

from lxml import etree

from src.apps.scraper.schemas import RespBody, ScrapeData
from src.apps.scraper.utils.cache import get_cache, set_cache
from src.apps.scraper.utils.network import request_abroad_website, wait_for_rate_limit

_HEADER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


async def steamdata(appid: str, udid: str | None = None) -> RespBody:
    """Scrape Steam store page by app ID."""
    site = "steam"
    await wait_for_rate_limit(site, limit=0.1)
    if udid is None:
        udid = f"{site}:{appid}"
    cached = await get_cache(udid)
    if cached:
        return cached

    url = f"https://store.steampowered.com/app/{appid}"
    r = await request_abroad_website(url, headers=_HEADER)
    if r.status_code == 302:
        return RespBody(status="err", msg=f"no content with {url}")
    html = r.content.decode("utf-8")
    try:
        page = etree.HTML(html)
        title_el = page.xpath('//*[@id="appHubAppName"]')
        if not title_el:
            return RespBody(status="parsererr", msg="steam: appHubAppName not found")
        title = title_el[0].text
        cover_el = page.xpath('//*[@id="gameHeaderImageCtn"]/img')
        cover_raw = cover_el[0].attrib["src"] if cover_el else None
        cover = (
            cover_raw[: cover_raw.find("?")]
            if cover_raw and "?" in cover_raw
            else cover_raw
        )
        media: list[str] = []
        show_list = page.xpath('//*[@id="highlight_player_area"]/div')
        if show_list:
            for item in show_list[0].xpath(
                '//div[@class="highlight_player_item highlight_movie"]'
            ):
                if v := item.attrib.get("data-mp4-hd-source"):
                    media.append(v[: v.find("?")] if "?" in v else v)
            for item in show_list[0].xpath(
                '//div/a[@class="highlight_screenshot_link"]'
            ):
                if img := item.attrib.get("href"):
                    media.append(img[: img.find("?")] if "?" in img else img)
        desc_el = page.xpath('/html/head/meta[@property="og:description"]')
        desc = desc_el[0].attrib["content"] if desc_el else None
        dev_el = page.xpath('//div[@id="developers_list"]/a')
        author_name = dev_el[0].text if dev_el else "unknown"
        time_el = page.xpath('//div[@class="release_date"]/div[@class="date"]')
        ptime = None
        if time_el:
            try:
                dt_struct = dt.datetime.strptime(
                    time_el[0].text.strip(), "%Y 年 %m 月 %d 日"
                )
                ptime = dt_struct.strftime("%Y-%m-%d %H:%M:%S +0800")
            except ValueError:
                pass
    except Exception as exc:
        return RespBody(status="parsererr", msg=f"steamparsererr: {repr(exc)}")

    result = RespBody(
        data=ScrapeData(
            title=title,
            udid=udid,
            cover=cover,
            media=media or None,
            desc=desc,
            ptime=ptime,
            author=[f"steam-author:{author_name}"],
            author_name=[author_name],
            tname="SOFTWARE",
        )
    )
    await set_cache(udid, result)
    return result
