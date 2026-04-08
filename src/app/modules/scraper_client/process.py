"""Scraper core processor."""

from __future__ import annotations

import logging
import re
from typing import Any, Awaitable, Callable

from .schemas import RespBody
from .sites.bilibili import biliarticledata, bilidata
from .sites.pixiv import pixdata, pixndata
from .sites.twitter import twidata
from .utils.network import get_redirect_url

logger = logging.getLogger(__name__)

Parser = Callable[[str], Awaitable[RespBody]]


async def get_data(url: str) -> RespBody:
    try:
        wid, parser = await parse_url(url)
        if not wid or parser is None:
            return RespBody(status="err", msg="no content found")

        response = await parser(wid)
        if response.status == "rematch":
            return await get_data(response.msg)
        return response
    except Exception as exc:
        logger.exception("scraper error")
        return RespBody(status="except", msg=repr(exc))


async def parse_url(url: str) -> tuple[str | None, Parser | None]:
    url = url.strip()

    if b23_match := re.search(
        r"(?:https?://)?(?:(?:bili(?:22|23|33|2233)\.cn)|(?:b23\.tv))/[\w]+",
        url,
        re.IGNORECASE,
    ):
        redirect_url = await get_redirect_url(b23_match.group(0))
        if redirect_url:
            url = redirect_url

    if bv_match := re.search(r"(?<![a-zA-Z0-9])(BV[a-zA-Z0-9]{10})(?![a-zA-Z0-9])", url, re.IGNORECASE):
        return bv_match.group(1), bilidata

    if av_match := re.search(r"(?<![a-zA-Z0-9])(?:AV|av)(\d+)", url):
        return av_match.group(1), bilidata

    if cv_match := re.search(r"(?<![a-zA-Z0-9])(?:CV|cv)(\d+)", url):
        return cv_match.group(1), biliarticledata

    if cv_mobile := re.search(r"bilibili\.com/read/mobile/(\d+)", url, re.IGNORECASE):
        return cv_mobile.group(1), biliarticledata

    if tw_match := re.search(r"(?:twitter|x)\.com/[^/]+/status/(\d+)", url, re.IGNORECASE):
        return tw_match.group(1), twidata

    if pixiv_match := re.search(
        r"pixiv\.(?:net|pixivdl\.com)/(?:(?:artworks|i)/|member_illust\.php\?.*id=)(\d+)",
        url,
        re.IGNORECASE,
    ):
        return pixiv_match.group(1), pixdata

    if pixn_match := re.search(r"pixiv\.net/novel/show\.php\?id=(\d+)", url, re.IGNORECASE):
        return pixn_match.group(1), pixndata

    return None, None
