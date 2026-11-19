"""DLsite scraper."""

from __future__ import annotations

import datetime as dt
import json
import re
from urllib.parse import urljoin

from lxml import etree

from src.apps.scraper.schemas import RespBody, ScrapeData
from src.apps.scraper.utils.cache import get_cache, set_cache
from src.apps.scraper.utils.network import request_abroad_website, wait_for_rate_limit

_HEADER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
}

_SOFT_TAGS = {
    "アクション",
    "クイズ",
    "アドベンチャー",
    "ロールプレイング",
    "テーブル",
    "デジタルノベル",
    "シミュレーション",
    "タイピング",
    "シューティング",
    "パズル",
    "その他ゲーム",
    "ツール/アクセサリ",
}
_IMAGE_TAGS = {"マンガ", "劇画", "WEBTOON", "CG・イラスト", "画像素材"}
_TEXT_TAGS = {"ノベル", "官能小説"}
_VIDEO_TAGS = {"動画", "ボイスコミック"}
_AUDIO_TAGS = {"音楽", "音素材", "ボイス・ASMR"}
_WORK_TYPES = {
    **dict.fromkeys(_SOFT_TAGS, "SOFTWARE"),
    **dict.fromkeys(_IMAGE_TAGS, "DRAWING"),
    **dict.fromkeys(_TEXT_TAGS, "ARTICLE"),
    **dict.fromkeys(_VIDEO_TAGS, "VIDEO"),
    **dict.fromkeys(_AUDIO_TAGS, "MUSIC"),
}


async def dlsitedata(rjid: str, udid: str | None = None) -> RespBody:
    """Scrape DLsite product page by RJ ID."""
    site = "dlsite"
    await wait_for_rate_limit(site, limit=0.1)
    if udid is None:
        udid = f"{site}:{rjid}"
    cached = await get_cache(udid)
    if cached:
        return cached

    url = f"https://www.dlsite.com/home/work/=/product_id/{rjid}.html"
    r = await request_abroad_website(url, headers=_HEADER)
    if not r.is_success:
        return RespBody(status="apierr", msg=f"dlsite: upstream HTTP {r.status_code}")
    try:
        page = etree.HTML(r.text)
        if page is None:
            return RespBody(status="parsererr", msg="dlsite: empty product page")
        outline = _work_outline(page)
        rating = outline.get("年齢指定")
        if rating is not None and _element_text(rating) != "全年齢":
            return RespBody(status="r18")

        product = _product_metadata(page, rjid)
        title = _element_text(next(iter(page.xpath('//*[@id="work_name"]')), None))
        title = title or product.get("name")
        if not title:
            return RespBody(status="parsererr", msg="dlsite: work_name not found")
        if rating is None:
            return RespBody(status="parsererr", msg="dlsite: age rating not found")

        maker = next(iter(page.xpath('//span[@class="maker_name"]/a')), None)
        brand = product.get("brand") or {}
        maker_url = maker.get("href", "") if maker is not None else brand.get("url", "")
        author_name = _element_text(maker) or brand.get("name")
        maker_id = re.search(r"maker_id[=/]([A-Za-z0-9]+)", maker_url)
        if not author_name or not maker_id:
            return RespBody(status="parsererr", msg="dlsite: maker not found")

        media, cover = _product_images(page, product.get("image"), url)
        desc = page.xpath('string(//meta[@property="og:description"]/@content)')
        ptime = _release_time(_element_text(outline.get("販売日")))
        work_types = _link_names(outline.get("作品形式"))
        tname = next(
            (_WORK_TYPES[name] for name in work_types if name in _WORK_TYPES), "OTHER"
        )
        genres = outline.get("ジャンル")
        warning = genres is not None and "東方Project" not in _link_names(genres)
    except Exception as exc:
        return RespBody(status="parsererr", msg=f"dlsiteparsererr: {repr(exc)}")

    result = RespBody(
        status="warning" if warning else "ok",
        msg="may not touhou" if warning else "",
        data=ScrapeData(
            title=title,
            udid=udid,
            cover=cover,
            media=media or None,
            desc=desc or product.get("description"),
            ptime=ptime,
            author=[maker_id.group(1)],
            author_name=[author_name],
            tname=tname,
        ),
    )
    await set_cache(udid, result)
    return result


def _element_text(element: etree._Element | None) -> str:
    return element.xpath("normalize-space(.)") if element is not None else ""


def _work_outline(page: etree._Element) -> dict[str, etree._Element]:
    labels = page.xpath('//table[@id="work_outline"]//th | //dt')
    fields = {}
    for label in labels:
        value = label.getnext()
        if value is not None and value.tag in ("td", "dd"):
            fields[_element_text(label)] = value
    return fields


def _product_metadata(page: etree._Element, rjid: str) -> dict:
    for script in page.xpath('//script[@type="application/ld+json"]/text()'):
        try:
            data = json.loads(script)
        except ValueError:
            continue
        if (
            isinstance(data, dict)
            and data.get("@type") == "Product"
            and data.get("sku") == rjid
        ):
            return data
    return {}


def _product_images(
    page: etree._Element, product_images: list[str] | str | None, url: str
) -> tuple[list[str], str | None]:
    media = []
    cover = None
    for slide in page.xpath('//div[@class="product-slider-data"]/div[@data-src]'):
        image = slide.get("data-src")
        if image:
            media.append(urljoin(url, image))
            if "img_main" in image and slide.get("data-thumb"):
                cover = urljoin(url, slide.get("data-thumb"))
    if not media and product_images:
        images = [product_images] if isinstance(product_images, str) else product_images
        media = [urljoin(url, image) for image in images if image]
    return media, cover or next(iter(media), None)


def _release_time(text: str) -> str | None:
    match = re.search(r"\d{4}年\d{1,2}月\d{1,2}日", text)
    if match is None:
        return None
    try:
        date = dt.datetime.strptime(match.group(), "%Y年%m月%d日")
    except ValueError:
        return None
    return date.strftime("%Y-%m-%d %H:%M:%S +0800")


def _link_names(element: etree._Element | None) -> list[str]:
    return (
        [_element_text(link) for link in element.xpath(".//a")]
        if element is not None
        else []
    )
