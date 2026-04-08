"""Bilibili scraper site module."""

from __future__ import annotations

import time

from ..schemas import RespBody, ScrapeData
from ..utils.biliutils import get_cookies, get_header
from ..utils.cache import get_cache, set_cache
from ..utils.network import request_api, wait_for_rate_limit

MUSIC_AREAS = [
    "原创音乐",
    "翻唱",
    "演奏",
    "VOCALOID·UTAU",
    "音乐现场",
    "MV",
    "乐评盘点",
    "音乐教学",
    "音乐综合",
    "音频",
    "说唱",
]


async def bilidata(wid: str, udid: str | None = None) -> RespBody:
    site = "bilibili"
    await wait_for_rate_limit(site, limit=0.2)
    udid = udid or f"{site}:{wid}"

    cached = await get_cache(udid)
    if cached:
        return cached

    if wid.upper().startswith("BV"):
        api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={wid}"
    else:
        api_url = f"https://api.bilibili.com/x/web-interface/view?aid={wid}"

    try:
        response = await request_api(api_url, headers=get_header(), cookies=get_cookies())
    except Exception as exc:
        return RespBody(status="apierr", msg=f"请求失败: {exc}")

    data = response.get("data")
    if data is None:
        if response.get("code") == -352:
            return RespBody(status="apierr", msg="biliapi: banned")
        return RespBody(status="apierr", msg=f"biliapimsg: {response.get('message', 'unknown')}")

    staffs = data.get("staff")
    if staffs:
        author = [f"bilibili-author:{item['mid']}" for item in staffs]
        author_name = [item["name"] for item in staffs]
    else:
        uid = data["owner"]["mid"]
        author = [f"bilibili-author:{uid}"]
        author_name = [data["owner"]["name"]]

    area = data.get("tname", "")
    tname = "VIDEO"
    if area in MUSIC_AREAS:
        tname = "MUSIC"
    elif area == "绘画":
        tname = "DRAWING"
    elif area == "手工":
        tname = "CRAFT"

    cover = (data.get("pic") or "").replace("http:", "https:")
    result = RespBody(
        status="ok",
        msg="",
        data=ScrapeData(
            title=data.get("title", ""),
            udid=udid,
            cover=cover or None,
            media=None,
            desc=data.get("desc", ""),
            ptime=_format_ptime(data.get("pubdate", 0)),
            author=author,
            author_name=author_name,
            tname=tname,
            repost=data.get("copyright") != 1,
        ),
    )
    await set_cache(udid, result)
    return result


async def biliarticledata(cv: str, udid: str | None = None) -> RespBody:
    site = "biliarticle"
    await wait_for_rate_limit(site, limit=0.2)
    udid = udid or f"{site}:{cv}"

    cached = await get_cache(udid)
    if cached:
        return cached

    try:
        response = await request_api(
            f"https://api.bilibili.com/x/article/view?id={cv}",
            headers=get_header(),
            cookies=get_cookies(),
        )
    except Exception as exc:
        return RespBody(status="apierr", msg=f"请求失败: {exc}")

    if response.get("data") is None:
        return RespBody(status="apierr", msg=f"获取文章失败: {response.get('message', 'unknown')}")

    data = response["data"]
    author_mid = str(data.get("author", {}).get("mid", ""))
    media_urls = list(data.get("image_urls") or [])
    media_urls.extend(data.get("dynamic_urls") or [])
    cover = (data.get("banner_url") or "").replace("http:", "https:")

    result = RespBody(
        status="ok",
        msg="",
        data=ScrapeData(
            title=data.get("title", ""),
            udid=udid,
            cover=cover or None,
            media=media_urls or None,
            desc=data.get("summary", ""),
            ptime=_format_ptime(data.get("publish_time", 0)),
            author=[f"bilibili-author:{author_mid}"] if author_mid else [],
            author_name=[data.get("author", {}).get("name", "")],
            tname="ARTICLE",
            repost=None,
        ),
    )
    await set_cache(udid, result)
    return result


def _format_ptime(ctime: int) -> str:
    if not ctime:
        return ""
    return time.strftime("%Y-%m-%d %H:%M:%S %z", time.localtime(ctime))
