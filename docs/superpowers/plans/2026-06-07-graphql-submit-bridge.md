# GraphQL Submit Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让前端的 5 个投票提交 mutation(`submitCharacterVote(content: CharacterSubmitGQL!)` 等)与 5 个回读 query(`getSubmit*Vote(voteToken)`)在 Python 后端可用,前端零改动。

**Architecture:** 业务逻辑不动(`SubmitService`);新增 `src/api/graphql/resolvers/submit_bridge.py` 按前端契约命名 resolver;错误工具从 `resolvers/user.py` 下沉到 `src/api/graphql/errors.py` 共享;`validate_paper` 重写为「合法 JSON + 256KB」。设计依据:`docs/superpowers/specs/2026-06-07-graphql-submit-bridge-design.md`(以下称 spec)。

**Tech Stack:** FastAPI + Strawberry GraphQL 0.315 + SQLAlchemy async + pytest(`tests/conftest.py` 已设 `JWT_SECRET_KEY`,可直接签真 token)。

**重要背景(实现者必读):**
- 当前在分支 `feat/graphql-submit-bridge`。提交信息结尾加 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`。
- 旧字段(`resolvers/submit.py` 全部内容)**一字不动**——注意它里面 `SubmitService(db)` 传错了参(构造函数要 `SubmitDAO`),是已知的坏代码,**不要模仿也不要修**(Task 8 文档里记录)。
- 本机 `python -m pytest tests/unit -q` 中 `test_startup_db_check.py::test_lifespan_raises_on_db_failure` 因缺 lxml 必失败,**与你无关**,用 `--deselect tests/unit/test_startup_db_check.py::test_lifespan_raises_on_db_failure` 跳过。
- lint:`python -m flake8 <files> --max-line-length=88`(CI 只查 `src/`,但测试也请保持干净)。

---

### Task 1: `AppException` 增加可选 `human_readable_message`

**Files:**
- Modify: `src/common/exceptions.py`(`AppException.__init__`)
- Test: `tests/unit/test_exceptions_fields.py`(追加)

- [ ] **Step 1: 写失败测试**(追加到 `tests/unit/test_exceptions_fields.py` 末尾)

```python
def test_human_readable_message_roundtrip():
    exc = AppException("INVALID_CONTENT", details=422, human_readable_message="多个本命")
    assert exc.human_readable_message == "多个本命"


def test_human_readable_message_defaults_none():
    assert AppException("X").human_readable_message is None
```

(该文件已 import `AppException`;如没有,补 `from src.common.exceptions import AppException`。)

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/unit/test_exceptions_fields.py -q`
Expected: 2 failed — `TypeError: ... unexpected keyword argument 'human_readable_message'`

- [ ] **Step 3: 最小实现**(`src/common/exceptions.py`,改 `AppException.__init__`)

```python
    def __init__(
        self,
        message: str,
        details: Optional[Any] = None,
        error_message: Optional[str] = None,
        upstream_response_string: Optional[str] = None,
        human_readable_message: Optional[str] = None,
    ):
        self.message = message
        self.details = details
        self.error_message = error_message
        self.upstream_response_string = upstream_response_string
        # 面向终端用户的中文文案;None 时由 GraphQL 层按 error_kind 查表兜底
        self.human_readable_message = human_readable_message
        super().__init__(self.message)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/unit/test_exceptions_fields.py -q`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src/common/exceptions.py tests/unit/test_exceptions_fields.py
