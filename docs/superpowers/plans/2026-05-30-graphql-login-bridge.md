# GraphQL 登录桥接 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 Python 后端 `thvote-be-re` 增加 5 个 GraphQL 登录 mutation，包装现有 `UserService`，让前端 `LoginBox.vue` 的 GraphQL 登录契约通起来。

**Architecture:** 新增 `resolvers/user.py` 定义 `UserMutation`，每个 resolver 复用已测的 `UserService`，只做参数组装 + 限流 + 错误翻译 + 类型转换。错误结构复刻 Rust `ServiceError`（含上游码透传），需给 `AppException` 加可选诊断字段并在 PNVS 失败处填充。REST 端点与 submit/result resolver 完全不动。

**Tech Stack:** FastAPI · Strawberry GraphQL (>=0.219) · SQLAlchemy async · pytest + pytest-asyncio（显式 `@pytest.mark.asyncio`）· fakeredis（autouse 夹具）

**设计稿：** `docs/superpowers/specs/2026-05-30-graphql-login-bridge-design.md`

---

## 文件结构

| 文件 | 责任 |
|---|---|
| `src/common/exceptions.py`（改） | `AppException` 增加可选 `error_message` / `upstream_response_string` |
| `src/common/aliyun/pnvs_client.py`（改） | 发送失败时把阿里云 `code`/`message` 填进异常 |
| `src/api/graphql/types.py`（改） | 新增 `VoterFEType`、`LoginResult`、`login_result_from_pydantic` |
| `src/api/graphql/resolvers/user.py`（建） | `UserMutation`(5 resolver) + `map_app_errors` + `_client_ip_from_info` + `build_user_service` |
| `src/api/graphql/schema.py`（改） | `Mutation(SubmitMutation, UserMutation)` |
| `tests/unit/test_exceptions_fields.py`（建） | AppException 新字段 |
| `tests/unit/test_pnvs_upstream_passthrough.py`（建） | PNVS 上游码透传 |
| `tests/unit/test_graphql_error_mapping.py`（建） | `map_app_errors` + `_client_ip_from_info` |
| `tests/integration/test_graphql_login.py`（建） | 5 个 mutation 端到端（schema.execute） |
| `tests/contract/test_graphql_login_contract.py`（建） | 内省锁字段名/camelCase |

---

## Task 1: AppException 增加可选诊断字段

**Files:**
- Modify: `src/common/exceptions.py:6-12`
- Test: `tests/unit/test_exceptions_fields.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_exceptions_fields.py
from src.common.exceptions import AppException, ValidationError


def test_appexception_carries_optional_diagnostic_fields():
    exc = ValidationError(
        "INVALID_PHONE",
        details=400,
        error_message="bad number",
        upstream_response_string="isv.MOBILE_NUMBER_ILLEGAL",
    )
    assert exc.message == "INVALID_PHONE"
    assert exc.details == 400
    assert exc.error_message == "bad number"
    assert exc.upstream_response_string == "isv.MOBILE_NUMBER_ILLEGAL"


def test_appexception_defaults_diagnostic_fields_to_none():
    exc = AppException("X")
    assert exc.error_message is None
    assert exc.upstream_response_string is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/unit/test_exceptions_fields.py -v`
Expected: FAIL（`TypeError: __init__() got an unexpected keyword argument 'error_message'`）

- [ ] **Step 3: 实现**

把 `src/common/exceptions.py` 的 `AppException.__init__` 改为：

```python
class AppException(Exception):
    """Base exception for all application exceptions."""

    def __init__(
        self,
        message: str,
        details: Optional[Any] = None,
        error_message: Optional[str] = None,
        upstream_response_string: Optional[str] = None,
    ):
        self.message = message
        self.details = details
        self.error_message = error_message
        self.upstream_response_string = upstream_response_string
        super().__init__(self.message)
```

（子类 `ValidationError` 等都 `pass`，继承此 `__init__`，无需改。）

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/unit/test_exceptions_fields.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 回归——确认没破坏现有异常用法**

Run: `python -m pytest tests/unit -q`
Expected: 全绿（新字段有默认值，旧调用点不受影响）

- [ ] **Step 6: 提交**

```bash
git add src/common/exceptions.py tests/unit/test_exceptions_fields.py
git commit -m "feat(exceptions): add optional error_message/upstream_response_string to AppException"
```

