"""Legacy REST compatibility layer (old Rust gateway contract).

These routes preserve the *flat* HTTP contract of the old Rust gateway
(``thvote-be/gateway``) so the frontend — which is shared with the still-live
Rust deployment (vote.thwiki.cc) — keeps working unmodified against this Python
backend.  They are intentionally NOT under ``/api/v1``: the frontend nginx
proxies ``/v11-be/`` to the backend root, so e.g. ``/v11-be/user-token-status``
arrives here as ``/user-token-status`` and must be served at the root path.

REMOVAL CONDITION (CLAUDE.md §5 — 临时兼容逻辑必须写明移除条件):
Delete this whole package once BOTH hold:
  1. the Rust gateway is retired (no deployment serves the flat contract), and
  2. the frontend has migrated its REST calls to the native ``/api/v1/...``
     endpoints + their response shapes.
Tracked in docs/BACKLOG.md (B-033) and docs/migration/python-rewrite.md.
"""

from src.api.rest.legacy.router import router as legacy_router

__all__ = ["legacy_router"]
