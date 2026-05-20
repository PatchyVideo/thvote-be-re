"""GraphQL UserMutation — bridges the REST-tested UserService to GraphQL.

The frontend login page (LoginBox.vue) drives login entirely through
GraphQL mutations; the REST /user/* endpoints are unchanged.  This module
holds the shared helpers; the mutation resolvers are added on top of them.
"""

from __future__ import annotations

from typing import Optional

import strawberry

from src.api.graphql.errors import _client_ip_from_info, map_app_errors
from src.api.graphql.types import LoginResult, pydantic_to_graphql_login_result
from src.apps.user.dao import ActivityLogDAO, UserDAO
from src.apps.user.schemas import (
    LoginEmailPasswordRequest,
    LoginEmailRequest,
    LoginPhoneRequest,
    Meta,
    SendEmailCodeRequest,
    SendSmsCodeRequest,
    UpdateEmailRequest,
    UpdateNicknameRequest,
    UpdatePasswordRequest,
    UpdatePhoneRequest,
)
from src.apps.user.service import UserService
from src.common.database import get_db_session, get_session_maker
from src.common.exceptions import AppException
from src.common.middleware.rate_limit import rate_limit
from src.common.security import decode_session_token


def build_user_service(db) -> UserService:
    """Construct a UserService bound to *db*.

    Mirrors deps.get_user_service but omits redis: these login flows never
    carry an SSO sid, and UserService._merge_sso_session no-ops when redis
    is None.  ActivityLogDAO intentionally gets its own session
    (get_session_maker()) for best-effort audit isolation, matching
    deps.get_user_service.
    """
    return UserService(
        user_dao=UserDAO(db),
        activity_dao=ActivityLogDAO(get_session_maker()),
    )


async def _throttle_user_mutation(
    info: "strawberry.Info",
    user_token: str,
    *,
    bucket: str,
    window: int,
    limit: int,
) -> None:
    """Per-IP + per-user rate limit for authenticated account mutations.

    Mirrors the REST layer (apps/user/router._rate_limit_by_token): a loose
    pre-decode per-IP bucket so garbage tokens still cost something, then a
    tight per-user bucket.  Call inside ``map_app_errors`` so the
    RRL breach surfaces as REQUEST_TOO_FREQUENT.
    """
    ip = _client_ip_from_info(info)
    await rate_limit(f"user-mut-ip-{ip or 'unknown'}", window=60, max_requests=30)
    try:
        user_id = decode_session_token(user_token).user_id
    except AppException:
        user_id = "unknown"  # service-layer _authenticate will reject it
    await rate_limit(f"{bucket}-{user_id}", window=window, max_requests=limit)