git commit -m "feat(exceptions): optional human_readable_message on AppException"
```

---

### Task 2: 错误工具下沉到 `src/api/graphql/errors.py`

**Files:**
- Create: `src/api/graphql/errors.py`
- Modify: `src/api/graphql/resolvers/user.py`(删除被搬走的定义,改 import)
- Modify: `tests/unit/test_graphql_error_mapping.py`(import 改指 errors.py;追加 1 个优先级测试)

- [ ] **Step 1: 写失败测试**(追加到 `tests/unit/test_graphql_error_mapping.py`)

```python
@pytest.mark.asyncio
async def test_exception_carried_human_message_beats_table():
    # 异常自带的 human_readable_message 优先于文案表(INCORRECT_PASSWORD 表内是"密码错误")
    with pytest.raises(GraphQLError) as ei:
        async with map_app_errors(service="submit-handler"):
            raise ValidationError(
                "INCORRECT_PASSWORD", details=400, human_readable_message="数量9不在范围内[1,8]"
            )
    assert ei.value.extensions["human_readable_message"] == "数量9不在范围内[1,8]"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/unit/test_graphql_error_mapping.py -q`
Expected: 新测试 FAIL(human_readable_message == "密码错误",因为现在只查表)

- [ ] **Step 3: 创建 `src/api/graphql/errors.py`**(内容 = 从 `resolvers/user.py` **整体搬走** `_HUMAN_READABLE_MESSAGES` / `_extensions` / `map_app_errors` / `_client_ip_from_info`,加优先级逻辑与 SUBMIT_LOCKED 文案)

```python
"""Shared GraphQL resolver plumbing: error mapping + client-IP extraction.

map_app_errors / _extensions 原住在 resolvers/user.py;submit 桥也需要同一套
错误契约,故下沉到此(单一出处,user.py 改为从这里 import)。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import strawberry
from fastapi import HTTPException
from graphql import GraphQLError

from src.apps.user.deps import get_client_ip
from src.common.exceptions import AppException

logger = logging.getLogger(__name__)

# error_kind → 面向用户的中文文案。前端部分错误处理直接展示
# extensions.human_readable_message。未列出的 kind 回退 None(前端走自己的兜底)。
# 只放安全、可直接展示给终端用户的措辞,不含任何敏感信息。
_HUMAN_READABLE_MESSAGES: dict[str, str] = {
    "INCORRECT_VERIFY_CODE": "验证码错误或已失效，请重新获取",
    "SMS_VERIFY_FAILED": "验证码校验失败，请重试",
    "INCORRECT_PASSWORD": "密码错误",
    "OLD_PASSWORD_REQUIRED": "请输入原密码",
    "EMAIL_IN_USE": "该邮箱已被使用",
    "PHONE_IN_USE": "该手机号已被使用",
    "USER_ALREADY_EXIST": "该账号已存在",
    "REQUEST_TOO_FREQUENT": "请求过于频繁，请稍后再试",
    "INVALID_PHONE": "手机号格式不正确",
    "INVALID_EMAIL": "邮箱格式不正确",
    "INVALID_TOKEN": "登录已失效，请重新登录",
    "USER_NOT_FOUND": "用户不存在",
    "SMS_SEND_FAILED": "短信发送失败，请稍后重试",
    "ALIYUN_NOT_CONFIGURED": "服务暂未配置，请联系管理员",
    "INTERNAL_ERROR": "服务器开小差了，请稍后重试",
    "SUBMIT_LOCKED": "提交处理中，请稍后再试",
}


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
    human_readable: Optional[str] = None,
) -> dict[str, object]:
    return {
        "service": service,
        "url": None,
        "error_kind": error_kind,
        "error_message": error_message,
        "human_readable_message": (
            human_readable
            if human_readable is not None
            else _HUMAN_READABLE_MESSAGES.get(error_kind)
        ),
        "upstream_response_string": upstream,
    }


@asynccontextmanager
async def map_app_errors(
    service: str, *, remap: Optional[dict[str, str]] = None
) -> AsyncIterator[None]:
    """Translate service-layer errors into a Rust-aligned GraphQLError.

    *remap* lets a resolver rename a service error_kind to the one the
    frontend expects (e.g. the service's generic ``USER_ALREADY_EXIST`` →
    ``EMAIL_IN_USE`` / ``PHONE_IN_USE`` for the update mutations).
    """
    try:
        yield
    except AppException as exc:
        kind = (remap or {}).get(exc.message, exc.message)
        raise GraphQLError(
            "Error",
            extensions=_extensions(
                service,
                kind,
                error_message=getattr(exc, "error_message", None),
                upstream=getattr(exc, "upstream_response_string", None),
                human_readable=getattr(exc, "human_readable_message", None),
            ),
        ) from exc
    except HTTPException as exc:
        raise GraphQLError(
            "Error", extensions=_extensions(service, str(exc.detail))
        ) from exc
    except GraphQLError:
        raise  # already-mapped error — pass through unchanged
    except Exception as exc:
        # 真实异常进日志(含堆栈),响应只暴露稳定的 INTERNAL_ERROR,
        # 不向调用方透出内部细节(SDK/SQL/类名等)。
        logger.exception("Unhandled error in GraphQL resolver (service=%s)", service)
        raise GraphQLError(
            "Error",
            extensions=_extensions(service, "INTERNAL_ERROR", error_message=None),
        ) from exc
```

- [ ] **Step 4: 改 `src/api/graphql/resolvers/user.py`**
  1. 删除其中的 `_HUMAN_READABLE_MESSAGES`、`_extensions`、`map_app_errors`、`_client_ip_from_info` 四个定义(连同它们独占的 import:`asynccontextmanager`、`AsyncIterator`、`HTTPException`、`GraphQLError`、`get_client_ip`——删前 grep 确认 user.py 其余代码不再用)。
  2. 顶部加:

```python
from src.api.graphql.errors import _client_ip_from_info, map_app_errors
```

- [ ] **Step 5: 改 `tests/unit/test_graphql_error_mapping.py` 的 import**

```python
from src.api.graphql.errors import _client_ip_from_info, map_app_errors
```

(原 `from src.api.graphql.resolvers.user import ...` 删除;其余 8 个既有断言**一个不改**。)

- [ ] **Step 6: 全量回归**

Run: `python -m pytest tests/unit/test_graphql_error_mapping.py tests/unit/test_user_account_mutations.py tests/unit/test_graphql_login_types.py -q`
Expected: all passed(含新优先级测试)

Run: `python -m flake8 src/api/graphql/errors.py src/api/graphql/resolvers/user.py --max-line-length=88`
Expected: 无输出

- [ ] **Step 7: Commit**

```bash
git add src/api/graphql/errors.py src/api/graphql/resolvers/user.py tests/unit/test_graphql_error_mapping.py
git commit -m "refactor(graphql): sink error mapping into shared errors.py + human message priority"
```

---

### Task 3: 重写 `validate_paper`(合法 JSON + 256KB)

**Files:**
- Modify: `src/apps/submit/service.py`(仅 `SubmitValidator.validate_paper` 函数体)
- Modify: `tests/unit/test_submit_validator.py`(paper 段整组重写)

- [ ] **Step 1: 重写 paper 测试段**(替换 `tests/unit/test_submit_validator.py` 中 `# ── paper ──` 注释到 dojin 段之前的全部 5 个测试)

```python
# ── paper ──────────────────────────────────────────────────────────────
# papers_json 是不透明业务数据(前端真实载荷为嵌套对象,统计侧不读原始表),
# 只验「合法 JSON + UTF-8 ≤ 256KB」。旧的"非空列表+整数id"校验是按想象格式写的,
# 会拒掉真实前端载荷,已按 spec 2026-06-07 移除。


def test_validate_paper_accepts_real_frontend_payload():
    # 前端 Questionnaire.vue 实际提交的嵌套结构(精简版)
    payload = json.dumps({
        "mainQuestionnaire": {
            "requiredQuestionnaire": {
                "id": 11,
                "answers": [{"id": 11011, "options": [1, 2], "input": ""}],
            },
            "optionalQuestionnaire1": {"id": 12, "answers": []},
        },
        "extraQuestionnaire": {"exQuestionnaire1": {"id": 21, "answers": []}},
    })
    data = PaperSubmitRest(papers_json=payload, meta=META)
    assert v.validate_paper(data) is data


def test_validate_paper_accepts_any_valid_json_shape():
    # 列表、对象、甚至标量都放行——结构不归后端管
    for payload in ['[{"id": 1}]', "{}", '"just a string"']:
        assert v.validate_paper(
            PaperSubmitRest(papers_json=payload, meta=META)
        ) is not None


def test_validate_paper_invalid_json():
    with pytest.raises(ValueError):
        v.validate_paper(PaperSubmitRest(papers_json="{not json", meta=META))


def test_validate_paper_oversize_rejected():
    big = json.dumps({"x": "a" * (256 * 1024)})  # 编码后必然 > 256KB
    with pytest.raises(ValueError):
        v.validate_paper(PaperSubmitRest(papers_json=big, meta=META))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/unit/test_submit_validator.py -q`
Expected: `test_validate_paper_accepts_real_frontend_payload` 与 `accepts_any_valid_json_shape` FAIL("papers_json 必须为非空列表");oversize 测试 FAIL(旧实现不查大小,且该 payload 是对象也会先被列表检查拒掉——总之有失败即可)

- [ ] **Step 3: 重写实现**(`src/apps/submit/service.py`,整体替换 `validate_paper`)

```python
    # papers_json 上限:防滥用存储。前端真实问卷 ≈ 几 KB,256KB 给足余量。
    PAPERS_JSON_MAX_BYTES = 256 * 1024

    def validate_paper(self, data: PaperSubmitRest) -> PaperSubmitRest:
        """Validate paper submit data.

        papers_json 是不透明业务数据:前端把整棵问卷答案树序列化成一个 JSON
        字符串,结构随问卷内容逐年变化,统计侧也不读这张原始表——所以这里只把
        关「是合法 JSON」+「大小上限」,不校验内部结构(对齐旧 Rust 的透传语义,
        外加大小护栏;详见 docs/superpowers/specs/2026-06-07-graphql-submit-bridge-design.md §5)。
        """
        if len(data.papers_json.encode("utf-8")) > self.PAPERS_JSON_MAX_BYTES:
            raise ValueError("问卷数据过大")
        try:
            json.loads(data.papers_json)
        except (json.JSONDecodeError, ValueError):
            raise ValueError("papers_json 不是合法 JSON")
        return data
```

(`PAPERS_JSON_MAX_BYTES` 作为 `SubmitValidator` 的类属性,放在 `validate_paper` 上方。)

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/unit/test_submit_validator.py -q`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src/apps/submit/service.py tests/unit/test_submit_validator.py
git commit -m "fix(submit): validate_paper accepts real frontend payload (JSON + 256KB only)"
```

---

### Task 4: `submit_bridge.py` 骨架 + 第一个 mutation `submitCharacterVote`

**Files:**
- Create: `src/api/graphql/resolvers/submit_bridge.py`
- Modify: `src/api/graphql/schema.py`(Mutation 多继承)
- Test: `tests/unit/test_submit_bridge_resolvers.py`(新)

- [ ] **Step 1: 写失败测试**(新建 `tests/unit/test_submit_bridge_resolvers.py`)

```python
"""Submit 桥 resolver 单测:token→user_id、服务端造 meta、错误映射。

