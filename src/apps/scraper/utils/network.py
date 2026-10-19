"""Scraper network utilities.

Provides HTTP request functionality for scraping.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx


async def get_redirect_url(url: str, proxy: str | None = None) -> str | None:
    """Get redirect URL from short URLs (like b23.tv).

    Args:
        url: Short URL to resolve
        proxy: Optional proxy URL

    Returns:
        Redirected URL or None
    """
    client_kwargs: dict[str, Any] = {"follow_redirects": False}
    if proxy:
        client_kwargs["proxy"] = proxy
    async with httpx.AsyncClient(**client_kwargs) as client:
        try:
            response = await client.head(url, timeout=10.0)
            return response.headers.get("Location")
        except Exception:
            return None


async def request_website(url: str, **kwargs: Any) -> httpx.Response:
    """Send HTTP request to a website (optional proxy).

    Args:
        url: Target URL
        **kwargs: Additional httpx arguments

    Returns:
        HTTP response
    """
    timeout = kwargs.pop("timeout", 30.0)
    proxy = kwargs.pop("proxy", None)
    client_kwargs = dict(kwargs)
    if proxy:
        client_kwargs["proxy"] = proxy
    async with httpx.AsyncClient(**client_kwargs) as client:
        if kwargs.get("data") or kwargs.get("json"):
            response = await client.post(url=url, timeout=timeout)
        elif kwargs.pop("method", None) == "post":
            response = await client.post(url=url, timeout=timeout)
        else:
            response = await client.get(url=url, timeout=timeout)
        return response


async def request_api(url: str, **kwargs: Any) -> dict[str, Any]:
    """Send HTTP request to an API endpoint (optional proxy).

    Args:
        url: Target API URL
        **kwargs: Additional httpx arguments (headers, cookies, etc.)

    Returns:
        JSON response as dict
    """
    timeout = kwargs.pop("timeout", 30.0)
    proxy = kwargs.pop("proxy", None)
    client_kwargs: dict[str, Any] = {"follow_redirects": True}
    if proxy:
        client_kwargs["proxy"] = proxy
    async with httpx.AsyncClient(**client_kwargs) as client:
        if kwargs.get("data") or kwargs.get("json"):
            response = await client.post(url=url, timeout=timeout, **kwargs)
        elif kwargs.pop("method", None) == "post":
            response = await client.post(url=url, timeout=timeout, **kwargs)
        else:
            response = await client.get(url=url, timeout=timeout, **kwargs)

        # Debug: check if response is valid JSON
        text = response.text
        if not text or not text.strip():
            raise ValueError(
                f"Empty response from {url}, status={response.status_code}"
            )

        try:
            return response.json()
        except Exception:
            raise ValueError(f"Invalid JSON from {url}: {text[:200]}")


async def wait_for_rate_limit(site: str, limit: float) -> None:
    """Wait for rate limit interval.

    Args:
        site: Site name for rate limiting
        limit: Minimum interval between requests in seconds
    """
    from src.apps.scraper.utils.cache import get_rate_limit_last, set_rate_limit_last

    last = await get_rate_limit_last(site)
    if last:
        elapsed = time.time() - last
        if elapsed < limit:
            await asyncio.sleep(limit - elapsed)

    await set_rate_limit_last(site, time.time())


# Aliases for sites that were "abroad" in the old backend
# In the new backend there is no proxy distinction - same client is used
request_abroad_website = request_website
request_abroad_api = request_api
