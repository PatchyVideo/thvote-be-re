"""Pixiv scraper site module.

Handles scraping data from Pixiv artworks and novels.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import httpx

from src.apps.scraper.schemas import RespBody, ScrapeData
from src.apps.scraper.utils.cache import get_cache, set_cache
from src.apps.scraper.utils.network import wait_for_rate_limit

if TYPE_CHECKING:
    pass


PIXIV_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.pixiv.net",
}


async def pixdata(illust_id: str, udid: str | None = None) -> RespBody:
    """Scrape Pixiv artwork data.

    Args:
        illust_id: Pixiv artwork ID
        udid: Optional unique ID for caching

    Returns:
        RespBody with artwork data
    """
    site = "pixiv"
    await wait_for_rate_limit(site, limit=0.5)

    if udid is None:
        udid = f"{site}:{illust_id}"

    cached = await get_cache(udid)
    if cached:
        return cached

    access_token = await _get_pixiv_token()
    if not access_token:
        return RespBody(status="err", msg="Pixiv authentication failed")

    api_url = "https://app-api.pixiv.net/v1/illust/detail"
    params = {"illust_id": illust_id}

    headers = {**PIXIV_HEADERS, "Authorization": f"Bearer {access_token}"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                api_url, headers=headers, params=params, timeout=30.0
            )
            data = response.json()
    except Exception as e:
        return RespBody(status="apierr", msg=f"请求失败: {str(e)}")

    if data.get("error"):
        return RespBody(
            status="apierr", msg=f"Pixiv API error: {data.get('message', 'unknown')}"
        )

    if "illust" not in data:
        return RespBody(status="err", msg="Artwork not found")

    illust = data["illust"]

    author_id = str(illust.get("user", {}).get("id", ""))
    author = [f"pixiv-author:{author_id}"] if author_id else []
    author_name = [illust.get("user", {}).get("name", "")]

    page_count = illust.get("page_count", 1)
    media_urls = []
    for i in range(page_count):
        if i == 0:
            url = illust.get("image_urls", {}).get("large", "")
        else:
            url = (
                illust.get("meta_pages", [{}])[i].get("image_urls", {}).get("large", "")
            )
        if url:
            url = url.replace("i.pximg.net", "i.pixiv.re")
            media_urls.append(url)

    cover_url = media_urls[0] if media_urls else None

    tname = "DRAWING"
    if illust.get("type") == "ugoira":
        tname = "ANIMATION"
    elif illust.get("illust_type") == 2:
        tname = "MANGA"

    scrape_data = ScrapeData(
        title=illust.get("title", ""),
        udid=udid,
        cover=cover_url,
        media=media_urls if media_urls else None,
        desc=illust.get("caption", ""),
        ptime=illust.get("create_date", ""),
        author=author,
        author_name=author_name,
        tname=tname,
        repost=None,
    )

    result = RespBody(status="ok", msg="", data=scrape_data)
    await set_cache(udid, result)

    return result


async def pixndata(novel_id: str, udid: str | None = None) -> RespBody:
    """Scrape Pixiv novel data.

    Args:
        novel_id: Pixiv novel ID
        udid: Optional unique ID for caching

    Returns:
        RespBody with novel data
    """
    site = "pixnovel"
    await wait_for_rate_limit(site, limit=0.5)

    if udid is None:
        udid = f"{site}:{novel_id}"

    cached = await get_cache(udid)
    if cached:
        return cached

    access_token = await _get_pixiv_token()
    if not access_token:
        return RespBody(status="err", msg="Pixiv authentication failed")

    api_url = "https://app-api.pixiv.net/v1/novel/detail"
    params = {"novel_id": novel_id}

    headers = {**PIXIV_HEADERS, "Authorization": f"Bearer {access_token}"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                api_url, headers=headers, params=params, timeout=30.0
            )
            data = response.json()
    except Exception as e:
        return RespBody(status="apierr", msg=f"请求失败: {str(e)}")

    if data.get("error"):
        return RespBody(
            status="apierr", msg=f"Pixiv API error: {data.get('message', 'unknown')}"
        )

    if "novel" not in data:
        return RespBody(status="err", msg="Novel not found")

    novel = data["novel"]

    author_id = str(novel.get("user", {}).get("id", ""))
    author = [f"pixiv-author:{author_id}"] if author_id else []
    author_name = [novel.get("user", {}).get("name", "")]

    cover_url = novel.get("cover_url", "")
    if cover_url:
        cover_url = cover_url.replace("i.pximg.net", "i.pixiv.re")

    text_length = novel.get("text_length", 0)
    description = f"[文字数: {text_length}] {novel.get('synopsis', '')}"

    scrape_data = ScrapeData(
        title=novel.get("title", ""),
        udid=udid,
        cover=cover_url or None,
        media=None,
        desc=description,
        ptime=novel.get("create_date", ""),
        author=author,
        author_name=author_name,
        tname="NOVEL",
        repost=None,
    )

    result = RespBody(status="ok", msg="", data=scrape_data)
    await set_cache(udid, result)

    return result


async def _get_pixiv_token() -> str | None:
    """Get Pixiv access token using refresh token.

    Returns:
        Access token or None if failed
    """
    refresh_token = os.getenv("PIXIV_REFRESH_TOKEN", "")

    if not refresh_token:
        cached = await get_cache("pixiv_token")
        if cached:
            return cached
        return None

    api_url = "https://oauth.secure.pixiv.net/auth/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": "MOUbB1cFIWTf5UyK6gkV9fNPo8fLqxcT",
        "client_secret": os.getenv("PIXIV_CLIENT_SECRET", ""),
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                api_url, data=data, headers=PIXIV_HEADERS, timeout=30.0
            )
            result = response.json()
    except Exception:
        return None

    if "access_token" in result:
        token = result["access_token"]
        await set_cache("pixiv_token", token)
        return token

    return None
