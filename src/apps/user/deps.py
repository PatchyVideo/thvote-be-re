"""FastAPI dependencies for the user module.

Centralizes:
- ``client_ip`` resolution: trusts ``X-Forwarded-For`` only when the
  connecting peer is listed in ``settings.trusted_proxy_ips``; falls back
  to ``request.client.host`` otherwise (B-009).
- ``current_user_from_token`` for endpoints that take a session token in
  the Authorization header (only ``GET /me`` today).
"""

from __future__ import annotations

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


def get_client_ip(request: Request) -> str:
    """Return the real client IP.

    If the connecting peer is a trusted proxy (listed in
    ``settings.trusted_proxy_ips``), the first entry of ``X-Forwarded-For``
    is used as the client IP. Otherwise the peer address is used directly.
    """
    peer = request.client.host if request.client else ""
    settings = get_settings()
    trusted = settings.trusted_proxy_ips
    if trusted and peer in trusted:
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip()
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
