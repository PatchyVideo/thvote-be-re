"""BrowserOriginGuard: block mutations without Origin/Referer; queries pass (B-048).

Also proves the middleware's body read is replayed to the GraphQL router (the
classic BaseHTTPMiddleware footgun) by asserting a guarded-but-allowed mutation
actually executes.
"""

import os
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-do-not-use-in-prod")
os.environ.setdefault("VOTE_START_ISO", "2020-01-01T00:00:00+00:00")
os.environ.setdefault("VOTE_END_ISO", "2099-12-31T23:59:59+00:00")

import src.common.middleware.origin_guard as guard_mod  # noqa: E402
from src.main import create_app  # noqa: E402

MUTATION = '{"query": "mutation { __typename }"}'
QUERY = '{"query": "{ __typename }"}'


def _settings(enabled: bool, allowed=None):
    return SimpleNamespace(
        require_browser_origin=enabled,
        cors_allowed_origins=allowed or ["*"],
    )


@pytest_asyncio.fixture
async def client():
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def _post(client, body, headers=None):
    return await client.post(
        "/graphql",
        content=body,
        headers={"content-type": "application/json", **(headers or {})},
    )


@pytest.mark.asyncio
async def test_mutation_without_origin_blocked(client, monkeypatch):
    monkeypatch.setattr(guard_mod, "get_settings", lambda: _settings(True))
    resp = await _post(client, MUTATION)
    assert resp.status_code == 403
    assert resp.json()["errors"][0]["extensions"]["error_kind"] == "FORBIDDEN_ORIGIN"


@pytest.mark.asyncio
async def test_mutation_with_origin_passes_and_executes(client, monkeypatch):
    """Guarded but allowed → the body must reach the resolver (replay works)."""
    monkeypatch.setattr(guard_mod, "get_settings", lambda: _settings(True))
    resp = await _post(client, MUTATION, {"origin": "https://vote.thwiki.cc"})
    assert resp.status_code == 200
    assert resp.json()["data"]["__typename"] == "Mutation"  # executed, body intact


@pytest.mark.asyncio
async def test_mutation_with_referer_passes(client, monkeypatch):
    monkeypatch.setattr(guard_mod, "get_settings", lambda: _settings(True))
    resp = await _post(client, MUTATION, {"referer": "https://vote.thwiki.cc/v11/"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_query_without_origin_passes(client, monkeypatch):
    """Read-only introspection (codegen) must never be blocked."""
    monkeypatch.setattr(guard_mod, "get_settings", lambda: _settings(True))
    resp = await _post(client, QUERY)
    assert resp.status_code == 200
    assert resp.json()["data"]["__typename"] == "Query"


@pytest.mark.asyncio
async def test_disabled_lets_scripted_mutation_through(client, monkeypatch):
    monkeypatch.setattr(guard_mod, "get_settings", lambda: _settings(False))
    resp = await _post(client, MUTATION)  # no origin, but guard off
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_allowlist_rejects_foreign_origin(client, monkeypatch):
    monkeypatch.setattr(
        guard_mod, "get_settings",
        lambda: _settings(True, ["https://vote.thwiki.cc"]),
    )
    resp = await _post(client, MUTATION, {"origin": "https://evil.example"})
    assert resp.status_code == 403
    ok = await _post(client, MUTATION, {"origin": "https://vote.thwiki.cc"})
    assert ok.status_code == 200