---

## Task 2: PNVS 发送失败透传上游码

**Files:**
- Modify: `src/common/aliyun/pnvs_client.py:144-169`（`_parse_send_response`）、`:112-116`（transport except）
- Test: `tests/unit/test_pnvs_upstream_passthrough.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_pnvs_upstream_passthrough.py
import pytest

from src.common.aliyun.pnvs_client import _parse_send_response
from src.common.exceptions import ExternalAPIError, RateLimitError, ValidationError


class _Body:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Resp:
    def __init__(self, body):
        self.body = body


def test_rate_limit_failure_passes_upstream_code():
    resp = _Resp(_Body(code="isv.BUSINESS_LIMIT_CONTROL", message="too many", request_id="r1"))
    with pytest.raises(RateLimitError) as ei:
        _parse_send_response(resp)
    assert ei.value.message == "REQUEST_TOO_FREQUENT"
    assert ei.value.upstream_response_string == "isv.BUSINESS_LIMIT_CONTROL"
    assert ei.value.error_message == "too many"


def test_invalid_phone_passes_upstream_code():
    resp = _Resp(_Body(code="isv.MOBILE_NUMBER_ILLEGAL", message="bad", request_id="r2"))
    with pytest.raises(ValidationError) as ei:
        _parse_send_response(resp)
    assert ei.value.message == "INVALID_PHONE"
    assert ei.value.upstream_response_string == "isv.MOBILE_NUMBER_ILLEGAL"


def test_unknown_failure_is_sms_send_failed_with_upstream():
    resp = _Resp(_Body(code="isv.SOMETHING_ELSE", message="boom", request_id="r3"))
    with pytest.raises(ExternalAPIError) as ei:
        _parse_send_response(resp)
    assert ei.value.message == "SMS_SEND_FAILED"
    assert ei.value.upstream_response_string == "isv.SOMETHING_ELSE"
    assert ei.value.error_message == "boom"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/unit/test_pnvs_upstream_passthrough.py -v`
Expected: FAIL（`assert None == 'isv.BUSINESS_LIMIT_CONTROL'`）

- [ ] **Step 3: 实现**

把 `src/common/aliyun/pnvs_client.py` 的 `_parse_send_response` 三个 raise 改为带上 `code`/`message`：

```python
    if code in {"isv.MOBILE_NUMBER_ILLEGAL", "isv.MOBILE_COUNTRY_NOT_SUPPORTED"}:
        raise ValidationError(
            "INVALID_PHONE", details=400,
            error_message=message, upstream_response_string=code,
        )
    if code in {
        "isv.BUSINESS_LIMIT_CONTROL",
        "isv.OUT_OF_SERVICE",
        "isv.SMS_TEST_NUMBER_NOT_LOGIN",
    } or (code or "").endswith("_LIMIT_CONTROL"):
        raise RateLimitError(
            "REQUEST_TOO_FREQUENT", details=429,
            error_message=message, upstream_response_string=code,
        )
    raise ExternalAPIError(
        "SMS_SEND_FAILED", details=502,
        error_message=message, upstream_response_string=code,
    )
```

并把 `send_sms_verify_code` 里 transport 失败的 raise（约 `:116`）改为带上异常文本：

```python
        except Exception as exc:  # SDK / network failures
            logger.exception("PNVS send_sms_verify_code transport failure")
            raise ExternalAPIError(
                "SMS_SEND_FAILED", details=502, error_message=str(exc)
            ) from exc
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/unit/test_pnvs_upstream_passthrough.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 回归 PNVS 现有测试**

Run: `python -m pytest tests/unit/test_pnvs_client.py -q`
Expected: 全绿

- [ ] **Step 6: 提交**

```bash
git add src/common/aliyun/pnvs_client.py tests/unit/test_pnvs_upstream_passthrough.py
git commit -m "feat(pnvs): surface Aliyun upstream code/message on send failure"
```

---

## Task 3: GraphQL 类型 VoterFEType / LoginResult + 转换器

**Files:**
- Modify: `src/api/graphql/types.py`（文件末尾追加）
- Test: `tests/unit/test_graphql_login_types.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_graphql_login_types.py
from datetime import datetime, timezone

from src.api.graphql.types import LoginResult, VoterFEType, login_result_from_pydantic
from src.apps.user.schemas import LoginResponse, VoterFE


