"""排名查询契约桥行为集成测:voteYear 回落 / query DSL 拒绝 / 未计算错误 / CP 适配。

session 用 tests/integration/conftest.py 的共享 fixture;fake_redis/settings
照抄 tests/integration/test_result_compute.py 顶部。用真实白名单 id 起
raw_character/raw_cp 投票 -> ComputeService.compute_all 落 Redis -> monkeypatch
resolvers/result.py 的 get_redis/get_settings(_get_result_service 的接线点)
指向测试夹具 -> schema.execute 跑真实 GraphQL 文档。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
import pytest_asyncio

try:
    import fakeredis.aioredis as fakeredis_aioredis
    FakeRedis = fakeredis_aioredis.FakeRedis
except ImportError:
    import fakeredis
    FakeRedis = fakeredis.aioredis.FakeRedis

from sqlalchemy.ext.asyncio import AsyncSession

import src.api.graphql.resolvers.result as result_resolver_module
from src.api.graphql.schema import schema
from src.apps.result.compute_dao import ComputeDAO
from src.apps.result.compute_service import ComputeService
from src.apps.result.whitelist import load_whitelist
from src.common.config import Settings
from src.db_model.questionnaire_def import OptionDef, PaperAnswer, QuestionDef
from src.db_model.raw_submit import RawCharacterSubmit, RawCPSubmit

QUERY_CHARACTER_RANKING = """
query($voteYear: Int, $query: String) {
  queryCharacterRanking(voteYear: $voteYear, query: $query) {
    global { totalVotes }
    entries { name displayRank voteCount firstVoteCount maleVoteCount }
  }
}
"""

QUERY_CP_RANKING = """
query {
  queryCPRanking {
    global { totalVotes }
    entries {
      displayRank
      voteCount
      cp { a b c }
      aActive
      bActive
      cActive
      noneActive
    }
  }
}
"""


@pytest_asyncio.fixture
def fake_redis():
    return FakeRedis(decode_responses=True)


@pytest_asyncio.fixture
def settings():
    s = Settings()
    s.__dict__["vote_year"] = 2026
    s.__dict__["vote_start_iso"] = "2026-01-01T00:00:00Z"
    s.__dict__["vote_end_iso"] = "2026-12-31T23:59:59Z"
    s.__dict__["gender_question_code"] = "11011"
    s.__dict__["gender_male_option_code"] = "1101101"
    s.__dict__["gender_female_option_code"] = "1101102"
    return s


def _patch_result_service(monkeypatch, fake_redis, settings) -> None:
    """把 resolvers/result.py 里 _get_result_service 的 get_redis/get_settings
    接线指向测试夹具——result_compat.py 现在直接复用这个函数(不再自己拷贝一份),
    所以两处 resolver 共享同一个 monkeypatch 入口。"""

    async def _fake_get_redis():
        return fake_redis

    monkeypatch.setattr(result_resolver_module, "get_redis", _fake_get_redis)
    monkeypatch.setattr(result_resolver_module, "get_settings", lambda: settings)


async def _seed_and_compute(session: AsyncSession, fake_redis, settings) -> None:
    """两个真实白名单角色 + 三条角色投票 + 两组 CP 投票(2 人/3 人各一) + 一条
    性别问卷答案 -> compute_all 落 Redis(2026)。

    落到 result:2026:*;result:11:* 故意留空,用于验证 voteYear 回落行为。
    """
    wl = load_whitelist("character")
    id1, id2, id3 = sorted(wl.ids)[:3]
    session.add_all([
        RawCharacterSubmit(
            vote_id="user-1", attempt=1,
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc), user_ip="",
            payload=[{"id": id1, "first": True, "reason": "love"}],
        ),
        RawCharacterSubmit(
            vote_id="user-2", attempt=1,
            created_at=datetime(2026, 1, 3, tzinfo=timezone.utc), user_ip="",
            payload=[{"id": id1, "first": False, "reason": None}],
        ),
        RawCharacterSubmit(
            vote_id="user-3", attempt=1,
            created_at=datetime(2026, 1, 4, tzinfo=timezone.utc), user_ip="",
            payload=[{"id": id2, "first": True, "reason": None}],
        ),
        # 2 人 CP：id1×id2，两票(组合票数==1 不计入排名，需要 >=2)
        RawCPSubmit(
            vote_id="cp-user-1", attempt=1,
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc), user_ip="",
            payload=[{
                "id_a": id1, "id_b": id2, "id_c": None,
                "active": "a", "first": True, "reason": None,
            }],
        ),
        RawCPSubmit(
            vote_id="cp-user-2", attempt=1,
            created_at=datetime(2026, 1, 3, tzinfo=timezone.utc), user_ip="",
            payload=[{
                "id_a": id2, "id_b": id1, "id_c": None,
                "active": "none", "first": False, "reason": None,
            }],
        ),
        # 3 人 CP：id1×id2×id3，两票
        RawCPSubmit(
            vote_id="cp-user-3", attempt=1,
            created_at=datetime(2026, 1, 4, tzinfo=timezone.utc), user_ip="",
            payload=[{
                "id_a": id1, "id_b": id2, "id_c": id3,
                "active": "b", "first": True, "reason": None,
            }],
        ),
        RawCPSubmit(
            vote_id="cp-user-4", attempt=1,
            created_at=datetime(2026, 1, 5, tzinfo=timezone.utc), user_ip="",
            payload=[{
                "id_a": id3, "id_b": id1, "id_c": id2,
                "active": "none", "first": False, "reason": None,
            }],
        ),
    ])
    gender_q = QuestionDef(group_id=1, type="Single", content="性别", code="11011")
    session.add(gender_q)
    await session.flush()
    opt_male = OptionDef(question_id=gender_q.id, content="男", code="1101101")
    session.add(opt_male)
    await session.flush()
    session.add(PaperAnswer(
        vote_id="user-1", vote_year=2026, questionnaire_id=1, group_id=1,
        active_question_id=gender_q.id, selected_option_ids=[opt_male.id],
    ))
    await session.commit()

    dao = ComputeDAO(session)
    svc = ComputeService(dao, fake_redis, settings)
    result = await svc.compute_all(2026)
    assert result["ok"] is True
    assert result["counts"]["chars"] == 2
    assert result["counts"]["cps"] == 2


@pytest_asyncio.fixture
async def gql_schema(monkeypatch, session, fake_redis, settings):
    """schema，其 result_compat resolver(经 _get_result_service)指向测试夹具。"""
    await _seed_and_compute(session, fake_redis, settings)
    _patch_result_service(monkeypatch, fake_redis, settings)
    return schema


@pytest_asyncio.fixture
async def gql_schema_uncomputed(monkeypatch, fake_redis, settings):
    """schema，指向一个从未跑过 compute_all 的空 fake_redis(模拟全新部署/该年
    确实没算过——不是 seed 阶段的疏漏)。"""
    _patch_result_service(monkeypatch, fake_redis, settings)
    return schema


@pytest.mark.asyncio
async def test_query_character_ranking_returns_entries(gql_schema) -> None:
    result = await gql_schema.execute(
        QUERY_CHARACTER_RANKING, variable_values={"voteYear": None, "query": None}
    )
    assert result.errors is None
    ranking = result.data["queryCharacterRanking"]
    assert len(ranking["entries"]) == 2
    assert ranking["global"]["totalVotes"] == 3


@pytest.mark.asyncio
async def test_query_character_ranking_vote_year_fallback(gql_schema) -> None:
    """前端硬编码 voteYear: 11(该年无计算数据) -> 回落 settings.vote_year(2026) 仍有数据。"""
    result = await gql_schema.execute(
        QUERY_CHARACTER_RANKING, variable_values={"voteYear": 11, "query": None}
    )
    assert result.errors is None
    ranking = result.data["queryCharacterRanking"]
    assert len(ranking["entries"]) == 2
    assert ranking["global"]["totalVotes"] == 3


@pytest.mark.asyncio
async def test_query_character_ranking_rejects_query_dsl(gql_schema) -> None:
    """非空 query(高级搜索 DSL)-> 可辨识错误,且不是 INTERNAL_ERROR
    (静默忽略会让用户误以为看到的是筛选后的结果,这是要避免的失败模式)。"""
    result = await gql_schema.execute(
        QUERY_CHARACTER_RANKING,
        variable_values={"voteYear": None, "query": 'chars:["x"]'},
    )
    assert result.errors is not None
    error_kind = result.errors[0].extensions["error_kind"]
    assert error_kind != "INTERNAL_ERROR"
    assert error_kind == "ADVANCED_SEARCH_NOT_IMPLEMENTED"


@pytest.mark.asyncio
async def test_query_character_ranking_not_computed_is_stable_and_leak_free(
    gql_schema_uncomputed,
) -> None:
    """该年(含回落后的 settings.vote_year)确实没算过时:错误 kind 必须稳定
    可辨识(不是 dao.py 里那条含年份/Redis key 的原始 message),且响应里不能
    出现内部 Redis key 布局(如 "result:2026:chars:ranking")。"""
    result = await gql_schema_uncomputed.execute(
        QUERY_CHARACTER_RANKING, variable_values={"voteYear": None, "query": None}
    )
    assert result.errors is not None
    error_kind = result.errors[0].extensions["error_kind"]
    assert error_kind == "RESULT_NOT_COMPUTED"

    # 完整序列化整个错误对象(含 locations/path,而不是只挑 message/extensions)——
    # 这条测试的目的就是证明"响应里任何角落都不泄内部细节",挑字段序列化会让
    # 这个安全性质变得不完整。
    serialized = json.dumps(
        {"errors": [e.formatted for e in result.errors]},
        default=str,
    )
    assert "result:" not in serialized
    assert "Redis key" not in serialized


@pytest.mark.asyncio
async def test_query_cp_ranking_adapts_two_and_three_member_entries(gql_schema) -> None:
    """CP 适配器覆盖 2 人(cp.c 为 None)和 3 人(cp.c 非 None)两种成员数形状。"""
    result = await gql_schema.execute(QUERY_CP_RANKING)
    assert result.errors is None
    ranking = result.data["queryCPRanking"]
    entries = ranking["entries"]
    assert len(entries) == 2
    assert ranking["global"]["totalVotes"] == 4

    by_c_none = {e["cp"]["c"] is None: e for e in entries}
    assert set(by_c_none.keys()) == {True, False}

    two_member = by_c_none[True]
    assert two_member["voteCount"] == 2
    assert {two_member["cp"]["a"], two_member["cp"]["b"]} == {
        load_whitelist("character").name_of(sorted(load_whitelist("character").ids)[0]),
        load_whitelist("character").name_of(sorted(load_whitelist("character").ids)[1]),
    }

    three_member = by_c_none[False]
    assert three_member["voteCount"] == 2
    assert three_member["cp"]["c"] == (
        load_whitelist("character").name_of(sorted(load_whitelist("character").ids)[2])
    )
