"""THBWiki (Touhou Wiki) scraper using MediaWiki API."""

from __future__ import annotations

import re
import time
from urllib.parse import quote, unquote

from src.apps.scraper.schemas import RespBody, ScrapeData
from src.apps.scraper.utils.cache import get_cache, set_cache
from src.apps.scraper.utils.network import (
    request_abroad_api,
    request_abroad_website,
    wait_for_rate_limit,
)

_API = "https://thwiki.cc/api.php"
_UDID_FMT = "thbwiki:{entry}"


async def thbdata(entry: str, udid: str | None = None) -> RespBody:
    """Scrape THBWiki entry using MediaWiki ASK API."""
    site = "thbwiki"
    await wait_for_rate_limit(site, limit=0.1)

    short = urlen = jump = None
    if "%" in entry:
        urlen = entry
        entry = unquote(urlen)
    if entry[:2] == "-/":
        short = entry
        entry = await _parse_short(short)

    if udid is None:
        udid = _UDID_FMT.format(entry=entry)
    cached = await get_cache(udid)
    if cached:
        return cached

    resp = await request_abroad_website(
        _API,
        params={
            "action": "ask",
            "format": "json",
            "formatversion": 2,
            "query": (
                f"[[{entry}]]|?封面图片|?专辑名称|?同人志名称|?视频名称"
                "|?软件名称|?发售日期|?制作方|?发售方|?出品方|?原画师|?模型名称"
            ),
        },
    )
    r = resp.json()
    results = r.get("query", {}).get("results", {})
    if not results:
        return RespBody(status="apierr", msg=f"thbapierr: no result for {entry}")

    data = list(results.values())[0]
    d = data["printouts"]
    title = data["fulltext"]
    udid = _UDID_FMT.format(entry=title)

    cover = None
    if d.get("封面图片") and d["封面图片"][0].get("exists") == "1":
        cover_entry = d["封面图片"][0]["fulltext"].replace("文件:", "")
        cover = await _get_cover(cover_entry)

    ptime = None
    if d.get("发售日期"):
        ctime = d["发售日期"][0].get("timestamp")
        if ctime:
            ptime = time.strftime("%Y-%m-%d %H:%M:%S %z", time.localtime(int(ctime)))

    author_list = (
        d.get("制作方", [])
        + d.get("发售方", [])
        + d.get("出品方", [])
        + d.get("原画师", [])
    )
    seen: list[str] = []
    for x in [a["fulltext"] for a in author_list]:
        if x not in seen:
            seen.append(x)
    author = seen
    author_name = [f"thbwiki-author:{x}" for x in seen]

    tname = "OTHER"
    if d.get("专辑名称"):
        tname = "MUSIC"
    elif d.get("同人志名称"):
        tname = "DRAWING"
    elif d.get("视频名称"):
        tname = "VIDEO"
    elif d.get("软件名称"):
        tname = "SOFTWARE"
    elif d.get("模型名称"):
        tname = "CRAFT"

    fulltext = data["fulltext"]
    if fulltext != entry:
        jump = entry
        entry = fulltext
    final_udid = _UDID_FMT.format(entry=fulltext)

    ret = RespBody(
        data=ScrapeData(
            title=title,
            udid=final_udid,
            cover=cover,
            ptime=ptime,
            author=author,
            author_name=author_name,
            tname=tname,
        )
    )
    await set_cache(final_udid, ret)
    if short:
        await set_cache(_UDID_FMT.format(entry=short), ret)
    if urlen:
        await set_cache(_UDID_FMT.format(entry=urlen), ret)
    else:
        await set_cache(_UDID_FMT.format(entry=quote(entry)), ret)
    if jump:
        await set_cache(_UDID_FMT.format(entry=jump), ret)
    return ret


async def _parse_short(short: str) -> str:
    pageid = _short2pageid(short.replace("-/", ""))
    resp = await request_abroad_api(
        _API,
        params={
            "action": "parse",
            "format": "json",
            "pageid": pageid,
            "formatversion": 2,
            "prop": "displaytitle",
        },
    )
    return resp["parse"]["title"]


async def _get_cover(file_entry: str) -> str | None:
    resp = await request_abroad_api(
        _API,
        params={
            "action": "parse",
            "format": "json",
            "text": "{{filepath:FILE_ENTRY | 378}}".replace("FILE_ENTRY", file_entry),
            "formatversion": 2,
            "prop": "text",
            "disablelimitreport": "1",
            "disableeditsection": "1",
            "disablestylededuplication": "1",
            "disabletoc": "1",
        },
    )
    text = resp.get("parse", {}).get("text", "")
    if m := re.search(r'"(http.+?)"', text):
        return m.group(1)
    return None


def _short2pageid(short: str) -> int:
    code = "0123456789abcdefghijklmnopqrstuvwxyz"
    result = 0
    for b, n in enumerate(short):
        result += code.find(n) * 32 ** (len(short) - b - 1)
    return result