def test_login_result_from_pydantic_maps_all_fields():
    created = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    resp = LoginResponse(
        user=VoterFE(
            username="alice", pfp=None, password=True,
            phone=None, email="a@b.com", thbwiki=False,
            patchyvideo=False, created_at=created,
        ),
        session_token="sess-123",
        vote_token="vote-456",
    )
    out = login_result_from_pydantic(resp)
    assert isinstance(out, LoginResult)
    assert isinstance(out.user, VoterFEType)
    assert out.user.username == "alice"
    assert out.user.email == "a@b.com"
    assert out.user.password is True
    assert out.user.created_at == created
    assert out.session_token == "sess-123"
    assert out.vote_token == "vote-456"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/unit/test_graphql_login_types.py -v`
Expected: FAIL（`ImportError: cannot import name 'LoginResult'`）

- [ ] **Step 3: 实现**

在 `src/api/graphql/types.py` 末尾追加（文件顶部已 `import strawberry`、`from datetime import datetime`、`from typing import Optional`）：

```python
from src.apps.user.schemas import LoginResponse as LoginResponsePydantic  # noqa: E402


@strawberry.type(name="VoterFE")
class VoterFEType:
    username: Optional[str]
    pfp: Optional[str]
    password: bool
    phone: Optional[str]
    email: Optional[str]
    thbwiki: bool
    patchyvideo: bool
    created_at: datetime


@strawberry.type
class LoginResult:
    user: VoterFEType
    session_token: str
    vote_token: str


