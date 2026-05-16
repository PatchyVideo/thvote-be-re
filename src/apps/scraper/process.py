"""Scraper core processor.

Handles URL matching and dispatches to appropriate site parsers.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from dotenv import load_dotenv

from src.apps.scraper.schemas import RespBody
from src.apps.scraper.sites.acarticle import acadata
from src.apps.scraper.sites.acfun import acdata
from src.apps.scraper.sites.bilibili import biliarticledata, bilidata
from src.apps.scraper.sites.dizzylab import dizzydata
from src.apps.scraper.sites.dlsite import dlsitedata
from src.apps.scraper.sites.melon import melondata
from src.apps.scraper.sites.nicoseiga import nicoseigadata
from src.apps.scraper.sites.nicovideo import nicovideodata
from src.apps.scraper.sites.patchyvideo import patchydata
from src.apps.scraper.sites.pixiv import pixdata, pixndata
from src.apps.scraper.sites.steam import steamdata
from src.apps.scraper.sites.thbwiki import thbdata
from src.apps.scraper.sites.tieba import tiebadata
from src.apps.scraper.sites.twitter import twidata
from src.apps.scraper.sites.weibo import wbdata
from src.apps.scraper.sites.youtube import ytbdata
from src.apps.scraper.utils.network import get_redirect_url

load_dotenv()

logger = logging.getLogger(__name__)


async def get_data(url: str) -> RespBody:
    """Process a URL and extract content data."""
    try:
        wid, parser = await parse_url(url)
        if not wid or not parser:
            return RespBody(status="err", msg="no content found")
        try:
            resp: RespBody = await parser(wid)
            if resp.status == "rematch":
                resp = await get_data(resp.msg)
            return resp
        except Exception as e:
            logger.exception(f"Parser error: {e}")
            return RespBody(status="except", msg=str(e))
    except Exception as e:
        logger.exception(f"Scraper error: {e}")
        return RespBody(status="except", msg=repr(e))


async def parse_url(url: str) -> tuple[str | None, Any | None]:
    """Parse URL and return (wid, parser) tuple."""
    url = url.strip()

    # Resolve Bilibili short links
    if b23_match := re.search(
        r"(?:https?://)?(?:(?:bili(?:22|23|33|2233)\.cn)|(?:b23\.tv))/[\w]+",
        url,
        re.IGNORECASE,
    ):
        redirect_url = await get_redirect_url(b23_match.group(0))
        if redirect_url:
            url = redirect_url

    # ── Bilibili ──────────────────────────────────────────────────────
    if bv_match := re.search(
        r"(?<![a-zA-Z0-9])(BV[a-zA-Z0-9]{10})(?![a-zA-Z0-9])", url, re.IGNORECASE
    ):
        return bv_match.group(1), bilidata
    if av_match := re.search(r"(?<![a-zA-Z0-9])(?:AV|av)(\d+)", url):
        return av_match.group(1), bilidata
    if cv_match := re.search(r"(?<![a-zA-Z0-9])(?:CV|cv)(\d+)", url):
        return cv_match.group(1), biliarticledata
    if cv_mobile := re.search(r"bilibili\.com/read/mobile/(\d+)", url, re.IGNORECASE):
        return cv_mobile.group(1), biliarticledata

    # ── Twitter / X ───────────────────────────────────────────────────
    if tw_match := re.search(r"twitter\.com/[^/]+/status/(\d+)", url, re.IGNORECASE):
        return tw_match.group(1), twidata
    if x_match := re.search(r"x\.com/[^/]+/status/(\d+)", url, re.IGNORECASE):
        return x_match.group(1), twidata

    # ── Pixiv ─────────────────────────────────────────────────────────
    _pixiv_re = (
        r"pixiv\.(?:net|pixivdl\.com)"
        r"/(?:(?:artworks|i)/|member_illust\.php\?.*id=)(\d+)"
    )
    if pixiv_match := re.search(_pixiv_re, url, re.IGNORECASE):
        return pixiv_match.group(1), pixdata
    if pixn_match := re.search(
        r"pixiv\.net/novel/show\.php\?id=(\d+)", url, re.IGNORECASE
    ):
        return pixn_match.group(1), pixndata

    # ── NicoNico ──────────────────────────────────────────────────────
    if nico_match := re.search(r"nicovideo\.jp/watch/sm(\d+)", url, re.IGNORECASE):
        return nico_match.group(1), nicovideodata
    if seiga_match := re.search(
        r"seiga(?:\.nicovideo\.jp)?/(?:seiga/)?im(\d+)", url, re.IGNORECASE
    ):
        return seiga_match.group(1), nicoseigadata

    # ── YouTube ───────────────────────────────────────────────────────
    if yt_match := re.search(
        r"(?:youtu\.be/|youtube\.com/watch\?v=)([-\w]+)", url, re.IGNORECASE
    ):
        return yt_match.group(1), ytbdata

    # ── Weibo ─────────────────────────────────────────────────────────
    if wb_match := re.search(
        r"m\.weibo\.cn/(?:status|detail)/(\d+)", url, re.IGNORECASE
    ):
        return wb_match.group(1), wbdata

    # ── Tieba ─────────────────────────────────────────────────────────
    if tieba_match := re.search(r"tieba\.baidu\.com/p/(\d+)", url, re.IGNORECASE):
        return tieba_match.group(1), tiebadata

    # ── THBWiki ───────────────────────────────────────────────────────
    if thb_short := re.search(r"thwiki\.cc/(-/\w+)", url, re.IGNORECASE):
        return thb_short.group(1), thbdata
    if thb_match := re.search(r"thwiki\.cc/([-%/.\w]+)", url, re.IGNORECASE):
        return thb_match.group(1), thbdata

    # ── PatchyVideo ───────────────────────────────────────────────────
    if patchy_match := re.search(
        r"(?:thvideo\.tv|patchyvideo\.com)/#/video\?id=(\w+)", url, re.IGNORECASE
    ):
        return patchy_match.group(1), patchydata
    if patchy_dev := re.search(
        r"platinum\.vercel\.app/video/(\w+)", url, re.IGNORECASE
    ):
        return patchy_dev.group(1), patchydata

    # ── Steam ─────────────────────────────────────────────────────────
    if steam_match := re.search(
        r"store\.steampowered\.com/app/(\d+)", url, re.IGNORECASE
    ):
        return steam_match.group(1), steamdata

    # ── DLsite ────────────────────────────────────────────────────────
    if dlsite_match := re.search(r"dlsite\.com.+?(RJ\d+)", url, re.IGNORECASE):
        return dlsite_match.group(1), dlsitedata

    # ── Melonbooks ────────────────────────────────────────────────────
    if melon_match := re.search(
        r"melonbooks\.co\.jp.+?product_id=(\d+)", url, re.IGNORECASE
    ):
        return melon_match.group(1), melondata

    # ── Dizzylab ──────────────────────────────────────────────────────
    if dizzy_match := re.search(r"dizzylab\.net/d/([-\w]+)", url, re.IGNORECASE):
        return dizzy_match.group(1), dizzydata

    # ── AcFun ─────────────────────────────────────────────────────────
    if ac_match := re.search(r"acfun\.cn/v/(?:ac|\?ac=)(\d+)", url, re.IGNORECASE):
        return ac_match.group(1), acdata
    if aca_match := re.search(r"acfun\.cn/a/(?:ac|\?ac=)(\d+)", url, re.IGNORECASE):
        return aca_match.group(1), acadata

    return None, None
