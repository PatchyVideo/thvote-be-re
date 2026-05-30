"""GraphQL UserMutation — bridges the REST-tested UserService to GraphQL.

The frontend login page (LoginBox.vue) drives login entirely through
GraphQL mutations; the REST /user/* endpoints are unchanged.  This module
holds the shared helpers; the mutation resolvers are added on top of them.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import strawberry
from fastapi import HTTPException
from graphql import GraphQLError

from src.api.graphql.types import LoginResult, pydantic_to_graphql_login_result
from src.apps.user.dao import ActivityLogDAO, UserDAO
from src.apps.user.deps import get_client_ip
from src.apps.user.schemas import (
    LoginEmailPasswordRequest,
    LoginEmailRequest,
    LoginPhoneRequest,
    Meta,
    SendEmailCodeRequest,
    SendSmsCodeRequest,
)
from src.apps.user.service import UserService
from src.common.database import get_db_session, get_session_maker
from src.common.exceptions import AppException
from src.common.middleware.rate_limit import rate_limit


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


def _client_ip_from_info(info: "strawberry.Info") -> str:
    """Extract the real client IP from the Strawberry request context."""
    ctx = info.context
    request = ctx["request"] if isinstance(ctx, dict) else getattr(ctx, "request", None)
    if request is None:
        return ""
    return get_client_ip(request)


def _extensions(
    service: str,
    error_kind: str,
    *,
    error_message: Optional[str] = None,
    upstream: Optional[str] = None,
) -> dict[str, object]:
    return {
        "service": service,
        "url": None,
        "error_kind": error_kind,
        "error_message": error_message,
        "human_readable_message": None,
        "upstream_response_string": upstream,
    }


@asynccontextmanager
async def map_app_errors(service: str) -> AsyncIterator[None]:
    """Translate service-layer errors into a Rust-aligned GraphQLError."""
    try:
        yield
    except AppException as exc:
        raise GraphQLError(
            "Error",
            extensions=_extensions(
                service,
                exc.message,
                error_message=getattr(exc, "error_message", None),
                upstream=getattr(exc, "upstream_response_string", None),
            ),
        ) from exc
    except HTTPException as exc:
        raise GraphQLError(
            "Error", extensions=_extensions(service, str(exc.detail))
        ) from exc
    except GraphQLError:
        raise  # already-mapped error — pass through unchanged
    except Exception as exc:
        raise GraphQLError(
            "Error", extensions=_extensions(service, "INTERNAL_ERROR")
        ) from exc


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