redis / db / service 全部 monkeypatch 假件;vote token 用 conftest 的测试密钥真签
(窗口 2026-01-01..2026-12-31 覆盖当前日期,无需 freezegun)。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from graphql import GraphQLError

import src.api.graphql.resolvers.submit_bridge as bridge
from src.api.graphql.types import CharacterSubmitInput
from src.common.security.jwt import create_vote_token

VOTE_START = datetime(2026, 1, 1, tzinfo=UTC)
VOTE_END = datetime(2026, 12, 31, tzinfo=UTC)


def _token(user_id: str = "user-7") -> str:
    return create_vote_token(user_id, VOTE_START, VOTE_END)


class _FakeRedis:
    def __init__(self):
        self.store = {}

    async def set(self, key, value, nx=False, px=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, key):
        self.store.pop(key, None)

    async def incr(self, key):
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    async def expire(self, key, ttl):
        return True


class _FakeService:
    """记录收到的 REST body;可配置抛 ValueError。"""

    def __init__(self, raise_value_error: str | None = None):
        self.bodies = []
        self._raise = raise_value_error

    async def submit_character(self, body):
        if self._raise:
            raise ValueError(self._raise)
        self.bodies.append(body)
        return 1


class _Info:
    context = {"request": None}  # _client_ip_from_info(None request) → ""


@pytest.fixture
def fake_env(monkeypatch):
    """统一替换 redis / db / Service;返回可注入的 fake service 容器。"""
    holder = {"service": _FakeService()}
    redis = _FakeRedis()

    async def fake_get_redis_client():
        return redis

    async def fake_get_db_session():
        yield None

    monkeypatch.setattr(bridge, "get_redis_client", fake_get_redis_client)
    monkeypatch.setattr(bridge, "get_db_session", fake_get_db_session)
    monkeypatch.setattr(bridge, "SubmitDAO", lambda db: db)
    monkeypatch.setattr(bridge, "SubmitService", lambda dao: holder["service"])
    return holder


def _character_content(token: str) -> "bridge.CharacterSubmitGQL":
    return bridge.CharacterSubmitGQL(
        vote_token=token,
        characters=[CharacterSubmitInput(id="reimu", first=True, reason="好")],
    )


@pytest.mark.asyncio
async def test_submit_character_uses_token_user_id_as_vote_id(fake_env):
    out = await bridge.SubmitBridgeMutation().submit_character_vote(
        info=_Info(), content=_character_content(_token("user-7"))
    )
    assert out is True
    body = fake_env["service"].bodies[0]
    assert body.meta.vote_id == "user-7"          # 来自 token,非客户端
    assert body.meta.created_at is not None       # 服务端生成
    assert body.characters[0].id == "reimu"


@pytest.mark.asyncio
async def test_submit_character_bad_token_maps_to_invalid_token(fake_env):
    with pytest.raises(GraphQLError) as ei:
        await bridge.SubmitBridgeMutation().submit_character_vote(
            info=_Info(), content=_character_content("not.a.token")
        )
    ext = ei.value.extensions
    assert ext["error_kind"] == "INVALID_TOKEN"
    assert ext["human_readable_message"] == "登录已失效，请重新登录"


@pytest.mark.asyncio
async def test_submit_character_value_error_maps_to_invalid_content(fake_env):
    fake_env["service"] = _FakeService(raise_value_error="多个本命")
    with pytest.raises(GraphQLError) as ei:
        await bridge.SubmitBridgeMutation().submit_character_vote(
            info=_Info(), content=_character_content(_token())
        )
    ext = ei.value.extensions
    assert ext["error_kind"] == "INVALID_CONTENT"
    assert ext["human_readable_message"] == "多个本命"


