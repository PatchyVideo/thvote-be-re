"""FastAPI dependencies for the user module.

Centralizes:
- ``client_ip`` resolution: when the connecting peer is a trusted proxy
  (an IP or CIDR in ``settings.trusted_proxy_ips``), trusts the
  nginx-set ``X-Real-IP`` header; falls back to ``request.client.host``
  otherwise (B-009).
- ``current_user_from_token`` for endpoints that take a session token in
  the Authorization header (only ``GET /me`` today).
"""

from __future__ import annotations

import ipaddress

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.user.dao import ActivityLogDAO, UserDAO
from src.apps.user.service import UserService
from src.common.config import get_settings
from src.common.database import get_db_session, get_session_maker
from src.common.exceptions import AppException
from src.common.redis import get_redis
from src.common.security import decode_session_token
from src.db_model.user import User


def _peer_is_trusted_proxy(peer: str, trusted: list[str]) -> bool:
    """True if *peer* matches any trusted entry (exact IP or CIDR network)."""
    if not peer or not trusted:
        return False
    try:
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        # Non-IP peer (e.g. unix socket) — fall back to exact string match.
        return peer in trusted
    for entry in trusted:
        entry = entry.strip()
        if not entry:
            continue
        try:
            if "/" in entry:
                if peer_ip in ipaddress.ip_network(entry, strict=False):
                    return True
            elif peer_ip == ipaddress.ip_address(entry):
                return True
        except ValueError:
            if peer == entry:  # malformed entry — exact string match
                return True
    return False


def get_client_ip(request: Request) -> str:
    """Return the real client IP.

    Behind nginx the TCP peer is always the proxy, so ``request.client.host``
    alone would collapse every caller to the proxy's address.  When the peer
    is a trusted proxy we therefore read ``X-Real-IP`` — which nginx sets to
    the true peer via ``$remote_addr`` and *overwrites*, so (unlike a
    client-supplied ``X-Forwarded-For`` prefix) it cannot be spoofed.  Direct
    callers (peer not trusted) are returned as-is.
    """
    peer = request.client.host if request.client else ""
    settings = get_settings()
    if _peer_is_trusted_proxy(peer, settings.trusted_proxy_ips):
        real_ip = request.headers.get("X-Real-IP", "").strip()
        if real_ip:
            return real_ip
        # Fallback: rightmost XFF entry is the hop nginx appended (the true
        # peer); the leftmost is client-controlled and must not be trusted.
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[-1].strip()
    return peer


def get_user_dao(
    session: AsyncSession = Depends(get_db_session),
) -> UserDAO:
    return UserDAO(session)


def get_activity_log_dao() -> ActivityLogDAO:
    return ActivityLogDAO(get_session_maker())


async def get_user_service(
    user_dao: UserDAO = Depends(get_user_dao),
    activity_dao: ActivityLogDAO = Depends(get_activity_log_dao),
    redis=Depends(get_redis),
) -> UserService:
    return UserService(user_dao=user_dao, activity_dao=activity_dao, redis=redis)


async def get_current_user(
    authorization: str | None = Header(default=None),
    user_dao: UserDAO = Depends(get_user_dao),
) -> User:
    """Resolve the authenticated user from an ``Authorization: Bearer …`` header.

    Used by ``GET /me`` only; mutation endpoints carry the token in the
    request body and decode it in the service layer.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="INVALID_TOKEN")
    token = authorization[7:].strip()

    try:
        payload = decode_session_token(token)
    except AppException as exc:
        raise HTTPException(status_code=401, detail="INVALID_TOKEN") from exc

    user = await user_dao.get_by_id(payload.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")
    return user
