"""Scraper network utilities.

Provides HTTP request functionality for scraping.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from .cache import get_rate_limit_last, set_rate_limit_last


async def get_redirect_url(url: str) -> str | None:
    """Get redirect URL from short URLs (like b23.tv)."""
    async with httpx.AsyncClient(follow_redirects=False) as client:
        try:
            response = await client.head(url, timeout=10.0)
            return response.headers.get("Location")
        except Exception:
            return None


async def request_website(url: str, **kwargs: Any) -> httpx.Response:
    """Send HTTP request to a website (no proxy)."""
    timeout = kwargs.pop("timeout", 30.0)
    async with httpx.AsyncClient(**kwargs) as client:
        if kwargs.get("data") or kwargs.get("json"):
            response = await client.post(url=url, timeout=timeout)
        elif kwargs.pop("method", None) == "post":
            response = await client.post(url=url, timeout=timeout)
        else:
            response = await client.get(url=url, timeout=timeout)
        return response


async def request_api(url: str, **kwargs: Any) -> dict[str, Any]:
    """Send HTTP request to an API endpoint (no proxy)."""
    timeout = kwargs.pop("timeout", 30.0)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        if kwargs.get("data") or kwargs.get("json"):
            response = await client.post(url=url, timeout=timeout, **kwargs)
        elif kwargs.pop("method", None) == "post":
            response = await client.post(url=url, timeout=timeout, **kwargs)
        else:
            response = await client.get(url=url, timeout=timeout, **kwargs)

        text = response.text
        if not text or not text.strip():
            raise ValueError(f"Empty response from {url}, status={response.status_code}")

        try:
            return response.json()
        except Exception:
            raise ValueError(f"Invalid JSON from {url}: {text[:200]}")


async def wait_for_rate_limit(site: str, limit: float) -> None:
    """Wait for rate limit interval."""
    last = await get_rate_limit_last(site)
    if last is not None:
        elapsed = time.time() - last
        if elapsed < limit:
            await asyncio.sleep(limit - elapsed)
    await set_rate_limit_last(site, time.time())