@pytest.mark.asyncio
async def test_submit_lock_conflict_maps_to_submit_locked(fake_env, monkeypatch):
    # 预占锁:同 user 再提交 → SUBMIT_LOCKED
    redis = await bridge.get_redis_client()
    await redis.set("lock-submit-user-7", "someone-else", nx=True, px=10_000)
    with pytest.raises(GraphQLError) as ei:
        await bridge.SubmitBridgeMutation().submit_character_vote(
            info=_Info(), content=_character_content(_token("user-7"))
        )
    assert ei.value.extensions["error_kind"] == "SUBMIT_LOCKED"
    assert ei.value.extensions["human_readable_message"] == "提交处理中，请稍后再试"
```

注意:`_client_ip_from_info` 对 `{"request": None}` 返回 `""`,meta.user_ip 落 `"<unknown>"`(见 Step 3 `_server_meta`),无需断言 IP。

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/unit/test_submit_bridge_resolvers.py -q`
Expected: collection error — `module 'submit_bridge' not found`

- [ ] **Step 3: 创建 `src/api/graphql/resolvers/submit_bridge.py`**

```python
"""GraphQL submit 桥 — 前端(旧 Rust gateway)契约的投票提交/回读。

业务逻辑全在 SubmitService;本模块只做:
  voteToken → user_id(即 vote_id)→ 服务端造 meta → service。
契约与决策见 docs/superpowers/specs/2026-06-07-graphql-submit-bridge-design.md。
旧自创字段(resolvers/submit.py)按用户决策原样保留,与本模块并存。
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from typing import AsyncIterator, Optional

import strawberry

from src.api.graphql.errors import _client_ip_from_info, map_app_errors
from src.api.graphql.types import (
    CharacterSubmit,
    CharacterSubmitInput,
    CPSubmit,
    CPSubmitInput,
    DojinSubmit,
    MusicSubmit,
    MusicSubmitInput,
    pydantic_to_graphql_characters,
    pydantic_to_graphql_cps,
    pydantic_to_graphql_dojins,
    pydantic_to_graphql_musics,
)
from src.apps.submit.dao import SubmitDAO
from src.apps.submit.schemas import CharacterSubmit as CharacterSubmitPydantic
from src.apps.submit.schemas import CharacterSubmitRest
from src.apps.submit.schemas import CPSubmit as CPSubmitPydantic
from src.apps.submit.schemas import CPSubmitRest
from src.apps.submit.schemas import DojinSubmit as DojinSubmitPydantic
from src.apps.submit.schemas import DojinSubmitRest
from src.apps.submit.schemas import MusicSubmit as MusicSubmitPydantic
from src.apps.submit.schemas import MusicSubmitRest, PaperSubmitRest, SubmitMetadata
from src.apps.submit.service import SubmitService
from src.common.database import get_db_session
from src.common.exceptions import RateLimitError, UnauthorizedError, ValidationError
from src.common.middleware.rate_limit import get_redis_client, rate_limit
from src.common.security import JWTValidationError, decode_vote_token

_SERVICE = "submit-handler"  # extensions.service,对齐旧 Rust 服务名


# ── GraphQL 类型(名字以前端 gql 文档为准,大小写精确) ────────────────


@strawberry.enum
class DojinType(Enum):
    MUSIC = "MUSIC"
    VIDEO = "VIDEO"
    DRAWING = "DRAWING"
    SOFTWARE = "SOFTWARE"
    ARTICLE = "ARTICLE"
    CRAFT = "CRAFT"
    OTHER = "OTHER"


@strawberry.input(name="DojinSubmitItemGQL")
class DojinSubmitItemGQL:
    title: str
    author: str
    url: str
    dojin_type: DojinType
    reason: str
    image_url: Optional[str] = None


@strawberry.input(name="CharacterSubmitGQL")
class CharacterSubmitGQL:
    vote_token: str
    characters: list[CharacterSubmitInput]


@strawberry.input(name="MusicSubmitGQL")
class MusicSubmitGQL:
    vote_token: str
    musics: list[MusicSubmitInput]  # 提交字段是复数;回读结果字段是单数 music(旧契约怪癖)


@strawberry.input(name="CPSubmitGQL")
class CPSubmitGQL:
    vote_token: str
    cps: list[CPSubmitInput]


@strawberry.input(name="PaperSubmitGQL")
class PaperSubmitGQL:
    vote_token: str
    paper_json: str


@strawberry.input(name="DojinSubmitGQL")
class DojinSubmitGQL:
    vote_token: str
    dojins: list[DojinSubmitItemGQL]


@strawberry.type
class CharacterSubmitRestQuery:
    characters: list[CharacterSubmit]


@strawberry.type
class MusicSubmitRestQuery:
    music: list[MusicSubmit]


@strawberry.type
class CPSubmitRestQuery:
    cps: list[CPSubmit]


@strawberry.type
class DojinSubmitRestQuery:
    dojins: list[DojinSubmit]


@strawberry.type
class PaperSubmitRestQuery:
    papers_json: str


# ── 共享 helpers ──────────────────────────────────────────────────────


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _vote_user_id(vote_token: str) -> str:
    """voteToken → user_id(即 vote_id)。缺失/伪造/过期(含窗口外)统一 INVALID_TOKEN。"""
    if not vote_token:
        raise UnauthorizedError("INVALID_TOKEN", details=401)
    try:
        return decode_vote_token(vote_token).user_id
    except JWTValidationError as exc:
        raise UnauthorizedError("INVALID_TOKEN", details=401) from exc


def _server_meta(user_id: str, info: "strawberry.Info") -> SubmitMetadata:
    """meta 由服务端生成:vote_id 取自 token,时间与 IP 不信任客户端。"""
    return SubmitMetadata(
        vote_id=user_id,
        created_at=_utcnow(),
        user_ip=_client_ip_from_info(info) or "<unknown>",
    )


@asynccontextmanager
async def _submit_lock(user_id: str) -> AsyncIterator[None]:
    """同一用户的并发提交互斥。冲突抛 AppException(SUBMIT_LOCKED),
    走 map_app_errors 出正确 extensions(旧 resolver 抛裸 Exception 会被全局
    格式化器脱敏,这里刻意不复用)。"""
    redis_client = await get_redis_client()
    lock_key = f"lock-submit-{user_id}"
    lock_value = str(uuid.uuid4())
    acquired = await redis_client.set(lock_key, lock_value, nx=True, px=10_000)
    if not acquired:
        raise RateLimitError("SUBMIT_LOCKED", details=429)
    try:
        yield
    finally:
        current = await redis_client.get(lock_key)
        if current == lock_value:
            await redis_client.delete(lock_key)


async def _run_submit(body, service_method_name: str) -> bool:
    """统一的 service 调用:ValueError → INVALID_CONTENT(中文原文透传)。"""
    async for db in get_db_session():
        service = SubmitService(SubmitDAO(db))
        try:
            await getattr(service, service_method_name)(body)
        except ValueError as exc:
            raise ValidationError(
                "INVALID_CONTENT", details=422, human_readable_message=str(exc)
            ) from exc
        return True
    raise RuntimeError("unreachable")  # pragma: no cover


# ── Mutations ─────────────────────────────────────────────────────────


@strawberry.type
class SubmitBridgeMutation:
    @strawberry.mutation
    async def submit_character_vote(
        self, info: strawberry.Info, content: CharacterSubmitGQL
    ) -> bool:
        async with map_app_errors(service=_SERVICE):
            user_id = _vote_user_id(content.vote_token)
            await rate_limit(user_id, await get_redis_client())
            async with _submit_lock(user_id):
                body = CharacterSubmitRest(
                    characters=[
                        CharacterSubmitPydantic(id=c.id, reason=c.reason, first=c.first)
                        for c in content.characters
                    ],
                    meta=_server_meta(user_id, info),
                )
                return await _run_submit(body, "submit_character")
        raise RuntimeError("unreachable")  # pragma: no cover
```

