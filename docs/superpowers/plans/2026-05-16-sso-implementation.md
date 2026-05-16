# SSO Implementation Plan (B-007: THBWiki + QQ)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add QQ OAuth2 and THBWiki OAuth2 single sign-on to the user module, including DB migration, 6 new endpoints, LoginSession Redis helper, and modifications to all 3 existing login flows to accept an optional `sid` that merges SSO identifiers into the authenticated user.

**Architecture:** New SSO state flows via Redis `LoginSession` (TTL 600s). OAuth callbacks create the session and return `{"sid": "..."}` to the frontend. Existing login endpoints accept an optional `sid` in the request body; on login/signup success, the SSO IDs from the session are merged into the user row if the columns are currently NULL. Two new SSO credential pairs are added to `Settings` (loaded via Nacos, like all other credentials).

**Tech Stack:** Python 3.12, FastAPI, aiohttp (for OAuth HTTP calls), SQLAlchemy async, Alembic, Redis, PyJWT, pytest

---

## File Map

| File | Action |
|---|---|
| `alembic/versions/0004_sso_columns.py` | Create (migration) |
| `src/db_model/user.py` | Modify (add thbwiki_uid, qq_openid) |
| `src/common/config.py` | Modify (add 5 SSO config fields) |
| `src/apps/user/sso_session.py` | Create (Redis LoginSession helper) |
| `src/apps/user/sso_clients.py` | Create (QQ + THBWiki OAuth HTTP helpers) |
| `src/apps/user/router.py` | Modify (add 6 SSO endpoints) |
| `src/apps/user/service.py` | Modify (add merge_sso_session, update login methods) |
| `src/apps/user/dao.py` | Modify (UserDAO.save already exists — verify) |
| `src/apps/user/schemas.py` | Modify (add sid to login requests, update VoterFE) |
| `tests/unit/test_sso_session.py` | Create |
| `tests/integration/test_sso_flows.py` | Create |
| `tests/contract/test_sso_endpoints.py` | Create |

---

## Task 1: DB Migration 0004 — add SSO columns

**Files:**
- Create: `alembic/versions/0004_sso_columns.py`
- Modify: `src/db_model/user.py`

- [ ] **Step 1: Write the failing integration test**

Create `tests/integration/test_sso_flows.py` (partial — just the schema test for now):

```python
import pytest
from sqlalchemy import inspect, text


@pytest.mark.asyncio
async def test_user_table_has_sso_columns(db_session):
    """Migration 0004 must add thbwiki_uid and qq_openid to user table."""
    async with db_session() as session:
        result = await session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'user' AND column_name IN ('thbwiki_uid', 'qq_openid')"
            )
        )
        cols = {row[0] for row in result.fetchall()}
    assert "thbwiki_uid" in cols, "thbwiki_uid column missing"
    assert "qq_openid" in cols, "qq_openid column missing"
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/integration/test_sso_flows.py::test_user_table_has_sso_columns -xvs
```

