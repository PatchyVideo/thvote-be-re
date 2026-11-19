"""Scraper site parsers: mocked HTTP, deterministic field extraction.

B-063：`apps/scraper` 此前只有 URL 路由与限流测试，站点解析器（HTML/API
→ ScrapeData）完全没有覆盖。本文件先钉住三类最容易回归的站点：

- Steam：HTML 选择器（标题/封面/开发商/发售日）；
- THBWiki：MediaWiki ASK API 的 printouts 映射与无结果处理；
- Bilibili：JSON API 字段映射、音乐分区判定、-352 风控错误；
- Pixiv/YouTube：缺凭据时必须 fail-closed，不能打外网。

所有网络、Redis 缓存、限流均 mock，测试不依赖外网。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from src.apps.scraper import process
from src.apps.scraper.sites import bilibili, pixiv, steam, thbwiki, youtube

STEAM_HTML = """
<html><head><meta property="og:description" content="A Touhou game" /></head>
<body>
  <div id="appHubAppName">Touhou Test Game</div>
  <div id="gameHeaderImageCtn"><img src="https://cdn.example/cover.jpg?x=1" /></div>
  <div id="developers_list"><a>Team Ladybug</a></div>
  <div class="release_date"><div class="date">2024 年 01 月 02 日</div></div>