- [ ] **Step 4: 接线 `src/api/graphql/schema.py`**(Mutation 多继承;Query 在 Task 6 接)

```python
from .resolvers.submit_bridge import SubmitBridgeMutation
# ...
class Mutation(SubmitMutation, UserMutation, SubmitBridgeMutation):
```

(保持现有 docstring/注释结构不变,只加继承与 import。)

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/unit/test_submit_bridge_resolvers.py -q`
Expected: 4 passed

Run: `python -m pytest tests/unit -q --deselect tests/unit/test_startup_db_check.py::test_lifespan_raises_on_db_failure`
Expected: all passed(确认 schema 接线没炸别人)

- [ ] **Step 6: Commit**

```bash
git add src/api/graphql/resolvers/submit_bridge.py src/api/graphql/schema.py tests/unit/test_submit_bridge_resolvers.py
git commit -m "feat(graphql): submit bridge skeleton + submitCharacterVote"
```

---

### Task 5: 其余 4 个 mutation(music / cp / paper / dojin)

**Files:**
- Modify: `src/api/graphql/resolvers/submit_bridge.py`(SubmitBridgeMutation 内追加)
- Modify: `tests/unit/test_submit_bridge_resolvers.py`(追加)

- [ ] **Step 1: 写失败测试**(追加;`_FakeService` 增加 4 个方法)

```python
# _FakeService 追加(与 submit_character 同模式):
    async def submit_music(self, body):
        if self._raise:
            raise ValueError(self._raise)
        self.bodies.append(body)
        return 1

    async def submit_cp(self, body):
        if self._raise:
            raise ValueError(self._raise)
        self.bodies.append(body)
        return 1

    async def submit_paper(self, body):
        if self._raise:
            raise ValueError(self._raise)
        self.bodies.append(body)
        return 1

    async def submit_dojin(self, body):
        if self._raise:
            raise ValueError(self._raise)
        self.bodies.append(body)
        return 1
```

```python
@pytest.mark.asyncio
async def test_submit_music_plural_input_singular_rest_field(fake_env):
    from src.api.graphql.types import MusicSubmitInput

    out = await bridge.SubmitBridgeMutation().submit_music_vote(
        info=_Info(),
        content=bridge.MusicSubmitGQL(
            vote_token=_token("user-m"),
            musics=[MusicSubmitInput(id="夜雀", first=True)],
        ),
    )
    assert out is True
    body = fake_env["service"].bodies[0]
    assert body.music[0].id == "夜雀"      # REST 模型字段是单数 music
    assert body.meta.vote_id == "user-m"


@pytest.mark.asyncio
async def test_submit_cp_maps_camel_fields(fake_env):
    from src.api.graphql.types import CPSubmitInput

    out = await bridge.SubmitBridgeMutation().submit_cp_vote(
        info=_Info(),
        content=bridge.CPSubmitGQL(
            vote_token=_token(),
            cps=[CPSubmitInput(id_a="reimu", id_b="marisa", active="reimu", first=True)],
        ),
    )
    assert out is True
    body = fake_env["service"].bodies[0]
    assert (body.cps[0].id_a, body.cps[0].id_b) == ("reimu", "marisa")


@pytest.mark.asyncio
async def test_submit_paper_passes_raw_json(fake_env):
    raw = '{"mainQuestionnaire": {"requiredQuestionnaire": {"id": 11, "answers": []}}}'
    out = await bridge.SubmitBridgeMutation().submit_paper_vote(
        info=_Info(),
        content=bridge.PaperSubmitGQL(vote_token=_token(), paper_json=raw),
    )
    assert out is True
    assert fake_env["service"].bodies[0].papers_json == raw


