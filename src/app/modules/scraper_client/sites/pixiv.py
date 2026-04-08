"""Pixiv scraper site module."""

from __future__ import annotations

import os

import httpx

from ..schemas import RespBody, ScrapeData
from ..utils.cache import get_cache, set_cache
from ..utils.network import wait_for_rate_limit

PIXIV_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.pixiv.net",
}


async def pixdata(illust_id: str, udid: str | None = None) -> RespBody:
    site = "pixiv"
    await wait_for_rate_limit(site, limit=0.5)
    udid = udid or f"{site}:{illust_id}"

    cached = await get_cache(udid)
    if cached:
        return cached

    access_token = await _get_pixiv_token()
    if not access_token:
        return RespBody(status="err", msg="Pixiv authentication failed")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://app-api.pixiv.net/v1/illust/detail",
                headers={**PIXIV_HEADERS, "Authorization": f"Bearer {access_token}"},
                params={"illust_id": illust_id},
                timeout=30.0,
            )
            data = response.json()
    except Exception as exc:
        return RespBody(status="apierr", msg=f"请求失败: {exc}")

    if data.get("error"):
        return RespBody(status="apierr", msg=f"Pixiv API error: {data.get('message', 'unknown')}")
    if "illust" not in data:
        return RespBody(status="err", msg="Artwork not found")

    illust = data["illust"]
    author_id = str(illust.get("user", {}).get("id", ""))
    media_urls: list[str] = []
    page_count = illust.get("page_count", 1)
    meta_pages = illust.get("meta_pages", [])
    for index in range(page_count):
        if index == 0:
            url = illust.get("image_urls", {}).get("large", "")
        else:
            url = meta_pages[index].get("image_urls", {}).get("large", "") if index < len(meta_pages) else ""
        if url:
            media_urls.append(url.replace("i.pximg.net", "i.pixiv.re"))

    tname = "DRAWING"
    if illust.get("type") == "ugoira":
        tname = "ANIMATION"
    elif illust.get("illust_type") == 2:
        tname = "MANGA"

    result = RespBody(
        status="ok",
        msg="",
        data=ScrapeData(
            title=illust.get("title", ""),
            udid=udid,
            cover=media_urls[0] if media_urls else None,
            media=media_urls or None,
            desc=illust.get("caption", ""),
            ptime=illust.get("create_date", ""),
            author=[f"pixiv-author:{author_id}"] if author_id else [],
            author_name=[illust.get("user", {}).get("name", "")],
            tname=tname,
            repost=None,
        ),
    )
    await set_cache(udid, result)
    return result


async def pixndata(novel_id: str, udid: str | None = None) -> RespBody:
    site = "pixnovel"
    await wait_for_rate_limit(site, limit=0.5)
    udid = udid or f"{site}:{novel_id}"

    cached = await get_cache(udid)
    if cached:
        return cached

    access_token = await _get_pixiv_token()
    if not access_token:
        return RespBody(status="err", msg="Pixiv authentication failed")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://app-api.pixiv.net/v1/novel/detail",
                headers={**PIXIV_HEADERS, "Authorization": f"Bearer {access_token}"},
                params={"novel_id": novel_id},
                timeout=30.0,
            )
            data = response.json()
    except Exception as exc:
        return RespBody(status="apierr", msg=f"请求失败: {exc}")

    if data.get("error"):
        return RespBody(status="apierr", msg=f"Pixiv API error: {data.get('message', 'unknown')}")
    if "novel" not in data:
        return RespBody(status="err", msg="Novel not found")

    novel = data["novel"]
    author_id = str(novel.get("user", {}).get("id", ""))
    synopsis = novel.get("synopsis", "")
    description = f"[文字数: {novel.get('text_length', 0)}] {synopsis}"

    cover_url = novel.get("cover_url", "")
    if cover_url:
        cover_url = cover_url.replace("i.pximg.net", "i.pixiv.re")

    result = RespBody(
        status="ok",
        msg="",
        data=ScrapeData(
            title=novel.get("title", ""),
            udid=udid,
            cover=cover_url or None,
            media=None,
            desc=description,
            ptime=novel.get("create_date", ""),
            author=[f"pixiv-author:{author_id}"] if author_id else [],
            author_name=[novel.get("user", {}).get("name", "")],
            tname="NOVEL",
            repost=None,
        ),
    )
    await set_cache(udid, result)
    return result


async def _get_pixiv_token() -> str | None:
    """Get Pixiv access token using refresh token."""
    refresh_token = os.getenv("PIXIV_REFRESH_TOKEN", "")

    if not refresh_token:
        cached = await get_cache("pixiv_token")
        if cached:
            return cached
        return None

    client_secret = os.getenv("PIXIV_CLIENT_SECRET", "")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://oauth.secure.pixiv.net/auth/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": "MOUbB1cFIWTf5UyK6gkV9fNPo8fLqxcT",
                    "client_secret": client_secret,
                },
                headers=PIXIV_HEADERS,
                timeout=30.0,
            )
            result = response.json()
    except Exception:
        return None

    if "access_token" in result:
        token = result["access_token"]
        await set_cache("pixiv_token", token)
        return token

    return None