@strawberry.type
class UserMutation:
    @strawberry.mutation
    async def request_phone_code(self, info: strawberry.Info, phone: str) -> bool:
        async with map_app_errors(service="sms-service"):
            ip = _client_ip_from_info(info)
            req = SendSmsCodeRequest(phone=phone, meta=Meta(user_ip=ip))
            async for db in get_db_session():
                await build_user_service(db).send_sms_code(req)
                return True
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.mutation
    async def request_email_code(self, info: strawberry.Info, email: str) -> bool:
        async with map_app_errors(service="mail-service"):
            ip = _client_ip_from_info(info)
            req = SendEmailCodeRequest(email=email, meta=Meta(user_ip=ip))
            async for db in get_db_session():
                await build_user_service(db).send_email_code(req)
                return True
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.mutation
    async def login_phone(
        self,
        info: strawberry.Info,
        phone: str,
        verify_code: str,
        nickname: Optional[str] = None,
    ) -> LoginResult:
        async with map_app_errors(service="user-manager"):
            ip = _client_ip_from_info(info)
            await rate_limit(f"login-{ip or 'unknown'}", window=60, max_requests=5)
            req = LoginPhoneRequest(
                phone=phone, nickname=nickname, verify_code=verify_code,
                meta=Meta(user_ip=ip),
            )
            async for db in get_db_session():
                resp = await build_user_service(db).login_with_phone_code(req)
                return pydantic_to_graphql_login_result(resp)
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.mutation
    async def login_email(
        self,
        info: strawberry.Info,
        email: str,
        verify_code: str,
        nickname: Optional[str] = None,
    ) -> LoginResult:
        async with map_app_errors(service="user-manager"):
            ip = _client_ip_from_info(info)
            await rate_limit(f"login-{ip or 'unknown'}", window=60, max_requests=5)
            req = LoginEmailRequest(
                email=email, nickname=nickname, verify_code=verify_code,
                meta=Meta(user_ip=ip),
            )
            async for db in get_db_session():
                resp = await build_user_service(db).login_with_email_code(req)
                return pydantic_to_graphql_login_result(resp)
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.mutation
    async def login_email_password(
        self, info: strawberry.Info, email: str, password: str
    ) -> LoginResult:
        async with map_app_errors(service="user-manager"):
            ip = _client_ip_from_info(info)
            await rate_limit(f"login-{ip or 'unknown'}", window=60, max_requests=5)
            req = LoginEmailPasswordRequest(
                email=email, password=password, meta=Meta(user_ip=ip),
            )
            async for db in get_db_session():
                resp = await build_user_service(db).login_with_email_password(req)
                return pydantic_to_graphql_login_result(resp)
        raise RuntimeError("unreachable")  # pragma: no cover

    # ── authenticated account mutations (UserSettings.vue) ───────────────
    # All take a session user_token, return True on success, and surface the
    # frontend-expected error_kinds.  Logic lives in UserService; this only
    # bridges GraphQL → service (same as the login mutations above).

    @strawberry.mutation
    async def update_nickname(
        self, info: strawberry.Info, user_token: str, new_nickname: str
    ) -> bool:
        async with map_app_errors(service="user-manager"):
            await _throttle_user_mutation(
                info, user_token, bucket="user-mut", window=60, limit=5
            )
            ip = _client_ip_from_info(info)
            req = UpdateNicknameRequest(
                user_token=user_token, nickname=new_nickname, meta=Meta(user_ip=ip),
            )
            async for db in get_db_session():
                await build_user_service(db).update_nickname(req)
                return True
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.mutation
    async def update_password(
        self,
        info: strawberry.Info,
        user_token: str,
        new_password: str,
        old_password: Optional[str] = None,
    ) -> bool:
        # Tighter per-user bucket (5/300s) — old_password verification is a
        # brute-force surface (B-012), matching the REST update-password limit.
        async with map_app_errors(service="user-manager"):
            await _throttle_user_mutation(
                info, user_token, bucket="update-password", window=300, limit=5
            )
            ip = _client_ip_from_info(info)
            req = UpdatePasswordRequest(
                user_token=user_token,
                old_password=old_password,
                new_password=new_password,
                meta=Meta(user_ip=ip),
            )
            async for db in get_db_session():
                await build_user_service(db).update_password(req)
                return True
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.mutation
    async def update_phone(
        self,
        info: strawberry.Info,
        user_token: str,
        phone: str,
        verify_code: str,
    ) -> bool:
        async with map_app_errors(
            service="user-manager", remap={"USER_ALREADY_EXIST": "PHONE_IN_USE"}
        ):
            await _throttle_user_mutation(
                info, user_token, bucket="user-mut", window=60, limit=5
            )
            ip = _client_ip_from_info(info)
            req = UpdatePhoneRequest(
                user_token=user_token, phone=phone, verify_code=verify_code,
                meta=Meta(user_ip=ip),
            )
            async for db in get_db_session():
                await build_user_service(db).update_phone(req)
                return True
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.mutation
    async def update_email(
        self,
        info: strawberry.Info,
        user_token: str,
        email: str,
        verify_code: str,
    ) -> bool:
        async with map_app_errors(
            service="user-manager", remap={"USER_ALREADY_EXIST": "EMAIL_IN_USE"}
        ):
            await _throttle_user_mutation(
                info, user_token, bucket="user-mut", window=60, limit=5
            )
            ip = _client_ip_from_info(info)
            req = UpdateEmailRequest(
                user_token=user_token, email=email, verify_code=verify_code,
                meta=Meta(user_ip=ip),
            )
            async for db in get_db_session():
                await build_user_service(db).update_email(req)
                return True
        raise RuntimeError("unreachable")  # pragma: no cover
