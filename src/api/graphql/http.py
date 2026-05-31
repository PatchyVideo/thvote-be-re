"""Global GraphQL error formatter.

``map_app_errors`` (resolvers/user.py) only shapes errors raised *inside* the
resolvers it wraps.  Errors that bypass it reach the client with **no**
``extensions`` block, which crashes frontend handlers that read
``extensions.error_kind``.  Those bypassing errors are:

- schema validation — ``Cannot query field 'X' on type 'Mutation'``
  (graphql-core raises this before any resolver runs);
- query parse / syntax errors;
- any resolver that forgets the ``map_app_errors`` wrapper and lets a plain
  exception escape.

``AppGraphQLRouter`` backfills a baseline ``extensions`` on every outgoing
error so the client can ALWAYS read ``error_kind`` / ``human_readable_message``.
This makes the frontend's per-handler guards defense-in-depth rather than the
only thing standing between a typo'd query and a white screen.
"""

from __future__ import annotations

import logging
from typing import Any

from strawberry.fastapi import GraphQLRouter
from strawberry.http import GraphQLHTTPResponse
from strawberry.types.execution import ExecutionResult

logger = logging.getLogger(__name__)

# Keys kept identical to resolvers/user.py::_extensions so the client sees ONE
# consistent error shape regardless of where the error originated.
_HUMAN_READABLE_DEFAULTS = {
    "BAD_REQUEST": "请求有误，请刷新后重试",
    "INTERNAL_ERROR": "服务器开小差了，请稍后重试",
}


def _baseline_extensions(error_kind: str) -> dict[str, Any]:
    return {
        "service": "graphql",
        "url": None,
        "error_kind": error_kind,
        "error_message": None,
        "human_readable_message": _HUMAN_READABLE_DEFAULTS.get(error_kind),
        "upstream_response_string": None,
    }


class AppGraphQLRouter(GraphQLRouter):
    """GraphQLRouter guaranteeing every error carries a usable ``extensions``."""

    async def process_result(
        self, request: Any, result: ExecutionResult
    ) -> GraphQLHTTPResponse:
        data = await super().process_result(request, result)
        formatted = data.get("errors")
        if not formatted:
            return data

        raw = list(result.errors or [])
        for i, err in enumerate(formatted):
            ext = err.get("extensions")
            if ext and ext.get("error_kind"):
                continue  # already shaped by map_app_errors — leave untouched

            original = getattr(raw[i], "original_error", None) if i < len(raw) else None
            if original is not None:
                # A non-GraphQLError escaped a resolver that lacked
                # map_app_errors.  Mask it like the INTERNAL_ERROR branch:
                # log the type, never leak the raw message (could be SQL/SDK).
                logger.warning(
                    "Unwrapped GraphQL resolver error surfaced: %s",
                    type(original).__name__,
                )
                err["message"] = "Internal server error"
                kind = "INTERNAL_ERROR"
            else:
                kind = "BAD_REQUEST"  # validation / parse error (safe to keep msg)

            err["extensions"] = {**_baseline_extensions(kind), **(ext or {})}
        return data
