"""Browser-origin guard: block lazy scripts hitting mutating endpoints (B-048).

A browser automatically attaches ``Origin`` and/or ``Referer`` to fetch/XHR
POSTs; a bare ``curl`` / ``python-requests`` script does not (unless the author
deliberately forges them). So requiring one of those headers on *mutating*
requests turns away the cheap scripts while never bothering a real browser.

Scope (only mutating operations, so read-only introspection — e.g. the
frontend's codegen — is never blocked):
- ``POST /graphql`` whose body contains a ``mutation`` operation.
- The REST submit / login / send-code endpoints.

Not a silver bullet: a determined attacker can forge the header or drive a
real headless browser. This only raises the cost and stops the lazy majority.
Gated behind ``REQUIRE_BROWSER_ORIGIN`` (default off) for safe rollout.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.common.config import get_settings

# A real ``mutation`` operation keyword — ``\b`` boundaries avoid matching the
# ``mutationType`` field inside an introspection *query* (that must pass).
_MUTATION_RE = re.compile(rb"\bmutation\b")

# REST endpoints that change state; guarded regardless of body.
_GUARDED_REST_SUFFIXES = (
    # submit votes
    "/character/", "/music/", "/cp/", "/paper/", "/dojin/",
    # registration codes
    "/send-sms-code", "/send-email-code",
    # login
    "/login-phone", "/login-email", "/login-email-password",
)

_FORBIDDEN = JSONResponse(
    {
        "errors": [
            {
                "message": "Error",
                "extensions": {
                    "service": "origin-guard",
                    "error_kind": "FORBIDDEN_ORIGIN",
                    "human_readable_message": "请通过官方页面操作",
                },
            }
        ]
    },
    status_code=403,
)


def _origin_trusted(request: Request, allowed: list[str]) -> bool:
    """True if the request carries an Origin/Referer we accept.

    Presence alone already defeats a bare script.  When an explicit allow-list
    is configured (not ``["*"]``) the host must additionally match it.
    """
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    if not origin and not referer:
        return False
    wildcard = "*" in allowed
    for value in (origin, referer):
        if not value:
            continue
        if wildcard:
            return True
        host = urlparse(value).netloc or value
        for a in allowed:
            if a == value or urlparse(a).netloc == host or a == host:
                return True
    return False


class BrowserOriginGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        settings = get_settings()
        if not settings.require_browser_origin or request.method != "POST":
            return await call_next(request)

        path = request.url.path
        guarded = False
        if path.endswith("/graphql"):
            body = await request.body()  # cached on the request for downstream
            guarded = bool(_MUTATION_RE.search(body))
        elif any(path.endswith(sfx) for sfx in _GUARDED_REST_SUFFIXES):
            guarded = True

        if guarded and not _origin_trusted(request, settings.cors_allowed_origins):
            return _FORBIDDEN
        return await call_next(request)