Expected: FAIL (columns don't exist)

- [ ] **Step 3: Create the Alembic migration**

Create `alembic/versions/0004_sso_columns.py`:

```python
"""add thbwiki_uid and qq_openid SSO columns to user table

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-16
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user", sa.Column("thbwiki_uid", sa.String(128), nullable=True))
    op.add_column("user", sa.Column("qq_openid", sa.String(128), nullable=True))
    op.create_index(
        "uq_user_thbwiki_uid",
        "user",
        ["thbwiki_uid"],
        unique=True,
        postgresql_where=sa.text("thbwiki_uid IS NOT NULL"),
        sqlite_where=sa.text("thbwiki_uid IS NOT NULL"),
    )
    op.create_index(
        "uq_user_qq_openid",
        "user",
        ["qq_openid"],
        unique=True,
        postgresql_where=sa.text("qq_openid IS NOT NULL"),
        sqlite_where=sa.text("qq_openid IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_user_qq_openid", table_name="user")
    op.drop_index("uq_user_thbwiki_uid", table_name="user")
    op.drop_column("user", "qq_openid")
    op.drop_column("user", "thbwiki_uid")
```

- [ ] **Step 4: Update the User ORM model**

In `src/db_model/user.py`, add after the `pfp` column:

```python
    thbwiki_uid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    qq_openid: Mapped[str | None] = mapped_column(String(128), nullable=True)
```

- [ ] **Step 5: Apply migration to test DB and run test**

```bash
alembic upgrade head
pytest tests/integration/test_sso_flows.py::test_user_table_has_sso_columns -xvs
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add alembic/versions/0004_sso_columns.py src/db_model/user.py tests/integration/test_sso_flows.py
git commit -m "feat(db): migration 0004 — add thbwiki_uid and qq_openid SSO columns (B-007)"
```

---

## Task 2: SSO config fields in Settings

**Files:**
- Modify: `src/common/config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_sso_config.py`:

```python
def test_sso_config_fields_exist():
    """Settings must expose the 5 SSO config fields."""
    from src.common.config import Settings
    s = Settings(
        QQ_APP_ID="test_id",
        QQ_APP_SECRET="test_secret",
        THBWIKI_CLIENT_ID="wiki_id",
        THBWIKI_CLIENT_SECRET="wiki_secret",
        SSO_CALLBACK_BASE_URL="https://example.com",
    )
    assert s.qq_app_id == "test_id"
    assert s.qq_app_secret == "test_secret"
    assert s.thbwiki_client_id == "wiki_id"
    assert s.thbwiki_client_secret == "wiki_secret"
    assert s.sso_callback_base_url == "https://example.com"


def test_sso_config_defaults_to_none():
    """SSO config fields must default to None when not set."""
    from src.common.config import Settings
    s = Settings()
    assert s.qq_app_id is None
    assert s.thbwiki_client_id is None
    assert s.sso_callback_base_url is None
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/unit/test_sso_config.py -xvs
```

Expected: FAIL with `ValidationError` or `AttributeError`

- [ ] **Step 3: Add SSO fields to Settings**

In `src/common/config.py`, inside the `Settings` class, add after the `cors_allowed_origins` / `trusted_proxy_ips` block:

```python
    # SSO 配置（通过 Nacos 下发，与 ALIYUN_* 字段同等对待）
    qq_app_id: Optional[str] = Field(None, validation_alias="QQ_APP_ID")
    qq_app_secret: Optional[str] = Field(None, validation_alias="QQ_APP_SECRET")
    thbwiki_client_id: Optional[str] = Field(None, validation_alias="THBWIKI_CLIENT_ID")
    thbwiki_client_secret: Optional[str] = Field(
        None, validation_alias="THBWIKI_CLIENT_SECRET"
    )
    sso_callback_base_url: Optional[str] = Field(
        None, validation_alias="SSO_CALLBACK_BASE_URL"
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_sso_config.py -xvs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/common/config.py tests/unit/test_sso_config.py
git commit -m "feat(config): add SSO config fields for QQ and THBWiki OAuth (B-007)"
```

---

## Task 3: Redis LoginSession helper

**Files:**
- Create: `src/apps/user/sso_session.py`
- Create: `tests/unit/test_sso_session.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_sso_session.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_create_sso_session_returns_sid():
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    from src.apps.user.sso_session import create_sso_session
    sid = await create_sso_session(redis, {"qq_openid": "12345"})

    assert len(sid) == 36  # UUID4 format
    redis.set.assert_called_once()
    call_args = redis.set.call_args
    assert call_args[1]["ex"] == 600


@pytest.mark.asyncio
async def test_consume_sso_session_returns_data_and_deletes():
    import json
    data = {"thbwiki_uid": "999", "qq_openid": None}

    redis = AsyncMock()
    redis.getdel = AsyncMock(return_value=json.dumps(data).encode())

    from src.apps.user.sso_session import consume_sso_session
    result = await consume_sso_session(redis, "some-sid")

    assert result == data
    redis.getdel.assert_called_once_with("sso-session:some-sid")


@pytest.mark.asyncio
async def test_consume_sso_session_returns_none_for_missing():
    redis = AsyncMock()
    redis.getdel = AsyncMock(return_value=None)

    from src.apps.user.sso_session import consume_sso_session
    result = await consume_sso_session(redis, "nonexistent")

    assert result is None


@pytest.mark.asyncio
async def test_consume_sso_session_falls_back_when_getdel_unavailable():
    """Redis < 6.2 doesn't have GETDEL; fall back to GET+DEL via pipeline."""
    import json
    data = {"thbwiki_uid": "777"}
    redis = AsyncMock()
    # Simulate GETDEL not available (raises ResponseError)
    from redis.exceptions import ResponseError
    redis.getdel = AsyncMock(side_effect=ResponseError("unknown command"))

    pipe = AsyncMock()
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__ = AsyncMock(return_value=False)
    pipe.get = MagicMock()
    pipe.delete = MagicMock()
    pipe.execute = AsyncMock(return_value=[json.dumps(data).encode(), 1])
    redis.pipeline = MagicMock(return_value=pipe)

    from src.apps.user.sso_session import consume_sso_session
    result = await consume_sso_session(redis, "some-sid")

    assert result == data
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/unit/test_sso_session.py -xvs
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create src/apps/user/sso_session.py**

```python
"""Redis-backed LoginSession for SSO OAuth flows.

A LoginSession holds the SSO identifiers (thbwiki_uid, qq_openid) obtained
from an OAuth callback before the user completes their normal login.
The frontend passes the returned ``sid`` in the login request body; the
service layer reads and immediately deletes the session to prevent replay.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

_KEY_PREFIX = "sso-session:"
_TTL_SECONDS = 600


def _key(sid: str) -> str:
    return f"{_KEY_PREFIX}{sid}"


async def create_sso_session(redis, data: dict) -> str:
    """Store SSO data in Redis and return a one-time session ID.

    Args:
        redis: aioredis / fakeredis client.
        data: dict with optional keys ``thbwiki_uid`` and/or ``qq_openid``.

    Returns:
        A UUID4 string to be returned to the frontend as ``sid``.
    """
    sid = str(uuid.uuid4())
    await redis.set(_key(sid), json.dumps(data), ex=_TTL_SECONDS)
    logger.debug("SSO session created: sid=%s keys=%s", sid, list(data.keys()))
    return sid


async def consume_sso_session(redis, sid: str) -> Optional[dict]:
    """Atomically read and delete a LoginSession.

    Uses GETDEL (Redis 6.2+) for atomicity; falls back to a pipeline on
    older Redis versions.

    Returns:
        Parsed dict, or None if the session doesn't exist or has expired.
    """
    from redis.exceptions import ResponseError

    key = _key(sid)
    try:
        raw = await redis.getdel(key)
    except ResponseError:
        # Redis < 6.2: fall back to GET + DEL in a pipeline
        async with redis.pipeline(transaction=True) as pipe:
            pipe.get(key)
            pipe.delete(key)
            results = await pipe.execute()
        raw = results[0]

    if raw is None:
        return None

    try:
        return json.loads(raw)
    except Exception:
        logger.warning("Failed to parse SSO session payload for sid=%s", sid)
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_sso_session.py -xvs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/apps/user/sso_session.py tests/unit/test_sso_session.py
git commit -m "feat(sso): add Redis LoginSession helper with atomic GETDEL (B-007)"
```

---

## Task 4: QQ + THBWiki OAuth HTTP helpers

**Files:**
- Create: `src/apps/user/sso_clients.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_sso_clients.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_qq_exchange_code_returns_openid():
    mock_response_token = MagicMock()
    mock_response_token.text = AsyncMock(
        return_value="access_token=mock_token&expires_in=7776000&refresh_token=mock_refresh"
    )
    mock_response_me = MagicMock()
    mock_response_me.text = AsyncMock(
        return_value='callback( {"client_id":"12345","openid":"ABCDEF"} );\n'
    )

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(side_effect=[mock_response_token, mock_response_me])
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        from src.apps.user.sso_clients import qq_exchange_code
        openid = await qq_exchange_code(
            code="test_code",
            app_id="12345",
            app_secret="secret",
            redirect_uri="https://example.com/callback",
        )

    assert openid == "ABCDEF"


@pytest.mark.asyncio
async def test_thbwiki_exchange_code_returns_uid():
    import jwt as pyjwt

    uid = "42"
    secret = "test_secret"
    token = pyjwt.encode(
        {"sub": uid, "username": "TestUser"},
        secret,
        algorithm="HS256",
    )

    mock_response = MagicMock()
    mock_response.json = AsyncMock(
        return_value={"access_token": "tok", "id_token": token}
    )
    mock_session = AsyncMock()
    mock_session.post = AsyncMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        from src.apps.user.sso_clients import thbwiki_exchange_code
        result_uid = await thbwiki_exchange_code(
            code="test_code",
            client_id="wiki_id",
            client_secret=secret,
            redirect_uri="https://example.com/callback",
        )

    assert result_uid == uid
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/unit/test_sso_clients.py -xvs
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create src/apps/user/sso_clients.py**

```python
"""OAuth HTTP helpers for QQ Connect and THBWiki (MediaWiki OAuth2).

Each function handles the token-exchange leg of the Authorization Code flow
and returns only the user identifier needed to link/create an account.
All network I/O is done with aiohttp to stay non-blocking.
"""
from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# QQ Connect endpoints
_QQ_TOKEN_URL = "https://graph.qq.com/oauth2.0/token"
_QQ_ME_URL = "https://graph.qq.com/oauth2.0/me"

# THBWiki MediaWiki OAuth2 endpoints
_THBWIKI_TOKEN_URL = "https://thwiki.cc/wiki/Special:OAuth/access_token"
_THBWIKI_AUTHORIZE_URL = "https://thwiki.cc/wiki/Special:OAuth/authorize"

# QQ Connect authorize URL
_QQ_AUTHORIZE_URL = "https://graph.qq.com/oauth2.0/authorize"


def qq_authorize_url(app_id: str, redirect_uri: str, state: str) -> str:
    """Build the QQ Connect authorization redirect URL."""
    params = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": app_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": "get_user_info",
        }
    )
    return f"{_QQ_AUTHORIZE_URL}?{params}"


def thbwiki_authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    """Build the THBWiki OAuth2 authorization redirect URL."""
    params = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": "basic",
        }
    )
    return f"{_THBWIKI_AUTHORIZE_URL}?{params}"


async def qq_exchange_code(
    code: str,
    app_id: str,
    app_secret: str,
    redirect_uri: str,
) -> str:
    """Exchange a QQ Connect authorization code for the user's openid.

    QQ OAuth2 uses a non-standard two-step process:
      1. Exchange code → access_token (query-string response, not JSON)
      2. Fetch /me with access_token → JSONP response containing openid

    Returns:
        The user's QQ openid string.

    Raises:
        ValueError: if the exchange or openid fetch fails.
    """
    async with aiohttp.ClientSession() as session:
        # Step 1: exchange code for access_token
        params = {
            "grant_type": "authorization_code",
            "client_id": app_id,
            "client_secret": app_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "fmt": "json",
        }
        resp = await session.get(_QQ_TOKEN_URL, params=params)
        text = await resp.text()

        # QQ may return JSON or query-string; handle both
        access_token: Optional[str] = None
        try:
            import json
            data = json.loads(text)
            if "access_token" not in data:
                raise ValueError(f"QQ token exchange error: {data}")
            access_token = data["access_token"]
        except (json.JSONDecodeError, TypeError):
            qs = urllib.parse.parse_qs(text)
            if "access_token" not in qs:
                raise ValueError(f"QQ token exchange failed: {text!r}")
            access_token = qs["access_token"][0]

        # Step 2: fetch openid via /me (JSONP format)
        resp2 = await session.get(_QQ_ME_URL, params={"access_token": access_token})
        text2 = await resp2.text()

    # Parse JSONP: callback( {"client_id":"...","openid":"..."} );
    match = re.search(r'\{.*\}', text2, re.DOTALL)
    if not match:
        raise ValueError(f"QQ /me JSONP parse failed: {text2!r}")
    import json
    me_data = json.loads(match.group())
    openid = me_data.get("openid")
    if not openid:
        raise ValueError(f"QQ /me response missing openid: {me_data}")
    return openid


async def thbwiki_exchange_code(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> str:
    """Exchange a THBWiki authorization code for the user's MediaWiki user ID.

    THBWiki uses MediaWiki OAuth2: the token response includes an id_token JWT
    whose ``sub`` claim is the user's MediaWiki user ID (string).

    The JWT is signed with HMAC-SHA256 using the client secret.
    If HS256 fails (e.g. the wiki uses RS256), this raises ValueError — update
    the implementation to fetch the JWKS endpoint in that case.

    Returns:
        The user's thbwiki_uid (the ``sub`` claim as a string).

    Raises:
        ValueError: if the exchange fails or the JWT cannot be decoded.
    """
    import jwt as pyjwt

    async with aiohttp.ClientSession() as session:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        }
        resp = await session.post(_THBWIKI_TOKEN_URL, data=data)
        token_data = await resp.json()

    if "id_token" not in token_data:
        raise ValueError(f"THBWiki token response missing id_token: {token_data}")

    id_token = token_data["id_token"]
    try:
        payload = pyjwt.decode(
            id_token,
            client_secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except pyjwt.PyJWTError as exc:
        raise ValueError(f"THBWiki id_token decode failed: {exc}") from exc

    sub = payload.get("sub")
    if not sub:
        raise ValueError(f"THBWiki id_token missing sub claim: {payload}")
    return str(sub)
```

- [ ] **Step 4: Add aiohttp and PyJWT to dependencies**

In `pyproject.toml`, add to the `dependencies` list (find the `[project]` section):
```toml
"aiohttp>=3.9",
"PyJWT>=2.8",
```

Install: `pip install -e .`

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/unit/test_sso_clients.py -xvs
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/apps/user/sso_clients.py tests/unit/test_sso_clients.py pyproject.toml
git commit -m "feat(sso): add QQ and THBWiki OAuth HTTP exchange helpers (B-007)"
```

---

## Task 5: SSO endpoints (authorize + callback + bind)

**Files:**
- Modify: `src/apps/user/router.py`

- [ ] **Step 1: Write the failing contract tests**

Create `tests/contract/test_sso_endpoints.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_qq_authorize_redirects(async_client, monkeypatch):
    """GET /user/sso/qq/authorize must 302 to QQ when configured."""
    import src.common.config as cfg
    original = cfg.get_settings

    def patched_settings():
        s = original()
        object.__setattr__(s, "qq_app_id", "test_app_id")
        object.__setattr__(s, "sso_callback_base_url", "https://example.com")
        return s

    monkeypatch.setattr(cfg, "get_settings", patched_settings)
    resp = await async_client.get("/api/v1/user/sso/qq/authorize", follow_redirects=False)
    assert resp.status_code == 302
    assert "graph.qq.com" in resp.headers["location"]


@pytest.mark.asyncio
async def test_qq_authorize_503_when_not_configured(async_client):
    """GET /user/sso/qq/authorize must return 503 when QQ_APP_ID is unset."""
    resp = await async_client.get("/api/v1/user/sso/qq/authorize", follow_redirects=False)
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_thbwiki_authorize_503_when_not_configured(async_client):
    resp = await async_client.get(
        "/api/v1/user/sso/thbwiki/authorize", follow_redirects=False
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_qq_bind_requires_session_token(async_client):
    """POST /user/sso/qq/bind must return 401 without a session token."""
    resp = await async_client.post(
        "/api/v1/user/sso/qq/bind",
        json={"code": "test_code", "user_token": ""},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_thbwiki_bind_requires_session_token(async_client):
    resp = await async_client.post(
        "/api/v1/user/sso/thbwiki/bind",
        json={"code": "test_code", "user_token": ""},
    )
    assert resp.status_code == 401
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/contract/test_sso_endpoints.py -xvs
```

Expected: FAIL (404 — routes don't exist yet)

- [ ] **Step 3: Add SSO schemas to src/apps/user/schemas.py**

Add at the end of the schemas file:

```python
# ── SSO schemas ──────────────────────────────────────────────────────


class SsoCallbackResponse(BaseModel):
    """Returned by OAuth callback endpoints; frontend passes sid to login."""
    sid: str


class SsoBindRequest(BaseModel):
    """Bind an SSO account to an already-logged-in user."""
    code: str
    user_token: str
    meta: Meta = Field(default_factory=Meta)
```

- [ ] **Step 4: Add SSO endpoints to src/apps/user/router.py**

At the top of `router.py`, ensure these imports are present (add if missing):

```python
import secrets
from fastapi.responses import RedirectResponse
```

Add the following 6 endpoints to the router (place before or after existing endpoints, keeping file organized):

```python
# ── SSO: QQ Connect ──────────────────────────────────────────────────


@router.get("/sso/qq/authorize", tags=["sso"])
async def qq_authorize() -> RedirectResponse:
    settings = get_settings()
    if not settings.qq_app_id or not settings.sso_callback_base_url:
        raise HTTPException(
            status_code=503,
            detail={"code": "SSO_NOT_CONFIGURED", "message": "QQ SSO is not configured"},
        )
    from .sso_clients import qq_authorize_url
    redirect_uri = f"{settings.sso_callback_base_url}/api/v1/user/sso/qq/callback"
    state = secrets.token_urlsafe(16)
    url = qq_authorize_url(settings.qq_app_id, redirect_uri, state)
    return RedirectResponse(url=url, status_code=302)


@router.get("/sso/qq/callback", tags=["sso"])
async def qq_callback(
    code: str,
    state: str = "",
    redis=Depends(get_redis),
) -> SsoCallbackResponse:
    settings = get_settings()
    if not settings.qq_app_id or not settings.qq_app_secret or not settings.sso_callback_base_url:
        raise HTTPException(status_code=503, detail={"code": "SSO_NOT_CONFIGURED"})
    from .sso_clients import qq_exchange_code
    from .sso_session import create_sso_session
    redirect_uri = f"{settings.sso_callback_base_url}/api/v1/user/sso/qq/callback"
    try:
        openid = await qq_exchange_code(code, settings.qq_app_id, settings.qq_app_secret, redirect_uri)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_SSO_CODE", "message": str(exc)})
    sid = await create_sso_session(redis, {"qq_openid": openid})
    return SsoCallbackResponse(sid=sid)


@router.post("/sso/qq/bind", tags=["sso"])
async def qq_bind(
    req: SsoBindRequest,
    db: AsyncSession = Depends(get_db_session),
    redis=Depends(get_redis),
) -> VoterFE:
    return await _sso_bind(req, "qq", db, redis)


# ── SSO: THBWiki ─────────────────────────────────────────────────────


@router.get("/sso/thbwiki/authorize", tags=["sso"])
async def thbwiki_authorize() -> RedirectResponse:
    settings = get_settings()
    if not settings.thbwiki_client_id or not settings.sso_callback_base_url:
        raise HTTPException(
            status_code=503,
            detail={"code": "SSO_NOT_CONFIGURED", "message": "THBWiki SSO is not configured"},
        )
    from .sso_clients import thbwiki_authorize_url
    redirect_uri = f"{settings.sso_callback_base_url}/api/v1/user/sso/thbwiki/callback"
    state = secrets.token_urlsafe(16)
    url = thbwiki_authorize_url(settings.thbwiki_client_id, redirect_uri, state)
    return RedirectResponse(url=url, status_code=302)


@router.get("/sso/thbwiki/callback", tags=["sso"])
async def thbwiki_callback(
    code: str,
    state: str = "",
    redis=Depends(get_redis),
) -> SsoCallbackResponse:
    settings = get_settings()
    if not settings.thbwiki_client_id or not settings.thbwiki_client_secret or not settings.sso_callback_base_url:
        raise HTTPException(status_code=503, detail={"code": "SSO_NOT_CONFIGURED"})
    from .sso_clients import thbwiki_exchange_code
    from .sso_session import create_sso_session
    redirect_uri = f"{settings.sso_callback_base_url}/api/v1/user/sso/thbwiki/callback"
    try:
        uid = await thbwiki_exchange_code(
            code, settings.thbwiki_client_id, settings.thbwiki_client_secret, redirect_uri
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_SSO_CODE", "message": str(exc)})
    sid = await create_sso_session(redis, {"thbwiki_uid": uid})
    return SsoCallbackResponse(sid=sid)


@router.post("/sso/thbwiki/bind", tags=["sso"])
async def thbwiki_bind(
    req: SsoBindRequest,
    db: AsyncSession = Depends(get_db_session),
    redis=Depends(get_redis),
) -> VoterFE:
    return await _sso_bind(req, "thbwiki", db, redis)
```

Add a shared helper at the bottom of the router (before or after the endpoints is fine):

```python
async def _sso_bind(
    req: SsoBindRequest,
    provider: str,
    db: AsyncSession,
    redis,
) -> VoterFE:
    """Shared logic for /sso/{provider}/bind endpoints."""
    settings = get_settings()

    if provider == "qq":
        if not settings.qq_app_id or not settings.qq_app_secret or not settings.sso_callback_base_url:
            raise HTTPException(status_code=503, detail={"code": "SSO_NOT_CONFIGURED"})
        from .sso_clients import qq_exchange_code
        redirect_uri = f"{settings.sso_callback_base_url}/api/v1/user/sso/qq/callback"
        try:
            openid = await qq_exchange_code(
                req.code, settings.qq_app_id, settings.qq_app_secret, redirect_uri
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"code": "INVALID_SSO_CODE", "message": str(exc)})
        sso_data = {"qq_openid": openid}
    else:  # thbwiki
        if not settings.thbwiki_client_id or not settings.thbwiki_client_secret or not settings.sso_callback_base_url:
            raise HTTPException(status_code=503, detail={"code": "SSO_NOT_CONFIGURED"})
        from .sso_clients import thbwiki_exchange_code
        redirect_uri = f"{settings.sso_callback_base_url}/api/v1/user/sso/thbwiki/callback"
        try:
            uid = await thbwiki_exchange_code(
                req.code, settings.thbwiki_client_id, settings.thbwiki_client_secret, redirect_uri
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"code": "INVALID_SSO_CODE", "message": str(exc)})
        sso_data = {"thbwiki_uid": uid}

    svc = _make_service(db, redis)
    try:
        voter_fe = await svc.bind_sso(req.user_token, sso_data)
    except AppException as exc:
        _raise_http(exc)
    return voter_fe
```

Also add the necessary imports to router.py that may be missing:
```python
from .schemas import SsoCallbackResponse, SsoBindRequest
from .sso_session import create_sso_session
```

Check the existing router.py for how `get_redis`, `_make_service`, `_raise_http`, `AppException` are used — use the same pattern as existing endpoints.

- [ ] **Step 5: Run contract tests to verify they pass**

```bash
pytest tests/contract/test_sso_endpoints.py -xvs
```

Expected: PASS for the 503/401 tests; the redirect test requires monkeypatching settings.

- [ ] **Step 6: Commit**

```bash
git add src/apps/user/router.py src/apps/user/schemas.py tests/contract/test_sso_endpoints.py
git commit -m "feat(sso): add 6 SSO endpoints for QQ and THBWiki authorize/callback/bind (B-007)"
```

---

## Task 6: UserService — bind_sso + merge_sso_session

**Files:**
- Modify: `src/apps/user/service.py`
- Modify: `src/apps/user/schemas.py` (add `sid` to login requests)

- [ ] **Step 1: Write the failing integration test**

Add to `tests/integration/test_sso_flows.py`:

```python
@pytest.mark.asyncio
async def test_login_email_merges_sso_session(db_session, fake_redis):
    """When a valid sid is present in the login request, SSO IDs are merged into the user row."""
    from src.apps.user.sso_session import create_sso_session
    from src.apps.user.service import UserService
    from src.apps.user.dao import UserDAO, ActivityLogDAO
    from src.apps.user.utils.security import AuthProvider
    from src.common.verification import get_email_code_service
    from src.common.config import get_settings

    settings = get_settings()
    sid = await create_sso_session(fake_redis, {"thbwiki_uid": "wiki-42"})

    async with db_session() as session:
        svc = UserService(
            user_dao=UserDAO(session),
            activity_dao=ActivityLogDAO(session),
            email_code_service=get_email_code_service(),
            sms_code_service=None,
            auth=AuthProvider(settings),
            redis=fake_redis,
            settings=settings,
        )

        # Pre-create a user with a verified email
        from tests.integration.test_login_flows import _seed_email_user, _set_email_code
        user = await _seed_email_user(session, email="sso@example.com")
        await _set_email_code(fake_redis, "sso@example.com", "123456")

        from src.apps.user.schemas import LoginEmailRequest, Meta
        req = LoginEmailRequest(
            email="sso@example.com",
            verify_code="123456",
            meta=Meta(user_ip="1.2.3.4"),
            sid=sid,
        )
        resp = await svc.login_email(req)

    assert resp.user.thbwiki is True


@pytest.mark.asyncio
async def test_bind_sso_sets_column(db_session, fake_redis):
    """bind_sso must write the SSO ID into the user row when the column is NULL."""
    from src.apps.user.service import UserService
    from src.apps.user.dao import UserDAO, ActivityLogDAO
    from src.apps.user.utils.security import AuthProvider
    from src.common.config import get_settings

    settings = get_settings()

    async with db_session() as session:
        from tests.integration.test_login_flows import _seed_email_user
        user = await _seed_email_user(session, email="bind@example.com")

        auth = AuthProvider(settings)
        session_token = auth.create_session_token(user.id)

        svc = UserService(
            user_dao=UserDAO(session),
            activity_dao=ActivityLogDAO(session),
            email_code_service=None,
            sms_code_service=None,
            auth=auth,
            redis=fake_redis,
            settings=settings,
        )
        voter_fe = await svc.bind_sso(session_token, {"qq_openid": "open-999"})

    assert voter_fe.thbwiki is False  # didn't set thbwiki
    # Verify the DB row
    async with db_session() as session:
        from sqlalchemy import select
        from src.db_model.user import User
        u = await session.scalar(select(User).where(User.email == "bind@example.com"))
        assert u.qq_openid == "open-999"


@pytest.mark.asyncio
async def test_bind_sso_409_when_openid_taken(db_session, fake_redis):
    """bind_sso must raise 409 if the openid is already bound to another account."""
    from src.apps.user.service import UserService
    from src.apps.user.dao import UserDAO, ActivityLogDAO
    from src.apps.user.utils.security import AuthProvider
    from src.common.config import get_settings
    from src.common.exceptions import AppException

    settings = get_settings()

    async with db_session() as session:
        from tests.integration.test_login_flows import _seed_email_user
        user1 = await _seed_email_user(session, email="owner@example.com")
        user2 = await _seed_email_user(session, email="thief@example.com")

        # Give user1 the openid
        user1.qq_openid = "taken-openid"
        await session.commit()

        auth = AuthProvider(settings)
        token2 = auth.create_session_token(user2.id)

        svc = UserService(
            user_dao=UserDAO(session),
            activity_dao=ActivityLogDAO(session),
            email_code_service=None,
            sms_code_service=None,
            auth=auth,
            redis=fake_redis,
            settings=settings,
        )

        with pytest.raises(AppException) as exc_info:
            await svc.bind_sso(token2, {"qq_openid": "taken-openid"})
        assert "SSO_ID_ALREADY_BOUND" in str(exc_info.value)
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/integration/test_sso_flows.py -xvs -k "merge_sso or bind_sso"
```

Expected: FAIL (methods don't exist)

- [ ] **Step 3: Add sid to login request schemas**

In `src/apps/user/schemas.py`, add `sid: Optional[str] = None` to these three classes:

```python
class LoginEmailPasswordRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)
    meta: Meta = Field(default_factory=Meta)
    sid: Optional[str] = None  # add this


class LoginEmailRequest(BaseModel):
    email: EmailStr
    verify_code: str
    meta: Meta = Field(default_factory=Meta)
    sid: Optional[str] = None  # add this


class LoginPhoneRequest(BaseModel):
    phone: str
    verify_code: str
    meta: Meta = Field(default_factory=Meta)
    sid: Optional[str] = None  # add this
```

Also add `thbwiki` and update `voter_fe_from_user`:

```python
def voter_fe_from_user(user) -> VoterFE:
    return VoterFE(
        username=user.nickname,
        pfp=user.pfp,
        password=bool(user.password_hash),
        phone=user.phone_number,
        email=user.email,
        thbwiki=bool(user.thbwiki_uid),   # change from False
        patchyvideo=False,
        created_at=user.register_date,
    )
```

- [ ] **Step 4: Add bind_sso and _merge_sso_session to UserService**

In `src/apps/user/service.py`, update the `__init__` to accept an optional `redis` parameter and store it:

```python
def __init__(
    self,
    user_dao: UserDAO,
    activity_dao: ActivityLogDAO,
    email_code_service,
    sms_code_service,
    auth: AuthProvider,
    redis=None,
    settings=None,
):
    self.user_dao = user_dao
    self.activity_dao = activity_dao
    self.email_code_service = email_code_service
    self.sms_code_service = sms_code_service
    self.auth = auth
    self.redis = redis
    self.settings = settings or get_settings()
```

Check how the router currently instantiates UserService (`_make_service`) and add `redis=redis` to the call there.

Add these two methods to `UserService`:

```python
async def _merge_sso_session(self, user, sid: Optional[str]) -> None:
    """If sid is present, consume the LoginSession and write SSO IDs to user row."""
    if not sid or not self.redis:
        return
    from .sso_session import consume_sso_session
    data = await consume_sso_session(self.redis, sid)
    if not data:
        return
    changed = False
    if data.get("thbwiki_uid") and user.thbwiki_uid is None:
        user.thbwiki_uid = data["thbwiki_uid"]
        changed = True
    if data.get("qq_openid") and user.qq_openid is None:
        user.qq_openid = data["qq_openid"]
        changed = True
    if changed:
        await self.user_dao.save(user)

async def bind_sso(self, user_token: str, sso_data: dict):
    """Bind an SSO identifier to an already-authenticated user.

    Args:
        user_token: session token from request body.
        sso_data: dict with one of ``thbwiki_uid`` or ``qq_openid``.

    Returns:
        Updated VoterFE.

    Raises:
        AppException: UNAUTHORIZED if token invalid; SSO_ID_ALREADY_BOUND if
            the identifier is already claimed by another account; CONFLICT if
            bound to this account already (idempotent success is handled
            by returning normally without raising).
    """
    user = await self._decode_session_token(user_token)

    thbwiki_uid = sso_data.get("thbwiki_uid")
    qq_openid = sso_data.get("qq_openid")

    if thbwiki_uid:
        existing = await self.user_dao.find_by_thbwiki_uid(thbwiki_uid)
        if existing and existing.id != user.id:
            raise AppException(
                "SSO_ID_ALREADY_BOUND",
                "This THBWiki account is already linked to another user",
                details=409,
            )
        if user.thbwiki_uid != thbwiki_uid:
            user.thbwiki_uid = thbwiki_uid
            await self.user_dao.save(user)

    if qq_openid:
        existing = await self.user_dao.find_by_qq_openid(qq_openid)
        if existing and existing.id != user.id:
            raise AppException(
                "SSO_ID_ALREADY_BOUND",
                "This QQ account is already linked to another user",
                details=409,
            )
        if user.qq_openid != qq_openid:
            user.qq_openid = qq_openid
            await self.user_dao.save(user)

    return voter_fe_from_user(user)
```

In each of the three login methods (`login_email`, `login_phone`, `login_email_password`), add a call to `_merge_sso_session` after the user is obtained:

```python
# After successful login/signup, before return:
await self._merge_sso_session(user, req.sid)
```

- [ ] **Step 5: Add DAO lookup methods**

In `src/apps/user/dao.py`, add to `UserDAO`:

```python
async def find_by_thbwiki_uid(self, thbwiki_uid: str) -> Optional[User]:
    from sqlalchemy import select
    result = await self.session.execute(
        select(User).where(User.thbwiki_uid == thbwiki_uid)
    )
    return result.scalar_one_or_none()

async def find_by_qq_openid(self, qq_openid: str) -> Optional[User]:
    from sqlalchemy import select
    result = await self.session.execute(
        select(User).where(User.qq_openid == qq_openid)
    )
    return result.scalar_one_or_none()
```

- [ ] **Step 6: Run integration tests to verify they pass**

```bash
pytest tests/integration/test_sso_flows.py -xvs
```

Expected: PASS

- [ ] **Step 7: Run full test suite**

```bash
pytest tests/ -x --tb=short -q
```

Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add src/apps/user/service.py src/apps/user/dao.py src/apps/user/schemas.py
git commit -m "feat(sso): add bind_sso, merge_sso_session, sid on login requests (B-007)"
```

---

## Task 7: Final integration test for the full SSO flow

**Files:**
- Modify: `tests/integration/test_sso_flows.py`

- [ ] **Step 1: Add end-to-end flow test**

Add to `tests/integration/test_sso_flows.py`:

```python
@pytest.mark.asyncio
async def test_full_qq_sso_flow(db_session, fake_redis):
    """Full flow: create QQ session → login with sid → user has qq_openid."""
    from src.apps.user.sso_session import create_sso_session
    from src.apps.user.service import UserService
    from src.apps.user.dao import UserDAO, ActivityLogDAO
    from src.apps.user.utils.security import AuthProvider
    from src.common.verification import get_email_code_service
    from src.common.config import get_settings

    settings = get_settings()
    sid = await create_sso_session(fake_redis, {"qq_openid": "end-to-end-openid"})

    async with db_session() as session:
        from tests.integration.test_login_flows import _seed_email_user, _set_email_code
        await _seed_email_user(session, email="e2e@example.com")
        await _set_email_code(fake_redis, "e2e@example.com", "654321")

        svc = UserService(
            user_dao=UserDAO(session),
            activity_dao=ActivityLogDAO(session),
            email_code_service=get_email_code_service(),
            sms_code_service=None,
            auth=AuthProvider(settings),
            redis=fake_redis,
            settings=settings,
        )

        from src.apps.user.schemas import LoginEmailRequest, Meta
        req = LoginEmailRequest(
            email="e2e@example.com",
            verify_code="654321",
            meta=Meta(user_ip="127.0.0.1"),
            sid=sid,
        )
        resp = await svc.login_email(req)

    assert resp.user.thbwiki is False  # didn't set thbwiki
    # Can't check qq directly from VoterFE but confirm no error
    # Verify DB state
    async with db_session() as session:
        from sqlalchemy import select
        from src.db_model.user import User
        u = await session.scalar(select(User).where(User.email == "e2e@example.com"))
        assert u.qq_openid == "end-to-end-openid"

    # Consuming the same sid again must return None (session deleted)
    result = await consume_sso_session(fake_redis, sid)
    assert result is None
```

- [ ] **Step 2: Run full SSO test suite**

```bash
pytest tests/integration/test_sso_flows.py tests/unit/test_sso_session.py tests/unit/test_sso_clients.py tests/contract/test_sso_endpoints.py -v
```

Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_sso_flows.py
git commit -m "test(sso): add end-to-end SSO flow integration tests (B-007)"
```
