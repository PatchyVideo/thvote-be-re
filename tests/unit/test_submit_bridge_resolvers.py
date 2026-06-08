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

    async def submit_dojin_nominations(self, body, settings, scraper, now=None):
        from src.apps.submit.schemas import NominationSubmitResult
        self.bodies.append(body)
        return NominationSubmitResult(
            accepted=len(body.dojins),
            rejected=[],
            skipped=[],
        )

    async def get_character_submit(self, vote_id):
        from src.apps.submit.schemas import CharacterSubmitRest, SubmitMetadata
        self.get_calls = getattr(self, "get_calls", [])
        self.get_calls.append(vote_id)
        return CharacterSubmitRest(characters=[], meta=SubmitMetadata())

    async def get_paper_submit(self, vote_id):
        from src.apps.submit.schemas import PaperSubmitRest, SubmitMetadata
        return PaperSubmitRest(papers_json="{}", meta=SubmitMetadata())


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
async def test_submit_lock_conflict_maps_to_submit_locked(fake_env):
    # 预占锁:同 user 再提交 → SUBMIT_LOCKED
    redis = await bridge.get_redis_client()
    await redis.set("lock-submit-user-7", "someone-else", nx=True, px=10_000)
    with pytest.raises(GraphQLError) as ei:
        await bridge.SubmitBridgeMutation().submit_character_vote(
            info=_Info(), content=_character_content(_token("user-7"))
        )
    assert ei.value.extensions["error_kind"] == "SUBMIT_LOCKED"
    assert ei.value.extensions["human_readable_message"] == "提交处理中，请稍后再试"


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
            cps=[
                CPSubmitInput(id_a="reimu", id_b="marisa", active="reimu", first=True)
            ],
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
    assert out.accepted == 1  # 提名逐条结果
    assert fake_env["service"].bodies[0].dojins[0].dojin_type == "MUSIC"  # 存枚举名


@pytest.mark.asyncio
async def test_lock_released_after_success(fake_env):
    redis = await bridge.get_redis_client()
    await bridge.SubmitBridgeMutation().submit_character_vote(
        info=_Info(), content=_character_content(_token("user-7"))
    )
    assert "lock-submit-user-7" not in redis.store  # finally 释放


@pytest.mark.asyncio
async def test_lock_released_after_value_error(fake_env):
    fake_env["service"] = _FakeService(raise_value_error="多个本命")
    redis = await bridge.get_redis_client()
    with pytest.raises(GraphQLError):
        await bridge.SubmitBridgeMutation().submit_character_vote(
            info=_Info(), content=_character_content(_token("user-7"))
        )
    assert "lock-submit-user-7" not in redis.store  # 异常路径也释放


# ── Query 测试 ──────────────────────────────────────────────────────────


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


# ── 参数化 ValueError 错误路径(覆盖其余 mutation;dojin 改为提名结果语义,
# 其错误走 NOMINATION_CLOSED/NOMINATION_NOT_CONFIGURED,见集成测试) ──────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "call",
    [
        lambda token: ("submit_music_vote", dict(content=bridge.MusicSubmitGQL(
            vote_token=token, musics=[]))),
        lambda token: ("submit_cp_vote", dict(content=bridge.CPSubmitGQL(
            vote_token=token, cps=[]))),
        lambda token: ("submit_paper_vote", dict(content=bridge.PaperSubmitGQL(
            vote_token=token, paper_json="{}"))),
    ],
)
async def test_all_mutations_map_value_error(fake_env, call):
    fake_env["service"] = _FakeService(raise_value_error="数量0不在范围内[1,8]")
    method, kwargs = call(_token())
    with pytest.raises(GraphQLError) as ei:
        await getattr(bridge.SubmitBridgeMutation(), method)(info=_Info(), **kwargs)
    ext = ei.value.extensions
    assert ext["error_kind"] == "INVALID_CONTENT"
    assert ext["human_readable_message"] == "数量0不在范围内[1,8]"
