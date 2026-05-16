"""OAuth HTTP helpers for QQ Connect and THBWiki (MediaWiki OAuth2).

Each function handles the token-exchange leg of the Authorization Code flow
and returns only the user identifier needed to link/create an account.
All network I/O is done with aiohttp to stay non-blocking.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.parse
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

_QQ_TOKEN_URL = "https://graph.qq.com/oauth2.0/token"
_QQ_ME_URL = "https://graph.qq.com/oauth2.0/me"
_QQ_AUTHORIZE_URL = "https://graph.qq.com/oauth2.0/authorize"

_THBWIKI_TOKEN_URL = "https://thwiki.cc/wiki/Special:OAuth/access_token"
_THBWIKI_AUTHORIZE_URL = "https://thwiki.cc/wiki/Special:OAuth/authorize"


def qq_authorize_url(app_id: str, redirect_uri: str, state: str) -> str:
    """Build the QQ Connect authorization redirect URL."""
    params = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": app_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": "get_user_info",
        }
    )
    return f"{_QQ_AUTHORIZE_URL}?{params}"


def thbwiki_authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    """Build the THBWiki OAuth2 authorization redirect URL."""
    params = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": "basic",
        }
    )
    return f"{_THBWIKI_AUTHORIZE_URL}?{params}"


async def qq_exchange_code(
    code: str,
    app_id: str,
    app_secret: str,
    redirect_uri: str,
) -> str:
    """Exchange a QQ Connect authorization code for the user's openid.

    QQ OAuth2 uses a non-standard two-step process:
      1. Exchange code -> access_token (query-string or JSON response)
      2. Fetch /me with access_token -> JSONP response containing openid

    Returns:
        The user's QQ openid string.

    Raises:
        ValueError: if the exchange or openid fetch fails.
    """
    async with aiohttp.ClientSession() as session:
        params = {
            "grant_type": "authorization_code",
            "client_id": app_id,
            "client_secret": app_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "fmt": "json",
        }
        resp = await session.get(_QQ_TOKEN_URL, params=params)
        text = await resp.text()

        access_token: Optional[str] = None
        try:
            data = json.loads(text)
            if "access_token" not in data:
                raise ValueError(f"QQ token exchange error: {data}")
            access_token = data["access_token"]
        except (json.JSONDecodeError, TypeError):
            qs = urllib.parse.parse_qs(text)
            if "access_token" not in qs:
                raise ValueError(f"QQ token exchange failed: {text!r}")
            access_token = qs["access_token"][0]

        resp2 = await session.get(_QQ_ME_URL, params={"access_token": access_token})
        text2 = await resp2.text()

    match = re.search(r"\{.*\}", text2, re.DOTALL)
    if not match:
        raise ValueError(f"QQ /me JSONP parse failed: {text2!r}")
    me_data = json.loads(match.group())
    openid = me_data.get("openid")
    if not openid:
        raise ValueError(f"QQ /me response missing openid: {me_data}")
    return openid


async def thbwiki_exchange_code(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> str:
    """Exchange a THBWiki authorization code for the user's MediaWiki user ID.

    THBWiki uses MediaWiki OAuth2: the token response includes an id_token JWT
    whose ``sub`` claim is the user's MediaWiki user ID (string).

    The JWT is expected to be signed with HMAC-SHA256 using the client secret.
    If HS256 fails (e.g. the wiki uses RS256), this raises ValueError.

    Returns:
        The user's thbwiki_uid (the ``sub`` claim as a string).

    Raises:
        ValueError: if the exchange fails or the JWT cannot be decoded.
    """
    import jwt as pyjwt

    async with aiohttp.ClientSession() as session:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        }
        resp = await session.post(_THBWIKI_TOKEN_URL, data=data)
        token_data = await resp.json()

    if "id_token" not in token_data:
        raise ValueError(f"THBWiki token response missing id_token: {token_data}")

    id_token = token_data["id_token"]
    try:
        payload = pyjwt.decode(
            id_token,
            client_secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except pyjwt.PyJWTError as exc:
        raise ValueError(f"THBWiki id_token decode failed: {exc}") from exc

    sub = payload.get("sub")
    if not sub:
        raise ValueError(f"THBWiki id_token missing sub claim: {payload}")
    return str(sub)
