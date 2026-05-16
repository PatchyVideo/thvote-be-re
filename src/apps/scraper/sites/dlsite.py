"""DLsite scraper."""

from __future__ import annotations

import datetime as dt

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


async def dlsitedata(rjid: str, udid: str | None = None) -> RespBody:
    """Scrape DLsite product page by RJ ID."""
    site = "dlsite"
    await wait_for_rate_limit(site, limit=0.1)
    if udid is None:
        udid = f"{site}:{rjid}"
    cached = await get_cache(udid)
    if cached:
        return cached

    url = f"https://www.dlsite.com/home/work/=/product_id/{rjid}"
    r = await request_abroad_website(url, headers=_HEADER)
    html = r.content.decode("utf-8")
    try:
        page = etree.HTML(html)
        if page is None:
            return RespBody(status="r18")
        title_el = page.xpath('//*[@id="work_name"]')
        if not title_el:
            return RespBody(status="parsererr", msg="dlsite: work_name not found")
        title = title_el[0].text_content().strip()
        media: list[str] = []
        cover = None
        for image in page.xpath('//div[@class="product-slider-data"]/div'):
            img = image.attrib.get("data-src", "")
            if img:
                media.append(img.replace("//", "https://"))
            if "img_main" in img:
                thumb = image.attrib.get("data-thumb", "")
                if thumb:
                    cover = thumb.replace("//", "https://")
        if not cover and media:
            cover = media[0]
        desc_el = page.xpath('/html/head/meta[@property="og:description"]')
        desc = desc_el[0].attrib["content"] if desc_el else None
        maker_el = page.xpath('//span[@class="maker_name"]/a')
        if not maker_el:
            return RespBody(status="parsererr", msg="dlsite: maker not found")
        maker = maker_el[0]
        href = maker.attrib.get("href", "")
        author_id = href[href.find("maker_id") + 9 :].replace(".html", "")
        author_name = maker.text
        table = page.xpath('//table[@id="work_outline"]')
        if not table:
            return RespBody(
                status="parsererr", msg="dlsite: work_outline table not found"
            )
        heads = page.xpath('//table[@id="work_outline"]/tr/th/text()')
        status = "ok"
        msg = ""
        tname = "OTHER"
        ptime = None
        for index, head in enumerate(heads):
            if head == "販売日":
                time_els = table[0].xpath(f"//tr[{index + 1}]/td/a")
                if time_els:
                    time_str = time_els[0].text or ""
                    time_str = time_str[: time_str.find("日") + 1]
                    try:
                        dt_struct = dt.datetime.strptime(time_str, "%Y年%m月%d日")
                        ptime = dt_struct.strftime("%Y-%m-%d %H:%M:%S +0800")
                    except ValueError:
                        pass
            elif head == "年齢指定":
                age_els = table[0].xpath(f"//tr[{index + 1}]/td/div/span")
                if age_els and age_els[0].text != "全年齢":
                    return RespBody(status="r18")
            elif head == "作品形式":
                type_els = table[0].xpath(f"//tr[{index + 1}]/td/div/a/span")
                if type_els:
                    work_type = type_els[0].text or ""
                    if work_type in _SOFT_TAGS:
                        tname = "SOFTWARE"
                    elif work_type in _IMAGE_TAGS:
                        tname = "DRAWING"
                    elif work_type in _TEXT_TAGS:
                        tname = "ARTICLE"
                    elif work_type in _VIDEO_TAGS:
                        tname = "VIDEO"
                    elif work_type in _AUDIO_TAGS:
                        tname = "MUSIC"
            elif head == "ジャンル":
                tags = table[0].xpath(f"//tr[{index + 1}]/td/div/a//text()")
                if "東方Project" not in tags:
                    status = "warning"
                    msg = "may not touhou"
    except Exception as exc:
        return RespBody(status="parsererr", msg=f"dlsiteparsererr: {repr(exc)}")

    result = RespBody(
        status=status,
        msg=msg,
        data=ScrapeData(
            title=title,
            udid=udid,
            cover=cover,
            media=media or None,
            desc=desc,
            ptime=ptime,
            author=[author_id],
            author_name=[author_name],
            tname=tname,
        ),
    )
    await set_cache(udid, result)
    return result