</body></html>
"""

THB_PAYLOAD = {
    "query": {
        "results": {
            "东方红魔乡": {
                "fulltext": "东方红魔乡",
                "printouts": {
                    "封面图片": [{"exists": "1", "fulltext": "文件:cover.png"}],
                    "发售日期": [{"timestamp": "1700000000"}],
                    "制作方": [{"fulltext": "上海爱丽丝幻乐团"}],
                    "软件名称": [{"fulltext": "东方红魔乡"}],
                },
            }
        }
    }
}

BILI_PAYLOAD = {
    "code": 0,
    "data": {
        "title": "Touhou Test Video",
        "pic": "http://i0.hdslb.com/cover.jpg",
        "desc": "description",
        "pubdate": 1700000000,
        "owner": {"mid": 123, "name": "UP Name"},
        "tname": "原创音乐",
        "copyright": 1,
    },
}


def _silence_cache(monkeypatch, module) -> None:
    monkeypatch.setattr(module, "get_cache", AsyncMock(return_value=None))
    monkeypatch.setattr(module, "set_cache", AsyncMock())
    monkeypatch.setattr(module, "wait_for_rate_limit", AsyncMock())


@pytest.mark.asyncio
async def test_steam_parses_html_fields(monkeypatch):
    _silence_cache(monkeypatch, steam)

    async def fake_request(url, **kwargs):
        return httpx.Response(200, content=STEAM_HTML.encode())

    monkeypatch.setattr(steam, "request_abroad_website", fake_request)

    result = await steam.steamdata("851100")

    assert result.status == "ok"
    assert result.data.title == "Touhou Test Game"
    assert result.data.cover == "https://cdn.example/cover.jpg"
    assert result.data.author_name == ["Team Ladybug"]
    assert result.data.tname == "SOFTWARE"
    assert result.data.ptime == "2024-01-02 00:00:00 +0800"


@pytest.mark.asyncio
async def test_steam_missing_title_is_parser_error(monkeypatch):
    _silence_cache(monkeypatch, steam)

    async def fake_request(url, **kwargs):
        return httpx.Response(200, content=b"<html><body>no title</body></html>")

    monkeypatch.setattr(steam, "request_abroad_website", fake_request)

    result = await steam.steamdata("851100")
    assert result.status == "parsererr"
    assert "appHubAppName" in result.msg


@pytest.mark.asyncio
async def test_thbwiki_maps_ask_printouts(monkeypatch):
    _silence_cache(monkeypatch, thbwiki)

    async def fake_request(url, **kwargs):
        return httpx.Response(200, json=THB_PAYLOAD)

    monkeypatch.setattr(thbwiki, "request_abroad_website", fake_request)
    monkeypatch.setattr(
        thbwiki, "_get_cover", AsyncMock(return_value="https://img.example/cover.png")
    )

    result = await thbwiki.thbdata("东方红魔乡")

    assert result.status == "ok"
    assert result.data.title == "东方红魔乡"
    assert result.data.cover == "https://img.example/cover.png"
    assert result.data.author == ["thbwiki-author:上海爱丽丝幻乐团"]
    assert result.data.author_name == ["上海爱丽丝幻乐团"]
    assert result.data.tname == "SOFTWARE"


@pytest.mark.asyncio
async def test_thbwiki_no_result(monkeypatch):
    _silence_cache(monkeypatch, thbwiki)

    async def fake_request(url, **kwargs):
        return httpx.Response(200, json={"query": {"results": {}}})

    monkeypatch.setattr(thbwiki, "request_abroad_website", fake_request)

    result = await thbwiki.thbdata("不存在的词条")
    assert result.status == "apierr"
    assert "no result" in result.msg


@pytest.mark.asyncio
async def test_thbwiki_uses_game_genre_when_software_name_is_absent(monkeypatch):
    _silence_cache(monkeypatch, thbwiki)
    payload = {
        "query": {
            "results": {
                "东方红魔乡": {
                    "fulltext": "东方红魔乡",
                    "printouts": {"游戏类型": ["弹幕射击游戏"]},
                }
            }
        }
    }
    request = AsyncMock(return_value=httpx.Response(200, json=payload))
    monkeypatch.setattr(thbwiki, "request_abroad_website", request)

    result = await thbwiki.thbdata("东方红魔乡")

    assert "?游戏类型" in request.call_args.kwargs["params"]["query"]
    thbwiki.get_cache.assert_awaited_once_with("v2:thbwiki:东方红魔乡")
    assert result.data.udid == "thbwiki:东方红魔乡"
    assert result.data.tname == "SOFTWARE"


@pytest.mark.asyncio
async def test_bilibili_maps_json_and_music_area(monkeypatch):
    _silence_cache(monkeypatch, bilibili)
    monkeypatch.setattr(bilibili, "get_header", lambda: {})
    monkeypatch.setattr(bilibili, "get_cookies", AsyncMock(return_value={}))
    monkeypatch.setattr(bilibili, "request_api", AsyncMock(return_value=BILI_PAYLOAD))

    result = await bilibili.bilidata("BV1xx411c7mD")

    assert result.status == "ok"
    assert result.data.title == "Touhou Test Video"
    assert result.data.cover == "https://i0.hdslb.com/cover.jpg"
    assert result.data.tname == "MUSIC"
    assert result.data.author_name == ["UP Name"]
    assert result.data.repost is False


@pytest.mark.asyncio
async def test_bilibili_banned_returns_apierr(monkeypatch):
    _silence_cache(monkeypatch, bilibili)
    monkeypatch.setattr(bilibili, "get_header", lambda: {})
    monkeypatch.setattr(bilibili, "get_cookies", AsyncMock(return_value={}))
    monkeypatch.setattr(
        bilibili,
        "request_api",
        AsyncMock(return_value={"code": -352, "message": "banned"}),
    )

    result = await bilibili.bilidata("BV1xx411c7mD")
    assert result.status == "apierr"
    assert result.msg == "biliapi: banned"


@pytest.mark.asyncio
async def test_bilibili_opus_uses_article_metadata_only(monkeypatch):
    _silence_cache(monkeypatch, bilibili)
    basic = {"comment_type": 12, "comment_id_str": "14689807"}
    state = {
        "detail": {
            "basic": basic,
            "modules": [
                {
                    "module_type": "MODULE_TYPE_TITLE",
                    "module_title": {"text": "Touhou; article"},
                },
                {
                    "module_type": "MODULE_TYPE_AUTHOR",
                    "module_author": {
                        "mid": 9,
                        "name": "Author",
                        "pub_ts": "1641211275",
                    },
                },
                {
                    "module_type": "MODULE_TYPE_TOP",
                    "module_top": {
                        "display": {
                            "album": {"pics": [{"url": "https://img.example/1.jpg"}]}
                        }
                    },
                },
            ],
        }
    }
    request = AsyncMock()
    monkeypatch.setattr(bilibili, "request_website", request)
    request.return_value = httpx.Response(
        200,
        text=f"<script>window.__INITIAL_STATE__={json.dumps(state)};extra()</script>",
    )

    result = await bilibili.biliopusdata("611486841963400434")

    assert result.status == "ok"
    assert result.data.udid == "biliarticle:14689807"
    assert result.data.title == "Touhou; article"
    assert result.data.author_name == ["Author"]
    assert result.data.cover == "https://img.example/1.jpg"

    basic["comment_type"] = 17
    request.return_value = httpx.Response(
        200, text=f"<script>window.__INITIAL_STATE__={json.dumps(state)};</script>"
    )
    assert (await bilibili.biliopusdata("611486841963400434")).status == "err"

    request.return_value = httpx.Response(412)
    assert (await bilibili.biliopusdata("611486841963400434")).status == "apierr"


@pytest.mark.asyncio
async def test_pixiv_without_credentials_fails_closed(monkeypatch):
    _silence_cache(monkeypatch, pixiv)
    monkeypatch.setattr(pixiv, "_get_pixiv_token", AsyncMock(return_value=None))

    result = await pixiv.pixdata("123456")
    assert result.status == "err"
    assert result.msg == "Pixiv authentication failed"


@pytest.mark.asyncio
async def test_youtube_without_api_key_fails_closed(monkeypatch):
    monkeypatch.setattr(
        "src.common.config.get_settings",
        lambda: SimpleNamespace(youtube_api_key=None),
    )

    result = await youtube.ytbdata("abc123")
    assert result.status == "apierr"
    assert "YOUTUBE_API_KEY" in result.msg


@pytest.mark.asyncio
async def test_unsupported_url_returns_err():
    result = await process.get_data("https://example.com/some-work")
    assert result.status == "err"
    assert result.msg == "no content found"


@pytest.mark.asyncio
async def test_parser_exception_is_wrapped_as_except(monkeypatch):
    async def boom(wid):
        raise RuntimeError("boom")

    monkeypatch.setattr(process, "parse_url", AsyncMock(return_value=("x", boom)))
    result = await process.get_data("https://example.com/x")
    assert result.status == "except"
    assert "boom" in result.msg


DL_HTML = (
    '<html><head><meta property="og:description" content="DL desc" />'
    "<body>"
    '<div id="work_name">东方同人音乐</div>'
    '<div class="product-slider-data">'
    '<div data-src="//img.example/img_main.jpg" '
    'data-thumb="//img.example/thumb.jpg"></div>'
    "</div>"
    '<span class="maker_name"><a href="https://www.dlsite.com/home/circle/'
    'profile/=/maker_id/RG123.html">社团名</a></span>'
    '<table id="work_outline">'
    "<tr><th>販売日</th><td><a>2024年01月02日</a></td></tr>"
    "<tr><th>年齢指定</th><td><div><span>全年齢</span></div></td></tr>"
    "<tr><th>作品形式</th><td><div><a><span>音楽</span></a></div></td></tr>"
    "<tr><th>ジャンル</th><td><div><a>東方Project</a></div></td></tr>"
    "</table></body></html>"
)


DIZZY_HTML = """
<html><head><title>Album</title>
  <link rel="shortcut icon" href="https://img.example/dizzy-cover.jpg" />
  <meta name="description" content="Dizzy desc" />