@pytest.mark.asyncio
async def test_submit_dojin_stores_enum_name(fake_env):
    out = await bridge.SubmitBridgeMutation().submit_dojin(
        info=_Info(),
        content=bridge.DojinSubmitGQL(
            vote_token=_token(),
            dojins=[
                bridge.DojinSubmitItemGQL(
                    title="t", author="a", url="https://x", reason="r",
                    dojin_type=bridge.DojinType.MUSIC,
                )
            ],
        ),
    )
    assert out is True
    assert fake_env["service"].bodies[0].dojins[0].dojin_type == "MUSIC"  # 存枚举名
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/unit/test_submit_bridge_resolvers.py -q`
Expected: 新 4 例 FAIL — `AttributeError: ... has no attribute 'submit_music_vote'` 等

- [ ] **Step 3: 实现 4 个 resolver**(追加到 `SubmitBridgeMutation`)

```python
    @strawberry.mutation
    async def submit_music_vote(
        self, info: strawberry.Info, content: MusicSubmitGQL
    ) -> bool:
        async with map_app_errors(service=_SERVICE):
            user_id = _vote_user_id(content.vote_token)
            await rate_limit(user_id, await get_redis_client())
            async with _submit_lock(user_id):
                body = MusicSubmitRest(
                    music=[  # REST 模型字段是单数 music(入参是复数 musics)
                        MusicSubmitPydantic(id=m.id, reason=m.reason, first=m.first)
                        for m in content.musics
                    ],
                    meta=_server_meta(user_id, info),
                )
                return await _run_submit(body, "submit_music")
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.mutation(name="submitCPVote")
    async def submit_cp_vote(
        self, info: strawberry.Info, content: CPSubmitGQL
    ) -> bool:
        async with map_app_errors(service=_SERVICE):
            user_id = _vote_user_id(content.vote_token)
            await rate_limit(user_id, await get_redis_client())
            async with _submit_lock(user_id):
                body = CPSubmitRest(
                    cps=[
                        CPSubmitPydantic(
                            id_a=c.id_a, id_b=c.id_b, id_c=c.id_c,
                            active=c.active, first=c.first, reason=c.reason,
                        )
                        for c in content.cps
                    ],
                    meta=_server_meta(user_id, info),
                )
                return await _run_submit(body, "submit_cp")
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.mutation
    async def submit_paper_vote(
        self, info: strawberry.Info, content: PaperSubmitGQL
    ) -> bool:
        async with map_app_errors(service=_SERVICE):
            user_id = _vote_user_id(content.vote_token)
            await rate_limit(user_id, await get_redis_client())
            async with _submit_lock(user_id):
                body = PaperSubmitRest(
                    papers_json=content.paper_json,
                    meta=_server_meta(user_id, info),
                )
                return await _run_submit(body, "submit_paper")
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.mutation
    async def submit_dojin(
        self, info: strawberry.Info, content: DojinSubmitGQL
    ) -> bool:
        async with map_app_errors(service=_SERVICE):
            user_id = _vote_user_id(content.vote_token)
            await rate_limit(user_id, await get_redis_client())
            async with _submit_lock(user_id):
                body = DojinSubmitRest(
                    dojins=[
                        DojinSubmitPydantic(
                            dojin_type=d.dojin_type.value,  # 入库存枚举名("MUSIC")
                            url=d.url, title=d.title, author=d.author,
                            reason=d.reason, image_url=d.image_url,
                        )
                        for d in content.dojins
                    ],
                    meta=_server_meta(user_id, info),
                )
                return await _run_submit(body, "submit_dojin")
        raise RuntimeError("unreachable")  # pragma: no cover
```

**坑位提示:** `submit_cp_vote` 必须用 `@strawberry.mutation(name="submitCPVote")`——strawberry 自动驼峰会把 `submit_cp_vote` 变成 `submitCpVote`(P 小写),与前端 `submitCPVote` 不符。其余 4 个自动驼峰即正确(`submit_character_vote`→`submitCharacterVote`、`submit_dojin`→`submitDojin` 等),无需 name=。

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/unit/test_submit_bridge_resolvers.py -q`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src/api/graphql/resolvers/submit_bridge.py tests/unit/test_submit_bridge_resolvers.py
git commit -m "feat(graphql): submitMusicVote/submitCPVote/submitPaperVote/submitDojin"
```

---

### Task 6: 5 个回读 query + `SubmitBridgeQuery` 接线

**Files:**
- Modify: `src/api/graphql/resolvers/submit_bridge.py`(追加 SubmitBridgeQuery)
- Modify: `src/api/graphql/schema.py`(Query 多继承)
- Modify: `tests/unit/test_submit_bridge_resolvers.py`(追加)

- [ ] **Step 1: 写失败测试**(追加;`_FakeService` 增加 get 方法)

```python
# _FakeService 追加:
    async def get_character_submit(self, vote_id):
        from src.apps.submit.schemas import CharacterSubmitRest, SubmitMetadata
        self.get_calls = getattr(self, "get_calls", [])
        self.get_calls.append(vote_id)
        return CharacterSubmitRest(characters=[], meta=SubmitMetadata())

    async def get_paper_submit(self, vote_id):
        from src.apps.submit.schemas import PaperSubmitRest, SubmitMetadata
        return PaperSubmitRest(papers_json="{}", meta=SubmitMetadata())
```

```python
@pytest.mark.asyncio
async def test_get_character_query_decodes_token_and_returns_empty(fake_env):
    out = await bridge.SubmitBridgeQuery().get_submit_character_vote(
        info=_Info(), vote_token=_token("user-q")
    )
    assert out.characters == []
    assert fake_env["service"].get_calls == ["user-q"]


@pytest.mark.asyncio
async def test_get_paper_query_returns_empty_object_string(fake_env):
    out = await bridge.SubmitBridgeQuery().get_submit_paper_vote(
        info=_Info(), vote_token=_token()
    )
    assert out.papers_json == "{}"   # 空结果回 "{}",不回 null(spec §3.2)


@pytest.mark.asyncio
async def test_get_query_bad_token_maps_to_invalid_token(fake_env):
    with pytest.raises(GraphQLError) as ei:
        await bridge.SubmitBridgeQuery().get_submit_character_vote(
            info=_Info(), vote_token="garbage"
        )
    assert ei.value.extensions["error_kind"] == "INVALID_TOKEN"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/unit/test_submit_bridge_resolvers.py -q`
Expected: 新 3 例 FAIL — `module ... has no attribute 'SubmitBridgeQuery'`

- [ ] **Step 3: 实现 `SubmitBridgeQuery`**(追加到 submit_bridge.py 末尾)

```python
# ── Queries(凭 voteToken 回读;空结果=空数组/"{}") ──────────────────


