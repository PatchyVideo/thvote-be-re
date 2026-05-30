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

from src.apps.user.dao import ActivityLogDAO, UserDAO
from src.apps.user.deps import get_client_ip
from src.apps.user.service import UserService
from src.common.database import get_db_session  # noqa: F401  # used by Task 5 resolvers
from src.common.database import get_session_maker
from src.common.exceptions import AppException


def build_user_service(db) -> UserService:
    """Construct a UserService bound to *db*.

    Mirrors deps.get_user_service but omits redis: these login flows never
    carry an SSO sid, and UserService._merge_sso_session no-ops when redis
    is None.
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