</head><body>
  <div class="col">
    <h1>Dizzy Album</h1>
    <h4><a>@ Artist Name</a></h4>
    <p class="text-left">发布于2024年01月02日</p>
  </div>
  <ul class="playlist--list"><li data-audio="https://audio.example/1.mp3"></li></ul>
</body></html>
"""

MELON_HTML = """
<html><head><title>Melon Album の通販・購入</title>
  <meta property="og:image" content="https://img.example/melon-cover.jpg" />
  <meta property="og:description" content="Melon desc" />
</head><body>
  <div id="thumbs"><ul><li><div><a href="//img.example/1.jpg"></a></div></li></ul></div>
  <div id="contents">
    <div>header</div>
    <div>
      <div><p><a href="/circle/detail/=/circle_id=123.html">Melon Circle</a></p></div>
      <div><div><div><div><div>2024年01月02日</div></div></div></div></div></div>
    </div>
  </div>
</body></html>
"""


@pytest.mark.asyncio
async def test_dlsite_parses_work_outline(monkeypatch):
    from src.apps.scraper.sites import dlsite

    _silence_cache(monkeypatch, dlsite)

    async def fake_request(url, **kwargs):
        return httpx.Response(200, content=DL_HTML.encode())

    monkeypatch.setattr(dlsite, "request_abroad_website", fake_request)

    result = await dlsite.dlsitedata("RJ123456")

    assert result.status == "ok"
    assert result.data.title == "东方同人音乐"
    assert result.data.author_name == ["社团名"]
    assert result.data.author == ["RG123"]
    assert result.data.tname == "MUSIC"
    assert result.data.cover == "https://img.example/thumb.jpg"


@pytest.mark.asyncio
async def test_dlsite_r18_returns_r18(monkeypatch):
    from src.apps.scraper.sites import dlsite

    _silence_cache(monkeypatch, dlsite)

    async def fake_request(url, **kwargs):
        html = (
            "<html><body><div id='work_name'>x</div>"
            "<span class='maker_name'><a href='maker_id/RG1.html'>a</a></span>"
            "<table id='work_outline'><tr><th>年齢指定</th>"
            "<td><div><span>成人向け</span></div></td></tr></table></body></html>"
        )
        return httpx.Response(200, content=html.encode())

    monkeypatch.setattr(dlsite, "request_abroad_website", fake_request)

    result = await dlsite.dlsitedata("RJ123456")
    assert result.status == "r18"


@pytest.mark.asyncio
async def test_dlsite_reads_modern_product_metadata_and_rating(monkeypatch):
    from src.apps.scraper.sites import dlsite

    _silence_cache(monkeypatch, dlsite)
    html = """
    <html><head>
      <script type="application/ld+json">{"@type":"WebSite","name":"DLsite"}</script>
      <script type="application/ld+json">
        {"@type":"Product","sku":"RJ254841","name":"Touhou game",
         "brand":{"name":"Game Circle",
                  "url":"/home/circle/profile/=/maker_id/RG46179.html"},
         "image":["https://img.dlsite.jp/main.jpg", "//img.dlsite.jp/sample.jpg"]}
      </script>
    </head><body>
      <h1 id="work_name">Touhou game</h1>
      <dl>
        <div><dt>販売日</dt><dd><a>2019年5月31日</a></dd></div>
        <div><dt>年齢指定</dt><dd><span>全年齢</span></dd></div>
        <div><dt>作品形式</dt><dd><a>シューティング</a><span>音楽あり</span></dd></div>
        <div><dt>ジャンル</dt><dd><a>東方Project</a></dd></div>
      </dl>
    </body></html>
    """
    request = AsyncMock(return_value=httpx.Response(200, text=html))
    monkeypatch.setattr(dlsite, "request_abroad_website", request)

    result = await dlsite.dlsitedata("RJ254841")

    assert request.call_args.args[0].endswith("/RJ254841.html")
    assert result.status == "ok"
    assert result.data.title == "Touhou game"
    assert result.data.author == ["RG46179"]
    assert result.data.author_name == ["Game Circle"]
    assert result.data.tname == "SOFTWARE"
    assert result.data.ptime == "2019-05-31 00:00:00 +0800"
    assert result.data.cover == "https://img.dlsite.jp/main.jpg"
    assert result.data.media == [
        "https://img.dlsite.jp/main.jpg",
        "https://img.dlsite.jp/sample.jpg",
    ]

    request.return_value = httpx.Response(200, text=html.replace("全年齢", "成人向け"))
    assert (await dlsite.dlsitedata("RJ254841")).status == "r18"


@pytest.mark.asyncio
async def test_dizzylab_parses_album(monkeypatch):
    from src.apps.scraper.sites import dizzylab

    _silence_cache(monkeypatch, dizzylab)

    async def fake_request(url, **kwargs):
        return httpx.Response(200, content=DIZZY_HTML.encode())

    monkeypatch.setattr(dizzylab, "request_website", fake_request)

    result = await dizzylab.dizzydata("ABC-001")

    assert result.status == "ok"
    assert result.data.title == "Dizzy Album"
    assert result.data.author_name == ["Artist Name"]
    assert result.data.tname == "MUSIC"
    assert result.data.media == ["https://audio.example/1.mp3"]


@pytest.mark.asyncio
async def test_melon_parses_product(monkeypatch):
    from src.apps.scraper.sites import melon

    _silence_cache(monkeypatch, melon)

    async def fake_request(url, **kwargs):
        return httpx.Response(200, content=MELON_HTML.encode())

    monkeypatch.setattr(melon, "request_abroad_website", fake_request)

    result = await melon.melondata("123456")

    assert result.status == "ok"
    assert result.data.title == "Melon Album"
    assert result.data.author_name == ["Melon Circle"]
    assert result.data.author == ["melonbooks-author:123"]
    assert result.data.cover == "https://img.example/melon-cover.jpg"


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [200, 403])
async def test_melon_reports_overseas_access_restriction(monkeypatch, status_code):
    from src.apps.scraper.sites import melon

    _silence_cache(monkeypatch, melon)
    html = "<html><head><title>海外からのアクセス制限につきまして</title></head></html>"
    monkeypatch.setattr(
        melon,
        "request_abroad_website",
        AsyncMock(return_value=httpx.Response(status_code, text=html)),
    )

    result = await melon.melondata("3858061")

    assert result.status == "apierr"
    assert result.data is None


# ── 其余站点的 fail-closed 路径 ──────────────────────────────────────
# 不追求每个站点都造成功 fixture，但必须保证：页面结构变化/缺凭据时
# 返回结构化 parsererr/apierr，而不是把异常抛给 API 层变成 500。


async def _empty_response(monkeypatch, module, fn, arg, expected_msg):
    _silence_cache(monkeypatch, module)

    async def fake_request(url, **kwargs):
        return httpx.Response(200, content=b"<html><body>empty</body></html>")

    for name in ("request_website", "request_abroad_website"):
        if hasattr(module, name):
            monkeypatch.setattr(module, name, fake_request)
    result = await fn(arg)
    assert result.status == "parsererr"
    assert expected_msg in result.msg


@pytest.mark.asyncio
async def test_acfun_missing_script(monkeypatch):
    from src.apps.scraper.sites import acfun

    await _empty_response(monkeypatch, acfun, acfun.acdata, "123", "script not found")


@pytest.mark.asyncio
async def test_acarticle_missing_script(monkeypatch):
    from src.apps.scraper.sites import acarticle

    await _empty_response(
        monkeypatch, acarticle, acarticle.acadata, "123", "main script not found"
    )


@pytest.mark.asyncio
async def test_acarticle_decodes_assignment_with_semicolons_in_content(monkeypatch):
    from src.apps.scraper.sites import acarticle

    _silence_cache(monkeypatch, acarticle)
    html = """
    <main id="main">
      <script>window.other = {};</script>
      <script>
        window.articleInfo = {
          "title":"Article","description":"One; two; three;",
          "coverUrl":"https://img.example/cover.png?size=100",
          "createTimeMillis":1700000000000, "user":{"id":9,"name":"Author"},
          "channel":{"name":"动漫"},"realm":{"realmName":"漫画文学"}
        };
        window.likeDomain = "https://example.com";
      </script>
    </main>
    """
    monkeypatch.setattr(
        acarticle,
        "request_website",
        AsyncMock(return_value=httpx.Response(200, text=html)),
    )

    result = await acarticle.acadata("1115033")

    assert result.status == "ok"
    assert result.data.title == "Article"
    assert result.data.desc == "One; two; three;"
    assert result.data.author_name == ["Author"]
    assert result.data.cover == "https://img.example/cover.png"


@pytest.mark.asyncio
async def test_nicovideo_missing_ldjson(monkeypatch):
    from src.apps.scraper.sites import nicovideo
    from src.apps.scraper.sites.nicovideo import nicovideodata

    _silence_cache(monkeypatch, nicovideo)

    async def fake_request(url, **kwargs):
        return httpx.Response(200, content=b"<html></html>")

    monkeypatch.setattr(nicovideo, "request_abroad_website", fake_request)
    result = await nicovideodata("sm123")
    assert result.status == "parsererr"
    assert "no video JSON-LD" in result.msg


@pytest.mark.asyncio
async def test_nicovideo_selects_video_jsonld_from_multiple_scripts(monkeypatch):
    from src.apps.scraper.sites import nicovideo

    _silence_cache(monkeypatch, nicovideo)
    html = """
    <html><head>
      <script type="application/ld+json">{"@type":"WebSite","name":"niconico"}</script>
      <script data-server="1" type="application/ld+json">
        {"@type":"VideoObject", "name":"Bad Apple!!",
         "author":{"name":"Uploader","url":"https://www.nicovideo.jp/user/123"},
         "uploadDate":"2009-10-27T03:31:33+09:00",
         "thumbnailUrl":["https://img.example/cover.jpg"]}
      </script>
    </head></html>
    """
    monkeypatch.setattr(
        nicovideo,
        "request_abroad_website",
        AsyncMock(return_value=httpx.Response(200, text=html)),
    )

    result = await nicovideo.nicovideodata("8628149")

    assert result.status == "ok"
    assert result.data.title == "Bad Apple!!"
    assert result.data.author == ["nicovideo-author:123"]
    assert result.data.author_name == ["Uploader"]
    assert result.data.cover == "https://img.example/cover.jpg"
    assert result.data.ptime == "2009-10-27 02:31:33 +0800"


@pytest.mark.asyncio
async def test_nicoseiga_missing_title(monkeypatch):
    from src.apps.scraper.sites import nicoseiga

    await _empty_response(
        monkeypatch, nicoseiga, nicoseiga.nicoseigadata, "123", "title not found"
    )


@pytest.mark.asyncio
async def test_nicoseiga_empty_response_has_a_structured_error(monkeypatch):
    from src.apps.scraper.sites import nicoseiga

    _silence_cache(monkeypatch, nicoseiga)
    request = AsyncMock(return_value=httpx.Response(200))
    monkeypatch.setattr(nicoseiga, "request_abroad_website", request)

    result = await nicoseiga.nicoseigadata("11217962")
    assert result.status == "parsererr"
    assert result.msg == "nicoseiga: title not found"

    request.return_value = httpx.Response(403)
    result = await nicoseiga.nicoseigadata("11217962")
    assert result.status == "apierr"
    assert result.msg == "nicoseiga: upstream HTTP 403"


@pytest.mark.asyncio
async def test_tieba_missing_post_list(monkeypatch):
    from src.apps.scraper.sites import tieba

    await _empty_response(
        monkeypatch, tieba, tieba.tiebadata, "123", "postList script not found"
    )


@pytest.mark.asyncio
async def test_weibo_missing_render_data(monkeypatch):
    from src.apps.scraper.sites import weibo

    await _empty_response(
        monkeypatch, weibo, weibo.wbdata, "123", "render data not found"
    )


@pytest.mark.asyncio
async def test_weibo_reads_nested_render_data_and_reports_visitor_redirect(monkeypatch):
    from src.apps.scraper.sites import weibo

    _silence_cache(monkeypatch, weibo)
    html = """
    <script>
      var $render_data = [{
        "status":{"user":{"id":9,"screen_name":"Author"},"text":"Post",
                  "pics":[{"url":"https://img.example/one.jpg"}],
                  "created_at":"Thu Jan 02 00:00:00 +0800 2025"}
      }];
    </script>
    """
    request = AsyncMock(return_value=httpx.Response(200, text=html))
    monkeypatch.setattr(weibo, "request_website", request)

    result = await weibo.wbdata("123")

    assert result.status == "ok"
    assert result.data.title == "Author的微博"
    assert result.data.author_name == ["Author"]
    assert result.data.desc == "Post"

    request.return_value = httpx.Response(
        302, headers={"Location": "https://visitor.passport.weibo.cn/visitor/visitor"}
    )
    result = await weibo.wbdata("123")
    assert result.status == "apierr"
    assert "requires a visitor session" in result.msg


@pytest.mark.asyncio
async def test_twitter_without_bearer_token(monkeypatch):
    from src.apps.scraper.sites import twitter

    _silence_cache(monkeypatch, twitter)
    monkeypatch.delenv("TWITTER_BEARER_TOKEN", raising=False)

    result = await twitter.twidata("123")
    assert result.status == "err"
    assert result.msg == "Twitter API token not configured"


@pytest.mark.asyncio
async def test_pixiv_novel_without_credentials(monkeypatch):
    _silence_cache(monkeypatch, pixiv)
    monkeypatch.setattr(pixiv, "_get_pixiv_token", AsyncMock(return_value=None))

    result = await pixiv.pixndata("123")
    assert result.status == "err"
    assert result.msg == "Pixiv authentication failed"
