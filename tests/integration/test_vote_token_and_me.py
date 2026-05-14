"""vote_token signing scenarios + GET /me + bcrypt upgrade integration tests.

Covers B-014, B-015, B-016.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import freezegun
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.apps.user.schemas import LoginEmailRequest, Meta
from src.apps.user.utils.security import AuthProvider
from src.common.security.jwt import decode_vote_token
from src.db_model.base import Base

# ── Fixtures ──────────────────────────────────────────────────────────

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-do-not-use-in-prod")
os.environ.setdefault("VOTE_START_ISO", "2026-01-01T00:00:00+00:00")
os.environ.setdefault("VOTE_END_ISO", "2026-12-31T23:59:59+00:00")


async def _login_via_email(user_service, patch_redis, email="a@test.com", nickname="a"):
    """Helper: set code in Redis, call login, return LoginResponse."""
    await patch_redis.set(f"email-verify-{email}", "999999", ex=3600)
    return await user_service.login_with_email_code(
        LoginEmailRequest(email=email, nickname=nickname, verify_code="999999", meta=Meta())
    )


# ── B-014: vote_token signing scenarios ──────────────────────────────

@pytest.mark.asyncio
async def test_vote_token_signed_for_verified_user_within_window(user_service, patch_redis):
    """Verified user + within vote window → non-empty vote_token.

    VOTE_START/END_ISO env vars are set to 2026 range; tests run in 2026,
    so no time freezing is needed — the current date is within the window.
    """
    resp = await _login_via_email(user_service, patch_redis, "vt1@test.com")
    assert resp.vote_token, "Expected a non-empty vote_token"
    # Verify the token can be decoded (structure is correct) by peeking at
    # the payload without full validation (avoids iat clock-skew issues in CI)
    import jwt as pyjwt
    from src.common.config import get_settings
    settings = get_settings()
    payload = pyjwt.decode(
        resp.vote_token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        audience="vote",
        options={"verify_iat": False},
    )
    assert payload.get("user_id") or payload.get("sub")


@pytest.mark.asyncio
async def test_vote_token_empty_outside_vote_window(user_service, monkeypatch):
    """Verified user + OUTSIDE vote window → empty vote_token.

    Patches get_settings inside user.service to return a past vote window,
    so the current wall-clock time is guaranteed to be after vote_end.
    """
    from unittest.mock import MagicMock
    from src.db_model.user import User

    mock_settings = MagicMock()
    mock_settings.vote_start_iso = "2020-01-01T00:00:00+00:00"
    mock_settings.vote_end_iso = "2020-12-31T23:59:59+00:00"
    monkeypatch.setattr("src.apps.user.service.get_settings", lambda: mock_settings)

    verified_user = User(
        id="outside-uid",
        email="outside@test.com",
        email_verified=True,
        phone_verified=False,
        removed=False,
        register_date=datetime.now(UTC),
        register_ip_address="1.2.3.4",
    )
    result = user_service._maybe_sign_vote_token(verified_user)
    assert result == "", "vote_token must be empty when now > vote_end"


@pytest.mark.asyncio
async def test_vote_token_empty_for_unverified_user(user_service, patch_redis):
    """Unverified user (neither email nor phone verified) → empty vote_token."""
    from src.db_model.user import User

    unverified = User(
        id="unverified-uid",
        email="unverified@test.com",
        email_verified=False,
        phone_verified=False,
        removed=False,
        register_date=datetime.now(UTC),
        register_ip_address="1.2.3.4",
    )
    result = user_service._maybe_sign_vote_token(unverified)
    assert result == "", "Unverified user must not receive a vote_token"


@pytest.mark.asyncio
async def test_vote_token_has_correct_audience_and_subject(user_service, patch_redis):
    """vote_token payload: aud='vote', sub/user_id is the authenticated user."""
    resp = await _login_via_email(user_service, patch_redis, "vt3@test.com")
    assert resp.vote_token
    import jwt as pyjwt
    from src.common.config import get_settings
    settings = get_settings()
    payload = pyjwt.decode(
        resp.vote_token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        audience="vote",
        options={"verify_iat": False},
    )
    assert payload.get("aud") == "vote"
    assert payload.get("user_id") or payload.get("sub")


# ── B-015: GET /me integration test ──────────────────────────────────

@pytest_asyncio.fixture
async def http_client():
    """Full-stack TestClient against the FastAPI app with SQLite + fakeredis."""
    from src.main import create_app

    app = create_app()
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(bind=eng, class_=AsyncSession, expire_on_commit=False)

    async def _db():
        async with maker() as s:
            yield s

    from src.common.database import get_db_session
    app.dependency_overrides[get_db_session] = _db

    try:
        import fakeredis.aioredis as fakeredis
        fake_redis = fakeredis.FakeRedis(decode_responses=True)
    except ImportError:
        import fakeredis
        fake_redis = fakeredis.FakeRedis(decode_responses=True)

    with patch("src.common.redis.get_redis", return_value=fake_redis), \
         patch("src.common.verification.email_code.get_redis", return_value=fake_redis), \
         patch("src.common.middleware.rate_limit.get_redis", return_value=fake_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c, fake_redis

    await eng.dispose()


@pytest.mark.asyncio
async def test_get_me_returns_voter_fe(http_client):
    """GET /me with valid Bearer session_token returns VoterFE."""
    client, fake_redis = http_client

    # Register a user via email login
    await fake_redis.set("email-verify-me@test.com", "123456", ex=3600)
    with patch("src.common.aliyun.dm_smtp_client.AliyunDmSmtpClient"):
        login_resp = await client.post("/api/v1/user/login-email", json={
            "email": "me@test.com",
            "nickname": "meuser",
            "verify_code": "123456",
            "meta": {},
        })
    assert login_resp.status_code == 200
    session_token = login_resp.json()["session_token"]

    me_resp = await client.get(
        "/api/v1/user/me",
        headers={"Authorization": f"Bearer {session_token}"},
    )
    assert me_resp.status_code == 200
    data = me_resp.json()
    assert data["email"] == "me@test.com"
    assert data["username"] == "meuser"


@pytest.mark.asyncio
async def test_get_me_rejects_missing_token(http_client):
    """GET /me without Authorization header → 401."""
    client, _ = http_client
    resp = await client.get("/api/v1/user/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me_rejects_invalid_token(http_client):
    """GET /me with garbage token → 401."""
    client, _ = http_client
    resp = await client.get("/api/v1/user/me", headers={"Authorization": "Bearer garbage.token"})
    assert resp.status_code == 401


# ── B-016: bcrypt → argon2 upgrade ───────────────────────────────────

@pytest.mark.asyncio
async def test_bcrypt_login_upgrades_to_argon2(user_service, session):
    """User with legacy bcrypt hash can log in; hash is upgraded to argon2."""
    import bcrypt
    from src.db_model.user import User

    # Create a user with a bcrypt-hashed password (legacy format)
    legacy_salt = bcrypt.gensalt().decode()
    legacy_hash = bcrypt.hashpw(
        ("testpass" + legacy_salt).encode(), bcrypt.gensalt()
    ).decode()

    user = User(
        id="bcrypt-user-001",
        email="bcrypt@test.com",
        email_verified=True,
        password_hash=legacy_hash,
        legacy_salt=legacy_salt,
        removed=False,
        register_date=datetime.now(UTC),
        register_ip_address="127.0.0.1",
    )
    session.add(user)
    await session.commit()

    from src.apps.user.schemas import LoginEmailPasswordRequest
    resp = await user_service.login_with_email_password(
        LoginEmailPasswordRequest(
            email="bcrypt@test.com",
            password="testpass",
            meta=Meta(),
        )
    )
    assert resp.session_token, "Login with bcrypt hash must succeed"

    # Reload and verify the hash has been upgraded to argon2
    await session.refresh(user)
    assert user.legacy_salt is None, "legacy_salt must be cleared after upgrade"
    assert user.password_hash is not None
    assert user.password_hash != legacy_hash, "password_hash must be updated"
    # argon2 hashes start with $argon2
    assert user.password_hash.startswith("$argon2"), "New hash must be argon2"
