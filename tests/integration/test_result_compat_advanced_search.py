"""契约层高级搜索集成测:GraphQL query 参数端到端(设计稿 §三/§八)。"""

from __future__ import annotations

import pytest
import pytest_asyncio

import src.apps.result.advanced_search.service as adv_service_module
from src.apps.result.whitelist import load_whitelist_db
from src.db_model.questionnaire_def import OptionDef, PaperAnswer, QuestionDef
from tests.integration.test_result_compat_ranking import (
    QUERY_CHARACTER_RANKING,
    _patch_result_service,
    _seed_and_compute,
    fake_redis,
    settings,
)
from src.api.graphql.schema import schema

__all__ = ["fake_redis", "settings"]  # re-export fixtures for pytest


@pytest_asyncio.fixture
async def gql(monkeypatch, session, session_maker, fake_redis, settings):
    """种子+compute(复用 ranking 测试的 helper)+ 双 monkeypatch:
    resolver 的 redis/settings + advanced_search 的 session_maker。
    返回 (schema, name1, name2):name1=两票角色,name2=一票角色。"""
    await _seed_and_compute(session, fake_redis, settings)
    _patch_result_service(monkeypatch, fake_redis, settings)
    monkeypatch.setattr(adv_service_module, "get_session_maker", lambda: session_maker)
    wl = await load_whitelist_db(session, "character", 2026)
    id1, id2 = sorted(wl.ids)[:2]
    return schema, wl.name_of(id1), wl.name_of(id2)


@pytest.mark.asyncio
async def test_filtered_ranking_recounts_on_subset(gql) -> None:
    schema_, name1, _ = gql
    result = await schema_.execute(
        QUERY_CHARACTER_RANKING,
        variable_values={"voteYear": 2026, "query": f'chars: ["{name1}"]'},
    )
    assert result.errors is None
    data = result.data["queryCharacterRanking"]
    # _seed_and_compute:user-1/user-2 投 id1,user-3 投 id2。
    # 筛选"投了 name1"→ 子集 {user-1, user-2} → 榜上只剩 name1,基数=2
    assert [e["name"] for e in data["entries"]] == [name1]
    assert data["entries"][0]["voteCount"] == 2
    assert data["global"]["totalVotes"] == 2


@pytest.mark.asyncio
async def test_empty_and_none_query_hit_precomputed_path(gql) -> None:
    schema_, _, _ = gql
    baseline = await schema_.execute(
        QUERY_CHARACTER_RANKING, variable_values={"voteYear": 2026, "query": None}
    )
    for q in ("", "NONE"):
        result = await schema_.execute(
            QUERY_CHARACTER_RANKING, variable_values={"voteYear": 2026, "query": q}
        )
        assert result.errors is None
        assert result.data == baseline.data


@pytest.mark.asyncio
async def test_syntax_error_is_identifiable(gql) -> None:
    schema_, _, _ = gql
    result = await schema_.execute(
        QUERY_CHARACTER_RANKING,
        variable_values={"voteYear": 2026, "query": "chars:["},
    )
    assert result.errors is not None
    # GraphQLError 的 message 恒为 "Error"(map_app_errors 的设计,见
    # errors.py):可辨识的 kind 落在 extensions 里,不在 str(error) 里——
    # 与 test_result_compat_ranking.py 里既有的
    # test_query_character_ranking_not_computed_is_stable_and_leak_free 同一
    # 断言口径,这里对齐,而不是断言 brief 字面写的 str(error) 包含关系
    # (那条对当前 errors.py 契约不成立)。
    assert result.errors[0].extensions["error_kind"] == "ADVANCED_SEARCH_SYNTAX_ERROR"


@pytest.mark.asyncio
async def test_unknown_name_is_identifiable(gql) -> None:
    schema_, _, _ = gql
    result = await schema_.execute(
        QUERY_CHARACTER_RANKING,
        variable_values={"voteYear": 2026, "query": 'chars: ["绝对不存在的角色名XYZ"]'},
    )
    assert result.errors is not None
    assert result.errors[0].extensions["error_kind"] == "ADVANCED_SEARCH_UNKNOWN_NAME"


QUERY_QUESTIONNAIRE = """
query($voteYear: Int, $query: String, $questionsOfInterest: [String!]!) {
  queryQuestionnaire(
    voteYear: $voteYear, query: $query, questionsOfInterest: $questionsOfInterest
  ) {
    entries {
      questionId
      totalAnswers
      answersCat { aid totalVotes maleVotes femaleVotes }
    }
  }
}
"""


@pytest.mark.asyncio
async def test_filtered_questionnaire_missing_question_skipped(gql, session) -> None:
    """窄子集下 paper:{qid} 缺 key,由契约层 catch-skip 兜住——entries 里对应
    的题消失,而不是整个查询报错(``_query_questionnaire_entries`` 里的
    ``except ResultNotComputedError: continue``)。

    补种一道**只有 user-3 回答**的题(code=22022)——user-3 投的是 id2,不在
    ``chars: ["{name1}"]``(name1=id1)圈出的子集 {user-1, user-2} 里。全量结果
    里这道题正常存在,但 ``_compute_filtered`` 会把 q_votes 按子集过滤
    (``[v for v in q_votes if v[0] in subset]``),user-3 的答案被过滤掉后
    ``compute_paper_results`` 根本不会产出这道题的 key——这比"这道题从未被
    种过数据"的平凡情形更精确地验证了子集过滤导致的 catch-skip 行为。
    """
    schema_, name1, _ = gql
    only_user3_question = QuestionDef(
        group_id=2, type="Single", content="仅 user-3 回答", code="22022"
    )
    session.add(only_user3_question)
    await session.flush()
    only_user3_option = OptionDef(
        question_id=only_user3_question.id, content="选项", code="2202201"
    )
    session.add(only_user3_option)
    await session.flush()
    session.add(
        PaperAnswer(
            vote_id="user-3", vote_year=2026, questionnaire_id=1, group_id=2,
            active_question_id=only_user3_question.id,
            selected_option_ids=[only_user3_option.id],
        )
    )
    await session.commit()

    result = await schema_.execute(
        QUERY_QUESTIONNAIRE,
        variable_values={
            "voteYear": 2026,
            "query": f'chars: ["{name1}"]',
            "questionsOfInterest": ["q11011", "q22022"],
        },
    )
    assert result.errors is None
    entries = result.data["queryQuestionnaire"]["entries"]
    question_ids = [e["questionId"] for e in entries]
    # q11011:user-1(在子集内)的答案,子集内仍有数据 → 保留。
    assert "q11011" in question_ids
    # q22022:唯一回答者 user-3 不在子集内,子集过滤后这道题缺 key → 从
    # entries 里消失,而不是让整个查询报错。
    assert "q22022" not in question_ids
