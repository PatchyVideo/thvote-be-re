"""GraphQL 登录 mutation 端到端：in-memory sqlite + fakeredis + mock Aliyun。

通过 schema.execute 跑，monkeypatch 把 resolver 的 get_db_session / build_user_service
指向测试夹具（带假 PNVS/SMTP 的 user_service）。
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from src.apps.user.dao import UserDAO
from src.apps.user.schemas import generate_user_id
from src.apps.user.utils.security import AuthProvider
from src.db_model.user import User


class _FakeClient:
    host = "1.2.3.4"


class _FakeRequest:
    client = _FakeClient()
    headers: dict = {}


# Read-only request context for schema.execute; tests must never mutate it.
CTX = {"request": _FakeRequest()}


@pytest_asyncio.fixture
async def gql_schema(monkeypatch, session, user_service):
    """schema，其 user resolver 被指向测试 session + 假外部服务的 user_service。"""
    import src.api.graphql.resolvers.user as user_resolver

    # Resolver consumes this with `async for db in get_db_session()`, so the
    # double must be an async generator (yields the test session once).
    async def _fake_db():
        yield session

    monkeypatch.setattr(user_resolver, "get_db_session", _fake_db)
    monkeypatch.setattr(user_resolver, "build_user_service", lambda db: user_service)

    from src.api.graphql.schema import schema

    return schema


LOGIN_EMAIL_PASSWORD = """
mutation($email: String!, $password: String!) {
  loginEmailPassword(email: $email, password: $password) {
    user { username email password phone thbwiki patchyvideo createdAt }
    sessionToken
    voteToken
  }
}
"""

REQUEST_EMAIL_CODE = """
mutation($email: String!) { requestEmailCode(email: $email) }
"""

LOGIN_EMAIL = """
mutation($email: String!, $verifyCode: String!, $nickname: String) {
  loginEmail(email: $email, verifyCode: $verifyCode, nickname: $nickname) {
    user { email }
    sessionToken
  }
}
"""


@pytest.mark.asyncio
async def test_login_email_password_success(gql_schema, session):
    user = User(
        id=generate_user_id(),
        email="alice@example.com",
        email_verified=True,
        password_hash=AuthProvider().hash_password("s3cret"),
    )
    await UserDAO(session).create(user)

    result = await gql_schema.execute(
        LOGIN_EMAIL_PASSWORD,
        variable_values={"email": "alice@example.com", "password": "s3cret"},
        context_value=CTX,
    )
    assert result.errors is None, result.errors
    data = result.data["loginEmailPassword"]
    assert data["user"]["email"] == "alice@example.com"
    assert data["user"]["password"] is True
    assert data["sessionToken"]


@pytest.mark.asyncio
async def test_login_email_password_wrong_password_error_kind(gql_schema, session):
    user = User(
        id=generate_user_id(),
        email="bob@example.com",
        email_verified=True,
        password_hash=AuthProvider().hash_password("right"),
    )
    await UserDAO(session).create(user)

    result = await gql_schema.execute(
        LOGIN_EMAIL_PASSWORD,
        variable_values={"email": "bob@example.com", "password": "wrong"},
        context_value=CTX,
    )
    assert result.errors is not None
    assert result.errors[0].extensions["error_kind"] == "INCORRECT_PASSWORD"
    assert result.errors[0].extensions["service"] == "user-manager"


@pytest.mark.asyncio
async def test_request_email_code_returns_true(gql_schema):
    result = await gql_schema.execute(
        REQUEST_EMAIL_CODE,
        variable_values={"email": "carol@example.com"},
        context_value=CTX,
    )
    assert result.errors is None, result.errors
    assert result.data["requestEmailCode"] is True


@pytest.mark.asyncio
async def test_login_email_wrong_code_error_kind(gql_schema):
    # 没先写验证码，consume 必然失败 → INCORRECT_VERIFY_CODE
    result = await gql_schema.execute(
        LOGIN_EMAIL,
        variable_values={"email": "dave@example.com", "verifyCode": "000000", "nickname": None},
        context_value=CTX,
    )
    assert result.errors is not None
    assert result.errors[0].extensions["error_kind"] == "INCORRECT_VERIFY_CODE"
    assert result.errors[0].extensions["service"] == "user-manager"


@pytest.mark.asyncio
async def test_login_email_registers_new_user_after_valid_code(gql_schema, patch_redis):
    await patch_redis.set("email-verify-erin@example.com", "123456")
    result = await gql_schema.execute(
        LOGIN_EMAIL,
        variable_values={"email": "erin@example.com", "verifyCode": "123456", "nickname": "Erin"},
        context_value=CTX,
    )
    assert result.errors is None, result.errors
    assert result.data["loginEmail"]["user"]["email"] == "erin@example.com"
    assert result.data["loginEmail"]["sessionToken"]


LOGIN_PHONE = """
mutation($phone: String!, $verifyCode: String!, $nickname: String) {
  loginPhone(phone: $phone, verifyCode: $verifyCode, nickname: $nickname) {
    user { phone }
    sessionToken
    voteToken
  }
}
"""


@pytest.mark.asyncio
async def test_login_phone_success_with_mocked_pnvs(gql_schema):
    # PNVS is mocked via the user_service fixture (check returns passed=True),
    # so any verifyCode passes and a new phone registers a user.
    result = await gql_schema.execute(
        LOGIN_PHONE,
        variable_values={"phone": "13800000000", "verifyCode": "123456", "nickname": None},
        context_value=CTX,
    )
    assert result.errors is None, result.errors
    assert result.data["loginPhone"]["user"]["phone"] == "13800000000"
    assert result.data["loginPhone"]["sessionToken"]
    # voteToken is always a string ("" outside the vote window); assert the field resolves.
    assert isinstance(result.data["loginPhone"]["voteToken"], str)


@pytest.mark.asyncio
async def test_login_rate_limited_on_6th_request(gql_schema):
    # Per-IP login limit is 5/60s (key: rate-limit-login-1.2.3.4): calls 1-5 pass,
    # the 6th is rejected with REQUEST_TOO_FREQUENT. patch_redis gives a fresh
    # per-test counter, so this is deterministic and isolated.
    last = None
    for _ in range(6):
        last = await gql_schema.execute(
            LOGIN_PHONE,
            variable_values={"phone": "13800000001", "verifyCode": "123456", "nickname": None},
            context_value=CTX,
        )
    assert last.errors is not None
    assert last.errors[0].extensions["error_kind"] == "REQUEST_TOO_FREQUENT"
