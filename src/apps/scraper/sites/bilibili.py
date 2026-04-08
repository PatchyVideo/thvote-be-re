"""Bilibili scraper site module.

Handles scraping data from Bilibili videos and articles.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from src.apps.scraper.schemas import RespBody, ScrapeData
from src.apps.scraper.utils.biliutils import get_cookies, get_header
from src.apps.scraper.utils.cache import get_cache, set_cache
from src.apps.scraper.utils.network import request_api, wait_for_rate_limit

if TYPE_CHECKING:
    pass


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
    """Scrape Bilibili video data by AV ID or BV ID.

    Args:
        wid: Bilibili AV ID (numeric string) or BV ID (BV... format)
        udid: Optional unique ID for caching

    Returns:
        RespBody with video data
    """
    site = "bilibili"
    await wait_for_rate_limit(site, limit=0.2)

    # 判断是 AV 号还是 BV 号
    is_bvid = wid.upper().startswith("BV")

    if udid is None:
        udid = f"{site}:{wid}"

    cached = await get_cache(udid)
    if cached:
        return cached

    # 优先使用 bvid 参数（更稳定），避免 AV 号转换错误
    if is_bvid:
        api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={wid}"
    else:
        api_url = f"https://api.bilibili.com/x/web-interface/view?aid={wid}"

    # 优先使用 bvid 参数（更稳定），避免 AV 号转换错误
    if is_bvid:
        api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={wid}"
    else:
        api_url = f"https://api.bilibili.com/x/web-interface/view?aid={wid}"

    try:
        response = await request_api(
            api_url, headers=get_header(), cookies=get_cookies()
        )
    except Exception as e:
        return RespBody(status="apierr", msg=f"请求失败: {str(e)}")

    data = response.get("data")
    if data is None:
        if response.get("code") == -352:
            return RespBody(status="apierr", msg="biliapi: banned")
        return RespBody(
            status="apierr", msg=f"biliapimsg: {response.get('message', 'unknown')}"
        )

    staffs = data.get("staff")
    if staffs:
        author = [f"bilibili-author:{x['mid']}" for x in staffs]
        author_name = [x["name"] for x in staffs]
    else:
        uid = data["owner"]["mid"]
        author = [f"bilibili-author:{uid}"]
        author_name = [data["owner"]["name"]]

    repost = data.get("copyright") != 1

    area = data.get("tname", "")
    tname = "VIDEO"
    if area in MUSIC_AREAS:
        tname = "MUSIC"
    elif area == "绘画":
        tname = "DRAWING"
    elif area == "手工":
        tname = "CRAFT"

    ptime = _format_ptime(data.get("pubdate", 0))

    cover = data.get("pic", "")
    if cover:
        cover = cover.replace("http:", "https:")

    scrape_data = ScrapeData(
        title=data.get("title", ""),
        udid=udid,
        cover=cover,
        media=None,
        desc=data.get("desc", ""),
        ptime=ptime,
        author=author,
        author_name=author_name,
        tname=tname,
        repost=repost,
    )

    result = RespBody(status="ok", msg="", data=scrape_data)
    await set_cache(udid, result)

    return result


async def biliarticledata(cv: str, udid: str | None = None) -> RespBody:
    """Scrape Bilibili article (专栏) data by CV ID.

    Args:
        cv: Bilibili CV ID (numeric)
        udid: Optional unique ID for caching

    Returns:
        RespBody with article data
    """
    site = "biliarticle"
    await wait_for_rate_limit(site, limit=0.2)

    if udid is None:
        udid = f"{site}:{cv}"

    cached = await get_cache(udid)
    if cached:
        return cached

    api_url = f"https://api.bilibili.com/x/article/view?id={cv}"
    try:
        response = await request_api(
            api_url, headers=get_header(), cookies=get_cookies()
        )
    except Exception as e:
        return RespBody(status="apierr", msg=f"请求失败: {str(e)}")

    if response.get("data") is None:
        return RespBody(
            status="apierr", msg=f"获取文章失败: {response.get('message', 'unknown')}"
        )

    data = response["data"]

    author_mid = str(data.get("author", {}).get("mid", ""))
    author = [f"bilibili-author:{author_mid}"] if author_mid else []
    author_name = [data.get("author", {}).get("name", "")]

    ptime = _format_ptime(data.get("publish_time", 0))

    cover = data.get("banner_url", "")
    if cover:
        cover = cover.replace("http:", "https:")

    media_urls = []
    if image_urls := data.get("image_urls"):
        media_urls = image_urls

    if dynamic_urls := data.get("dynamic_urls"):
        media_urls.extend(dynamic_urls)

    scrape_data = ScrapeData(
        title=data.get("title", ""),
        udid=udid,
        cover=cover,
        media=media_urls if media_urls else None,
        desc=data.get("summary", ""),
        ptime=ptime,
        author=author,
        author_name=author_name,
        tname="ARTICLE",
        repost=None,
    )

    result = RespBody(status="ok", msg="", data=scrape_data)
    await set_cache(udid, result)

    return result


def _format_ptime(ctime: int) -> str:
    """Convert Unix timestamp to formatted datetime string.

    Args:
        ctime: Unix timestamp

    Returns:
        Formatted datetime string in CST timezone
    """
    if not ctime:
        return ""
    return time.strftime("%Y-%m-%d %H:%M:%S %z", time.localtime(ctime))