@strawberry.type
class SubmitBridgeQuery:
    @strawberry.field
    async def get_submit_character_vote(
        self, info: strawberry.Info, vote_token: str
    ) -> CharacterSubmitRestQuery:
        async with map_app_errors(service=_SERVICE):
            user_id = _vote_user_id(vote_token)
            async for db in get_db_session():
                data = await SubmitService(SubmitDAO(db)).get_character_submit(user_id)
                return CharacterSubmitRestQuery(
                    characters=pydantic_to_graphql_characters(data.characters)
                )
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.field
    async def get_submit_music_vote(
        self, info: strawberry.Info, vote_token: str
    ) -> MusicSubmitRestQuery:
        async with map_app_errors(service=_SERVICE):
            user_id = _vote_user_id(vote_token)
            async for db in get_db_session():
                data = await SubmitService(SubmitDAO(db)).get_music_submit(user_id)
                return MusicSubmitRestQuery(
                    music=pydantic_to_graphql_musics(data.music)
                )
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.field(name="getSubmitCPVote")
    async def get_submit_cp_vote(
        self, info: strawberry.Info, vote_token: str
    ) -> CPSubmitRestQuery:
        async with map_app_errors(service=_SERVICE):
            user_id = _vote_user_id(vote_token)
            async for db in get_db_session():
                data = await SubmitService(SubmitDAO(db)).get_cp_submit(user_id)
                return CPSubmitRestQuery(cps=pydantic_to_graphql_cps(data.cps))
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.field
    async def get_submit_dojin_vote(
        self, info: strawberry.Info, vote_token: str
    ) -> DojinSubmitRestQuery:
        async with map_app_errors(service=_SERVICE):
            user_id = _vote_user_id(vote_token)
            async for db in get_db_session():
                data = await SubmitService(SubmitDAO(db)).get_dojin_submit(user_id)
                return DojinSubmitRestQuery(
                    dojins=pydantic_to_graphql_dojins(data.dojins)
                )
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.field
    async def get_submit_paper_vote(
        self, info: strawberry.Info, vote_token: str
    ) -> PaperSubmitRestQuery:
        async with map_app_errors(service=_SERVICE):
            user_id = _vote_user_id(vote_token)
            async for db in get_db_session():
                data = await SubmitService(SubmitDAO(db)).get_paper_submit(user_id)
                # 空结果回 "{}"(service 现行为),不转 null —— spec §3.2
                return PaperSubmitRestQuery(papers_json=data.papers_json)
        raise RuntimeError("unreachable")  # pragma: no cover
```

**坑位提示:** `get_submit_cp_vote` 同样需要 `name="getSubmitCPVote"`(CP 全大写)。

- [ ] **Step 4: 接线 `src/api/graphql/schema.py`**

```python
from .resolvers.submit_bridge import SubmitBridgeMutation, SubmitBridgeQuery
# ...
class Query(SubmitQuery, ResultQuery, SubmitBridgeQuery):
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/unit/test_submit_bridge_resolvers.py -q`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add src/api/graphql/resolvers/submit_bridge.py src/api/graphql/schema.py tests/unit/test_submit_bridge_resolvers.py
git commit -m "feat(graphql): getSubmit*Vote queries (voteToken-authenticated read-back)"
```

---

### Task 7: SDL 全量契约回归测试

**Files:**
- Create: `tests/unit/test_submit_bridge_schema.py`

- [ ] **Step 1: 写测试**(新建;字段签名漂移即失败)

```python
"""Submit 桥 SDL 契约回归:10 个字段签名 + 枚举 + 顶层输入字段逐一钉死。

前端 gql 文档按名字严格校验(变量类型名、字段名、参数名),任何漂移都等于
线上 'Cannot query field'。签名来源:spec §3(已逐一与前端文档核对)。
"""

from __future__ import annotations

import pytest

from src.api.graphql.schema import schema

EXPECTED_SIGNATURES = [
    # mutations(返回裸 Boolean)
    "submitCharacterVote(content: CharacterSubmitGQL!): Boolean!",
    "submitMusicVote(content: MusicSubmitGQL!): Boolean!",
    "submitCPVote(content: CPSubmitGQL!): Boolean!",
    "submitPaperVote(content: PaperSubmitGQL!): Boolean!",
    "submitDojin(content: DojinSubmitGQL!): Boolean!",
    # queries
    "getSubmitCharacterVote(voteToken: String!): CharacterSubmitRestQuery!",
    "getSubmitMusicVote(voteToken: String!): MusicSubmitRestQuery!",
    "getSubmitCPVote(voteToken: String!): CPSubmitRestQuery!",
    "getSubmitDojinVote(voteToken: String!): DojinSubmitRestQuery!",
    "getSubmitPaperVote(voteToken: String!): PaperSubmitRestQuery!",
    # 顶层输入类型字段(camelCase + 复数 musics 怪癖)
    "input CharacterSubmitGQL {\n  voteToken: String!\n  characters: [CharacterSubmitInput!]!\n}",
    "input MusicSubmitGQL {\n  voteToken: String!\n  musics: [MusicSubmitInput!]!\n}",
    "input CPSubmitGQL {\n  voteToken: String!\n  cps: [CPSubmitInput!]!\n}",
    "input PaperSubmitGQL {\n  voteToken: String!\n  paperJson: String!\n}",
    "input DojinSubmitGQL {\n  voteToken: String!\n  dojins: [DojinSubmitItemGQL!]!\n}",
    # 回读结果字段(music 单数怪癖 + papersJson)
    "type MusicSubmitRestQuery {\n  music: [MusicSubmit!]!\n}",
    "type PaperSubmitRestQuery {\n  papersJson: String!\n}",
]

DOJIN_ENUM_VALUES = ["MUSIC", "VIDEO", "DRAWING", "SOFTWARE", "ARTICLE", "CRAFT", "OTHER"]


@pytest.mark.parametrize("signature", EXPECTED_SIGNATURES)
def test_submit_bridge_contract_pinned(signature: str) -> None:
    sdl = schema.as_str()
    assert signature in sdl, f"missing or drifted: {signature}"


def test_dojin_type_enum_values() -> None:
    sdl = schema.as_str()
    for value in DOJIN_ENUM_VALUES:
        assert value in sdl.split("enum DojinType {")[1].split("}")[0]
```

