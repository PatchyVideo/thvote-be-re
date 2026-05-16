"""Redis-backed LoginSession for SSO OAuth flows.

A LoginSession holds the SSO identifiers (thbwiki_uid, qq_openid) obtained
from an OAuth callback before the user completes their normal login.
The frontend passes the returned ``sid`` in the login request body; the
service layer reads and immediately deletes the session to prevent replay.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

_KEY_PREFIX = "sso-session:"
_TTL_SECONDS = 600


def _key(sid: str) -> str:
    return f"{_KEY_PREFIX}{sid}"


async def create_sso_session(redis, data: dict) -> str:
    """Store SSO data in Redis and return a one-time session ID.

    Args:
        redis: aioredis / fakeredis client.
        data: dict with optional keys ``thbwiki_uid`` and/or ``qq_openid``.

    Returns:
        A UUID4 string to be returned to the frontend as ``sid``.
    """
    sid = str(uuid.uuid4())
    await redis.set(_key(sid), json.dumps(data), ex=_TTL_SECONDS)
    logger.debug("SSO session created: sid=%s keys=%s", sid, list(data.keys()))
    return sid


async def consume_sso_session(redis, sid: str) -> Optional[dict]:
    """Atomically read and delete a LoginSession.

    Uses GETDEL (Redis 6.2+) for atomicity; falls back to a pipeline on
    older Redis versions.

    Returns:
        Parsed dict, or None if the session doesn't exist or has expired.
    """
    from redis.exceptions import ResponseError

    key = _key(sid)
    try:
        raw = await redis.getdel(key)
    except ResponseError:
        # Redis < 6.2: fall back to GET + DEL in a pipeline
        async with redis.pipeline(transaction=True) as pipe:
            pipe.get(key)
            pipe.delete(key)
            results = await pipe.execute()
        raw = results[0]

    if raw is None:
        return None

    try:
        return json.loads(raw)
    except Exception:
        logger.warning("Failed to parse SSO session payload for sid=%s", sid)
        return None
