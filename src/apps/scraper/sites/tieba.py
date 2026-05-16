"""Baidu Tieba scraper."""

from __future__ import annotations

import json
import re
import time

from lxml import etree

from src.apps.scraper.schemas import RespBody, ScrapeData
from src.apps.scraper.utils.cache import get_cache, set_cache
from src.apps.scraper.utils.network import request_website, wait_for_rate_limit

_HEADER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36"
}


async def tiebadata(wid: str, udid: str | None = None) -> RespBody:
    """Scrape Baidu Tieba post by post ID."""
    site = "tieba"
    await wait_for_rate_limit(site, limit=0.2)
    if udid is None:
        udid = f"{site}:{wid}"
    cached = await get_cache(udid)
    if cached:
        return cached

    url = f"https://tieba.baidu.com/p/{wid}"
    r = await request_website(url, headers=_HEADER)
    html = r.content.decode("utf-8")
    try:
        page = etree.HTML(html)
        scripts = page.xpath("/html/body/script")
        target = ""
        for s in scripts:
            if s.text and "pb/widget/postList" in s.text:
                target = s.text
                break
        if not target:
            return RespBody(status="parsererr", msg="tieba: postList script not found")
        chunk = target[target.find("pb/widget/postList") + 21 :]
        chunk = chunk[: chunk.find("_.Module.use") - 2]
        chunk = chunk.replace("'", '"').replace("}, }", "}}").replace("},}", "}}")
        data = json.loads(chunk)
        if isinstance(data, list):
            data = data[0]
        post = data["firstPost"]
        title = post["title"]
        ctime = post["now_time"]
        desc_html = post["content"]
        img_match = re.search(r'<img.*?src="(.+?)".*?>', desc_html)
        cover = img_match.group(1) if img_match else None
        desc = re.sub(r"<.*?>", "", desc_html).replace("&amp;", "&").strip()
        thread = data["thread"]
        uid = thread["author_info"]["user_id"]
        author_name = thread["author_info"]["user_name"]
    except Exception as exc:
        return RespBody(status="parsererr", msg=f"tiebaparsererr: {repr(exc)}")

    resp = RespBody(
        data=ScrapeData(
            title=title,
            udid=udid,
            cover=cover,
            desc=desc,
            ptime=_tieba_ptime(ctime),
            author=[f"tieba-author:{uid}"],
            author_name=[author_name],
            tname="OTHER",
        )
    )
    await set_cache(udid, resp)
    return resp


def _tieba_ptime(ctime: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S +0800", time.localtime(int(ctime)))
