"""Shared pytest config / fixtures.

The test suite is organized by layer:
- ``tests/unit``        — pure logic, all external deps mocked
- ``tests/integration`` — real Postgres + Redis (CI provides them);
                          Aliyun is always mocked
- ``tests/contract``    — wire-format (JSON shape) checks against the FastAPI
                          app via httpx.AsyncClient
"""

from __future__ import annotations

import os

# Ensure required env vars exist for Settings() before importing app modules.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./.test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-do-not-use-in-prod")
os.environ.setdefault("VOTE_START_ISO", "2020-01-01T00:00:00+00:00")
os.environ.setdefault("VOTE_END_ISO", "2099-12-31T23:59:59+00:00")
