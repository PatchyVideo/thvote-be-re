"""Bilibili 访客 Cookie 自动获取（不依赖账号）。

背景：旧 Rust/Python 后端靠部署机 config.toml 里的 SESSDATA 才能请求
B 站 API；新部署没有账号 Cookie 时只会发随机 buvid3，被风控成 HTML。
这里钉住访客方案：/x/frontend/finger/spi → b_3/b_4 + b_nut，缓存 12h。
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from src.apps.scraper.utils import biliutils


@pytest.fixture(autouse=True)
def _clear_bili_env(monkeypatch):
    for name in (
        "BILIBILI_SESSDATA",
        "BILIBILI_B_LSID",
        "BILIBILI_B_NUT",
        "BILIBILI_BUVID3",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.asyncio
async def test_guest_cookies_fetched_and_cached(monkeypatch):
    monkeypatch.setattr(biliutils, "get_cache", AsyncMock(return_value=None))
    set_cache = AsyncMock()
    monkeypatch.setattr(biliutils, "set_cache", set_cache)
    monkeypatch.setattr(
        biliutils,
        "request_api",
        AsyncMock(return_value={"code": 0, "data": {"b_3": "B3", "b_4": "B4"}}),
    )

    cookies = await biliutils.get_cookies()

    assert cookies["buvid3"] == "B3"
    assert cookies["buvid4"] == "B4"
    assert cookies["b_nut"].isdigit()
    set_cache.assert_awaited_once()
    key, value = set_cache.await_args.args
    assert key == "bilibili_guest_cookies"
    assert value["buvid3"] == "B3"
    assert set_cache.await_args.kwargs["ex"] == timedelta(hours=12)


@pytest.mark.asyncio
async def test_cached_guest_cookies_skip_network(monkeypatch):
    cached = {"buvid3": "CACHED", "buvid4": "C4", "b_nut": "1700000000"}
    monkeypatch.setattr(biliutils, "get_cache", AsyncMock(return_value=cached))
    monkeypatch.setattr(biliutils, "set_cache", AsyncMock())
    request_api = AsyncMock()
    monkeypatch.setattr(biliutils, "request_api", request_api)

    cookies = await biliutils.get_cookies()

    assert cookies == cached
    request_api.assert_not_awaited()


@pytest.mark.asyncio
async def test_env_cookies_override_guest_bootstrap(monkeypatch):
    monkeypatch.setenv("BILIBILI_SESSDATA", "SESS")
    monkeypatch.setenv("BILIBILI_BUVID3", "ENV3")
    monkeypatch.setenv("BILIBILI_B_NUT", "1700000000")
    request_api = AsyncMock()
    monkeypatch.setattr(biliutils, "request_api", request_api)

    cookies = await biliutils.get_cookies()

    assert cookies == {
        "SESSDATA": "SESS",
        "buvid3": "ENV3",
        "b_nut": "1700000000",
    }
    request_api.assert_not_awaited()


@pytest.mark.asyncio
async def test_spi_failure_falls_back_to_random_buvid3(monkeypatch):
    monkeypatch.setattr(biliutils, "get_cache", AsyncMock(return_value=None))
    monkeypatch.setattr(biliutils, "set_cache", AsyncMock())
    monkeypatch.setattr(
        biliutils,
        "request_api",
        AsyncMock(side_effect=ValueError("Invalid JSON from spi")),
    )

    cookies = await biliutils.get_cookies()

    assert cookies.get("buvid3")
    assert "buvid4" not in cookies


@pytest.mark.asyncio
async def test_redis_outage_does_not_block_guest_bootstrap(monkeypatch):
    monkeypatch.setattr(
        biliutils, "get_cache", AsyncMock(side_effect=ConnectionError("redis down"))
    )
    set_cache = AsyncMock()
    monkeypatch.setattr(biliutils, "set_cache", set_cache)
    monkeypatch.setattr(
        biliutils,
        "request_api",
        AsyncMock(return_value={"data": {"b_3": "B3", "b_4": "B4"}}),
    )

    cookies = await biliutils.get_cookies()

    assert cookies["buvid3"] == "B3"
    set_cache.assert_awaited_once()
