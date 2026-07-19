"""queryCharacterRanking 行为集成测:voteYear 回落 + query DSL 拒绝。

session 用 tests/integration/conftest.py 的共享 fixture;fake_redis/settings
照抄 tests/integration/test_result_compute.py 顶部。用真实白名单 id 起
raw_character 投票 -> ComputeService.compute_all 落 Redis -> monkeypatch
resolver 的 get_redis/get_settings 指向测试夹具 -> schema.execute 跑真实
GraphQL 文档(brief 给定的查询)。
"""

from __future__ import annotations

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

import src.api.graphql.resolvers.result_compat as result_compat_module
from src.api.graphql.schema import schema
from src.apps.result.compute_dao import ComputeDAO
from src.apps.result.compute_service import ComputeService
from src.apps.result.whitelist import load_whitelist
from src.common.config import Settings
from src.db_model.questionnaire_def import OptionDef, PaperAnswer, QuestionDef
from src.db_model.raw_submit import RawCharacterSubmit

QUERY_CHARACTER_RANKING = """
query($voteYear: Int, $query: String) {
  queryCharacterRanking(voteYear: $voteYear, query: $query) {
    global { totalVotes }
    entries { name displayRank voteCount firstVoteCount maleVoteCount }
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


async def _seed_and_compute(session: AsyncSession, fake_redis, settings) -> None:
    """两个真实白名单角色 + 三条投票 + 一条性别问卷答案 -> compute_all 落 Redis(2026)。

    落到 result:2026:*;result:11:* 故意留空,用于验证 voteYear 回落行为。
    """
    wl = load_whitelist("character")
    id1, id2 = sorted(wl.ids)[:2]
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


@pytest_asyncio.fixture
async def gql_schema(monkeypatch, session, fake_redis, settings):
    """schema，其 result_compat resolver 的 get_redis/get_settings 指向测试夹具。"""
    await _seed_and_compute(session, fake_redis, settings)

    async def _fake_get_redis():
        return fake_redis

    monkeypatch.setattr(result_compat_module, "get_redis", _fake_get_redis)
    monkeypatch.setattr(result_compat_module, "get_settings", lambda: settings)
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