def login_result_from_pydantic(resp: "LoginResponsePydantic") -> LoginResult:
    u = resp.user
    return LoginResult(
        user=VoterFEType(
            username=u.username,
            pfp=u.pfp,
            password=u.password,
            phone=u.phone,
            email=u.email,
            thbwiki=u.thbwiki,
            patchyvideo=u.patchyvideo,
            created_at=u.created_at,
        ),
        session_token=resp.session_token,
        vote_token=resp.vote_token,
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/unit/test_graphql_login_types.py -v`
Expected: PASS（1 passed）

- [ ] **Step 5: 提交**

```bash
git add src/api/graphql/types.py tests/unit/test_graphql_login_types.py
git commit -m "feat(graphql): add VoterFE/LoginResult types and converter"
```

---

## Task 4: 错误映射 map_app_errors + 客户端 IP

**Files:**
- Create: `src/api/graphql/resolvers/user.py`（本任务只放 helper，下个任务补 mutation）
- Test: `tests/unit/test_graphql_error_mapping.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_graphql_error_mapping.py
import pytest
from fastapi import HTTPException
from graphql import GraphQLError

from src.api.graphql.resolvers.user import _client_ip_from_info, map_app_errors
from src.common.exceptions import RateLimitError, ValidationError


@pytest.mark.asyncio
async def test_maps_appexception_to_rust_extension_shape():
    with pytest.raises(GraphQLError) as ei:
        async with map_app_errors(service="user-manager"):
            raise ValidationError("INCORRECT_PASSWORD", details=400)
    ext = ei.value.extensions
    assert ext["service"] == "user-manager"
    assert ext["error_kind"] == "INCORRECT_PASSWORD"
    assert ext["url"] is None
    assert ext["human_readable_message"] is None


@pytest.mark.asyncio
async def test_passes_upstream_fields_through():
    with pytest.raises(GraphQLError) as ei:
        async with map_app_errors(service="sms-service"):
            raise RateLimitError(
                "REQUEST_TOO_FREQUENT", details=429,
                error_message="m", upstream_response_string="isv.X",
            )
    ext = ei.value.extensions
    assert ext["error_kind"] == "REQUEST_TOO_FREQUENT"
    assert ext["error_message"] == "m"
    assert ext["upstream_response_string"] == "isv.X"


@pytest.mark.asyncio
async def test_maps_ratelimit_httpexception_detail_to_error_kind():
    with pytest.raises(GraphQLError) as ei:
        async with map_app_errors(service="user-manager"):
            raise HTTPException(status_code=429, detail="REQUEST_TOO_FREQUENT")
    assert ei.value.extensions["error_kind"] == "REQUEST_TOO_FREQUENT"


@pytest.mark.asyncio
async def test_unexpected_exception_maps_to_internal_error():
    with pytest.raises(GraphQLError) as ei:
        async with map_app_errors(service="user-manager"):
            raise RuntimeError("boom")
    assert ei.value.extensions["error_kind"] == "INTERNAL_ERROR"


def test_client_ip_from_dict_context():
    class _C:
        host = "9.9.9.9"

    class _R:
        client = _C()
        headers: dict = {}

    class _Info:
        context = {"request": _R()}

    assert _client_ip_from_info(_Info()) == "9.9.9.9"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/unit/test_graphql_error_mapping.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'src.api.graphql.resolvers.user'`）

- [ ] **Step 3: 实现**

新建 `src/api/graphql/resolvers/user.py`：

```python
"""GraphQL UserMutation — bridges the REST-tested UserService to GraphQL.

The frontend login page (LoginBox.vue) drives login entirely through
GraphQL mutations; the REST /user/* endpoints are unchanged.  Each
resolver here only assembles the existing Pydantic request, enforces the
same rate limit as REST, delegates to UserService, and translates errors
into the Rust-aligned extensions shape the frontend reads.
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
from src.common.database import get_db_session, get_session_maker
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


def _extensions(service: str, error_kind: str, *, error_message=None, upstream=None) -> dict:
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
    except Exception as exc:
        raise GraphQLError(
            "Error", extensions=_extensions(service, "INTERNAL_ERROR")
        ) from exc
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/unit/test_graphql_error_mapping.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add src/api/graphql/resolvers/user.py tests/unit/test_graphql_error_mapping.py
git commit -m "feat(graphql): add map_app_errors + client-ip helpers for user resolvers"
```

---

## Task 5: UserMutation 5 个 resolver + 挂进 schema

**Files:**
- Modify: `src/api/graphql/resolvers/user.py`（追加 `UserMutation`）
- Modify: `src/api/graphql/schema.py`
- Test: 本任务只做"schema 能内省到 5 个字段"的烟测，端到端留 Task 6/7

- [ ] **Step 1: 写失败测试（烟测：字段存在）**

```python
# tests/contract/test_graphql_login_contract.py
import pytest

from src.api.graphql.schema import schema

INTROSPECT = """
{ __schema { mutationType { fields { name } } } }
"""


@pytest.mark.asyncio
async def test_login_mutations_present_and_camelcase():
    result = await schema.execute(INTROSPECT)
    assert result.errors is None
    names = {f["name"] for f in result.data["__schema"]["mutationType"]["fields"]}
    for expected in {
        "requestPhoneCode",
        "requestEmailCode",
        "loginPhone",
        "loginEmail",
        "loginEmailPassword",
    }:
        assert expected in names, f"missing mutation {expected}"
    # submit mutations must still be there
    assert "submitCharacter" in names
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/contract/test_graphql_login_contract.py -v`
Expected: FAIL（`missing mutation requestPhoneCode`）

- [ ] **Step 3: 实现 resolver**

在 `src/api/graphql/resolvers/user.py` 顶部 import 区补：

```python
from src.api.graphql.types import LoginResult, login_result_from_pydantic
from src.apps.user.schemas import (
    LoginEmailPasswordRequest,
    LoginEmailRequest,
    LoginPhoneRequest,
    Meta,
    SendEmailCodeRequest,
    SendSmsCodeRequest,
)
from src.common.middleware.rate_limit import rate_limit
```

并在文件末尾追加：

```python
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

    @strawberry.mutation
    async def request_email_code(self, info: strawberry.Info, email: str) -> bool:
        async with map_app_errors(service="mail-service"):
            ip = _client_ip_from_info(info)
            req = SendEmailCodeRequest(email=email, meta=Meta(user_ip=ip))
            async for db in get_db_session():
                await build_user_service(db).send_email_code(req)
        return True

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
                return login_result_from_pydantic(resp)
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
                return login_result_from_pydantic(resp)
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
                return login_result_from_pydantic(resp)
        raise RuntimeError("unreachable")  # pragma: no cover
```

- [ ] **Step 4: 挂进 root Mutation**

把 `src/api/graphql/schema.py` 改为：

```python
from .resolvers.result import ResultQuery
from .resolvers.submit import SubmitMutation, SubmitQuery
from .resolvers.user import UserMutation


@strawberry.type
class Query(SubmitQuery, ResultQuery):
    pass


@strawberry.type
class Mutation(SubmitMutation, UserMutation):
    pass


schema = strawberry.Schema(query=Query, mutation=Mutation)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/contract/test_graphql_login_contract.py -v`
Expected: PASS（1 passed）

- [ ] **Step 6: 提交**

```bash
git add src/api/graphql/resolvers/user.py src/api/graphql/schema.py tests/contract/test_graphql_login_contract.py
git commit -m "feat(graphql): add UserMutation with 5 login mutations"
```

---

## Task 6: 登录 mutation 端到端集成测试（成功 + 错误路径）

**Files:**
- Create: `tests/integration/test_graphql_login.py`
- 复用 `tests/integration/conftest.py` 的 `session` / `user_service` / `patch_redis` 夹具

- [ ] **Step 1: 写测试（先失败：还没有 gql 夹具/seed 助手时跑会报错；写完夹具后应通过）**

```python
# tests/integration/test_graphql_login.py
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


CTX = {"request": _FakeRequest()}


@pytest_asyncio.fixture
async def gql_schema(monkeypatch, session, user_service):
    """schema，其 user resolver 被指向测试 session + 假外部服务的 user_service。"""
    import src.api.graphql.resolvers.user as user_resolver

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
    # 没先 requestEmailCode，consume 必然失败 → INCORRECT_VERIFY_CODE
    result = await gql_schema.execute(
        LOGIN_EMAIL,
        variable_values={"email": "dave@example.com", "verifyCode": "000000", "nickname": None},
        context_value=CTX,
    )
    assert result.errors is not None
    assert result.errors[0].extensions["error_kind"] == "INCORRECT_VERIFY_CODE"


@pytest.mark.asyncio
async def test_login_email_registers_new_user_after_valid_code(gql_schema, patch_redis):
    # 写入一个有效邮箱验证码，再用它登录 → 新建用户、签发 token
    await patch_redis.set("email-verify-erin@example.com", "123456")
    result = await gql_schema.execute(
        LOGIN_EMAIL,
        variable_values={"email": "erin@example.com", "verifyCode": "123456", "nickname": "Erin"},
        context_value=CTX,
    )
    assert result.errors is None, result.errors
    assert result.data["loginEmail"]["user"]["email"] == "erin@example.com"
    assert result.data["loginEmail"]["sessionToken"]
```

> 注：邮箱验证码在 Redis 的 key 形如 `email-verify-<email>`（见 `tests/integration/test_login_flows.py` 同款断言）。若 `EmailCodeService.consume` 的 key 规则不同，按该文件实际 key 调整 `patch_redis.set` 的键名。

- [ ] **Step 2: 跑测试确认（先看红/黄）**

Run: `python -m pytest tests/integration/test_graphql_login.py -v`
Expected: 全绿（Task 5 已实现 resolver；本任务是补端到端覆盖）。若 `test_login_email_registers_new_user_after_valid_code` 因 code key 规则不符而失败，按上方注释对齐 key 后再跑。

- [ ] **Step 3: 提交**

```bash
git add tests/integration/test_graphql_login.py
git commit -m "test(graphql): end-to-end login mutations (success + error_kind paths)"
```

---

## Task 7: loginPhone + 限流路径补测

**Files:**
- Modify: `tests/integration/test_graphql_login.py`（追加用例）

- [ ] **Step 1: 追加测试**

```python
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
async def test_login_phone_success_with_mocked_pnvs(gql_schema, fake_pnvs):
    # fake_pnvs.check_sms_verify_code 默认 passed=True → 新用户注册成功
    result = await gql_schema.execute(
        LOGIN_PHONE,
        variable_values={"phone": "13800000000", "verifyCode": "123456", "nickname": None},
        context_value=CTX,
    )
    assert result.errors is None, result.errors
    assert result.data["loginPhone"]["user"]["phone"] == "13800000000"
    assert result.data["loginPhone"]["sessionToken"]


@pytest.mark.asyncio
async def test_login_rate_limited_after_5_requests(gql_schema, fake_pnvs):
    # 第 6 次同 IP 登录应被限流 → REQUEST_TOO_FREQUENT
    last = None
    for _ in range(6):
        last = await gql_schema.execute(
            LOGIN_PHONE,
            variable_values={"phone": "13800000001", "verifyCode": "123456", "nickname": None},
            context_value=CTX,
        )
    assert last.errors is not None
    assert last.errors[0].extensions["error_kind"] == "REQUEST_TOO_FREQUENT"
```

> `fake_pnvs` 来自 `conftest.py`，`check_sms_verify_code` 默认返回 `passed=True`，所以前 5 次登录成功、第 6 次撞 `login-1.2.3.4` 的 5/60s 限流。

- [ ] **Step 2: 跑测试确认通过**

Run: `python -m pytest tests/integration/test_graphql_login.py -v`
Expected: 全绿（含新增 2 个用例）

- [ ] **Step 3: 提交**

```bash
git add tests/integration/test_graphql_login.py
git commit -m "test(graphql): cover loginPhone success + login rate-limit path"
```

---

## Task 8: 全量回归 + 文档 / changelog

**Files:**
- Modify: `docs/CHANGELOG.md`、`REFACTOR_TODO.md`

- [ ] **Step 1: 全量测试回归**

Run: `python -m pytest -q`
Expected: 全绿（新增用例 + 现有用例都过；submit/result/user REST 不受影响）

- [ ] **Step 2: 更新 CHANGELOG**

在 `docs/CHANGELOG.md` 顶部加一节（GraphQL schema 变更按 CLAUDE.md §8 必须记录）：

```markdown
## [2026-05-30] GraphQL 登录 mutation 桥接

### Added
- GraphQL `UserMutation`：`requestPhoneCode` / `requestEmailCode` / `loginPhone` / `loginEmail` / `loginEmailPassword`，包装现有 `UserService`，对齐前端 `LoginBox.vue` 既定契约。
- `LoginResult { user: VoterFE, sessionToken, voteToken }` GraphQL 类型。

### Changed
- `AppException` 增加可选 `error_message` / `upstream_response_string`（向后兼容）。
- PNVS 发送失败时透传阿里云上游 code/message（复刻 Rust `ServiceError` 诊断信息）。
- GraphQL 错误 `extensions` 复刻 Rust shape：`{service,url,error_kind,error_message,human_readable_message,upstream_response_string}`。

### 兼容性
- 纯增量：REST `/user/*` 与 submit/result GraphQL 行为不变。
- GraphQL schema 新增 5 个 mutation 字段，无破坏。

### 已知差异
- `login_email_password` 对"用户不存在"返回 `INCORRECT_PASSWORD`（防枚举），前端 `NOT_FOUND` 分支不触发——刻意保留。
- 老用户密码登录仍依赖 B-008 历史数据回填（未做）。
```

- [ ] **Step 3: 更新 REFACTOR_TODO**

在 `REFACTOR_TODO.md` 第二节"用户与认证"补一行：

```markdown
- ✅ GraphQL 登录 mutation 桥接（2026-05-30）：5 个登录 mutation 包装 UserService，前端 LoginBox 契约打通
```

- [ ] **Step 4: 提交**

```bash
git add docs/CHANGELOG.md REFACTOR_TODO.md
git commit -m "docs: record GraphQL login bridge in changelog + REFACTOR_TODO"
```

---

## 自查清单（写计划时已核对）

- **Spec 覆盖**：5 个 mutation（Task 5）、错误方案 B + 上游透传（Task 1/2/4）、LoginResult/VoterFE 类型（Task 3）、客户端 IP + 限流（Task 4/5/7）、三层测试（Task 4 单元 / Task 6-7 集成 / Task 5 契约）、文档 changelog（Task 8）——逐条对应。
- **已知差异**（§九）：`NOT_FOUND` 不触发、B-008 依赖——写进 Task 8 的 CHANGELOG"已知差异"。
- **类型一致**：`VoterFEType`/`LoginResult`/`login_result_from_pydantic`/`build_user_service`/`map_app_errors`/`_client_ip_from_info` 全程同名。
- **风险点**：Strawberry context 是否含 `request` —— `_client_ip_from_info` 用 `isinstance(ctx, dict)` 双分支兜底；集成测试用 `context_value={"request": ...}` 直接喂。若实跑发现 `info.context` 既非 dict 也无 `.request`，回退方案是给 `GraphQLRouter` 加 `context_getter`（Task 5 Step 4 处补 `GraphQLRouter(schema, context_getter=...)`，但默认应无需）。
