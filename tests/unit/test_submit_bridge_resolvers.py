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