- [ ] **Step 2: 跑测试**

Run: `python -m pytest tests/unit/test_submit_bridge_schema.py -q`
Expected: all passed。**若有 FAIL:以测试内签名为准修 submit_bridge.py(签名来自前端文档,不许反向改测试)。** 唯一例外:SDL 的换行/排版与断言不符时(strawberry 版本差异),先 `python -c "from src.api.graphql.schema import schema; print(schema.as_str())"` 目视确认**语义**一致,再把断言调成实际排版。

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_submit_bridge_schema.py
git commit -m "test(graphql): pin submit bridge SDL contract (10 fields + enum)"
```

---

### Task 8: 文档 + 全量验证 + PR

**Files:**
- Modify: `docs/CHANGELOG.md`(顶部新条目)
- Modify: `docs/migration/graphql-submit-bridge.md`(状态更新)

- [ ] **Step 1: CHANGELOG 顶部插入**(`# thvote-be-re CHANGELOG` 头部引用块之后、第一个 `## [...]` 之前;并把头部「最后更新」行换成本条摘要)

```markdown
## [2026-06-07] GraphQL Submit 桥接(投票提交/回读适配前端契约)

### Added
- `src/api/graphql/resolvers/submit_bridge.py`:按前端(旧 Rust gateway)契约新增 5 个 mutation(`submitCharacterVote/submitMusicVote/submitCPVote/submitPaperVote/submitDojin`,入参 `content: …GQL!`,返回 `Boolean`)与 5 个回读 query(`getSubmit*Vote(voteToken)`)。resolver 内 `voteToken`→`user_id`(即 vote_id),meta(时间/IP)服务端生成,不信任客户端;限流与提交锁按 token 身份。`DojinType` GraphQL 枚举(入库存枚举名)。
- `src/api/graphql/errors.py`:错误映射工具从 resolvers/user.py 下沉共享;`_extensions` 支持异常自带 `human_readable_message` 优先于文案表;文案表新增 `SUBMIT_LOCKED`。
- `AppException` 增可选 `human_readable_message`(向后兼容)。

### Fixed
- `validate_paper` 重写为「合法 JSON + UTF-8 ≤256KB」:旧实现要求"非空列表+整数 id",是按想象格式写的,会拒掉前端真实载荷(嵌套对象);统计侧不读原始 papers_json,无下游结构依赖。REST 路径同步受益。

### 兼容性
- 旧自创 GraphQL 字段(`submitCharacter(input:)` ×5、`getCharacterSubmit(voteId)` ×7)按决策**原样保留**,与新桥并存;注意旧 resolver 存在 `SubmitService(db)` 传参错误(应为 `SubmitDAO`),本就不可用,未修——见 docs/migration/graphql-submit-bridge.md 遗留风险。
- service 校验错误(`ValueError`)经桥以 `error_kind=INVALID_CONTENT` + 中文原文(`human_readable_message`)返回。
```

- [ ] **Step 2: 迁移文档状态更新**(`docs/migration/graphql-submit-bridge.md` 头部引用块中"状态"行改为已实现,并在 §4 遗留风险追加一条)

```markdown
> 状态:**已实现**(2026-06-07,分支 feat/graphql-submit-bridge → PR 待合并)。
```

§4 追加:

```markdown
- ⚠️ 旧 GraphQL submit resolver(resolvers/submit.py)构造服务时传错参数(`SubmitService(db)`,
  构造函数要 `SubmitDAO`),即旧字段在运行时本就不可用——进一步佐证其无消费者。按"原样保留"
  决策未修;将来清理旧字段时一并处理。
```

- [ ] **Step 3: 全量验证**

```bash
python -m pytest tests/unit -q --deselect tests/unit/test_startup_db_check.py::test_lifespan_raises_on_db_failure
python -m flake8 src/ --max-line-length=88
python -m flake8 tests/unit/test_submit_bridge_resolvers.py tests/unit/test_submit_bridge_schema.py --max-line-length=88
```

Expected: 测试全过;flake8 无输出

- [ ] **Step 4: Commit + push**

```bash
git add docs/CHANGELOG.md docs/migration/graphql-submit-bridge.md
git commit -m "docs(submit): changelog + migration status for submit bridge"
git push -u origin feat/graphql-submit-bridge
```

- [ ] **Step 5: 开 PR**

```bash
gh pr create --base main --head feat/graphql-submit-bridge \
  --title "feat(graphql): submit 桥接——投票提交/回读适配前端契约" \
  --body "(正文按 CHANGELOG 条目组织:背景=前端 submit*Vote 与后端字段名/入参全不匹配;改动=submit_bridge.py 5+5、errors.py 下沉、validate_paper 重写;测试=resolver 单测 + SDL 契约回归;旧字段保留说明。结尾加:🤖 Generated with [Claude Code](https://claude.com/claude-code))"
```

Expected: 输出 PR URL;CI(代码检查+运行测试)绿。

---

## Self-Review 记录(已执行)

- **Spec 覆盖**:§2 文件清单→Task 2/4/6/8;§3 契约→Task 4/5/6/7;§4 数据流→Task 4 helpers;§5 validate_paper→Task 3;§6 错误表→Task 1/2/4(INVALID_TOKEN/INVALID_CONTENT/SUBMIT_LOCKED 各有测试);§7 测试→Task 3/4/5/6/7。无缺口。
- **占位符**:无 TBD/“类似 Task N”;所有代码块完整。
- **类型一致性**:`_vote_user_id/_server_meta/_submit_lock/_run_submit` 在 Task 4 定义、Task 5/6 复用同名;`CharacterSubmitGQL` 等类型名与 Task 7 SDL 断言一致;`name="submitCPVote"`/`name="getSubmitCPVote"` 两处大小写坑已显式标注。
