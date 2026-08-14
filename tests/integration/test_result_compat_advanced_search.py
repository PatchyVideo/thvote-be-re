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
    ``chars: ["{name1}"]``(name1=id1)圈出的子集 {user-1, user-2} 里。这道题是
    在预计算快照(``_seed_and_compute`` 里的 ``compute_all``)跑完之后才补种
    的,所以并非"全量结果里这道题正常存在、子集里消失"的对照——真正被验证
    的是筛选路径本身的机制:命中 miss 后 ``_compute_filtered`` 重新从 DB
    载票(带上刚补种的 q22022 答案),再把 q_votes 按子集过滤
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


QUERY_MUSIC_RANKING_FILTERED = """
query($voteYear: Int, $query: String) {
  queryMusicRanking(voteYear: $voteYear, query: $query) {
    entries { name voteCount }
    global { totalVotes }
  }
}
"""

QUERY_CP_RANKING_FILTERED = """
query($voteYear: Int, $query: String) {
  queryCPRanking(voteYear: $voteYear, query: $query) {
    entries { voteCount cp { a b c } }
    global { totalVotes }
  }
}
"""

QUERY_GLOBAL_STATS = """
query($voteYear: Int, $query: String) {
  queryGlobalStats(voteYear: $voteYear, query: $query) {
    voteYear
    numVote
    numChar
    numMusic
    numCp
    numDoujin
    numMale
    numFemale
  }
}
"""

QUERY_COMPLETION_RATES = """
query($voteYear: Int, $query: String) {
  queryCompletionRates(voteYear: $voteYear, query: $query) {
    voteYear
    items { name rate numComplete total }
  }
}
"""


@pytest.mark.asyncio
async def test_music_cp_stats_completion_share_same_filtered_subset(gql) -> None:
    """同一个非空 query 打四个不同端点(音乐榜/CP 榜/全局统计/完成率),都走
    ``_apply_advanced_search`` 命中同一份筛选缓存(同年份+同指纹),各自读取
    自己那段 key infix 下的子集口径数值,互不报错。

    ``chars: ["{name1}"]``(name1=id1)圈出的子集是 ``_seed_and_compute``
    里的 {user-1, user-2}(两人都投了 id1)。推导每个断言:

    - 音乐榜:种子里从未提交过任何音乐投票(``_seed_and_compute`` 不建
      ``RawMusicSubmit``),``_compute_filtered`` 里 ``music_votes`` 恒为
      空列表,子集过滤不改变这个事实——entries=[]、totalVotes=0 是合法值,
      不是"筛选出了空集"这种偶然结果。
    - CP 榜:CP 投票的 vote_id 是 ``cp-user-1``..``cp-user-4``(与角色投票
      的 ``user-1``/``user-2``/``user-3`` 是完全不同的 vote_id 命名空间),
      子集 {user-1, user-2} 里不包含任何一个 cp-user-*——即使 cp-user-1/
      cp-user-2 确实投了 id1×id2 这对组合(两票,达到入榜门槛)，它们的
      vote_id 本身就不在这个子集里，``_compute_filtered`` 里
      ``cp_votes = [v for v in cp_votes if v[0] in subset]`` 把四条 CP 记录
      全部滤空 → entries=[]、totalVotes=0。
    - 全局统计:``char_votes`` 过滤后剩 user-1(first=True)/user-2 两票，
      都投 id1 → numChar=2；numMusic=numCp=0(同上两条)；
      ``all_users = char_users|music_users|cp_users|q_users`` = {user-1,
      user-2} → numVote=2；``segment_map`` 用**全量**问卷构建(不经子集
      过滤,见 ``_compute_filtered`` 注释),user-1 答过性别=男，user-2 未
      答 → numMale=1、numFemale=0。
    - 完成率:``all_voters`` 同上 = {user-1, user-2}，total=2；character
      分子=2(两人都投了角色)→ rate=1.0；music/cp 分子=0(同上)；
      questionnaire 分子=1(问卷投票者里只有 user-1 的性别答案落在子集
      内,user-2 没有问卷答案)→ rate=0.5。
    """
    schema_, name1, _ = gql
    variables = {"voteYear": 2026, "query": f'chars: ["{name1}"]'}

    music_result = await schema_.execute(
        QUERY_MUSIC_RANKING_FILTERED, variable_values=variables
    )
    assert music_result.errors is None
    music_ranking = music_result.data["queryMusicRanking"]
    assert music_ranking["entries"] == []
    assert music_ranking["global"]["totalVotes"] == 0

    cp_result = await schema_.execute(
        QUERY_CP_RANKING_FILTERED, variable_values=variables
    )
    assert cp_result.errors is None
    cp_ranking = cp_result.data["queryCPRanking"]
    assert cp_ranking["entries"] == []
    assert cp_ranking["global"]["totalVotes"] == 0

    stats_result = await schema_.execute(QUERY_GLOBAL_STATS, variable_values=variables)
    assert stats_result.errors is None
    stats = stats_result.data["queryGlobalStats"]
    assert stats["numVote"] == 2
    assert stats["numChar"] == 2
    assert stats["numMusic"] == 0
    assert stats["numCp"] == 0
    assert stats["numMale"] == 1
    assert stats["numFemale"] == 0

    rates_result = await schema_.execute(
        QUERY_COMPLETION_RATES, variable_values=variables
    )
    assert rates_result.errors is None
    items = {i["name"]: i for i in rates_result.data["queryCompletionRates"]["items"]}
    assert items["character"]["total"] == 2
    assert items["character"]["numComplete"] == 2
    assert items["music"]["numComplete"] == 0
    assert items["cp"]["numComplete"] == 0
    assert items["questionnaire"]["numComplete"] == 1
    assert items["questionnaire"]["total"] == 2


QUERY_CHARACTER_SINGLE = """
query($voteYear: Int, $query: String, $rank: Int!) {
  queryCharacterSingle(rank: $rank, voteYear: $voteYear, query: $query) {
    name
    displayRank
    voteCount
  }
}
"""


@pytest.mark.asyncio
async def test_character_single_with_filter(gql) -> None:
    """筛选子集下的单条查询:rank 按子集内的名次序号(不是全量榜单的序号)。

    ``chars: ["{name1}"]`` 圈出子集 {user-1, user-2},榜上只剩 name1 一条,
    rank=1 命中;子集内不存在的 rank=2(全量里 id2 那条已被子集滤掉)
    应该报可辨识的 ENTITY_NOT_FOUND,而不是 500 或返回 null。
    """
    schema_, name1, _ = gql
    variables = {"voteYear": 2026, "query": f'chars: ["{name1}"]'}

    hit = await schema_.execute(
        QUERY_CHARACTER_SINGLE, variable_values={**variables, "rank": 1}
    )
    assert hit.errors is None
    assert hit.data["queryCharacterSingle"]["name"] == name1

    miss = await schema_.execute(
        QUERY_CHARACTER_SINGLE, variable_values={**variables, "rank": 2}
    )
    assert miss.errors is not None
    assert miss.errors[0].extensions["error_kind"] == "ENTITY_NOT_FOUND"


@pytest.mark.asyncio
async def test_too_complex_query_is_identifiable_end_to_end(gql) -> None:
    """21 个原子(> MAX_ATOMS=20,见 dsl.py)的 query 经 GraphQL 端到端报
    ADVANCED_SEARCH_TOO_COMPLEX,而不是在 parse_query 内部单测覆盖之外
    悄悄被契约层吞掉或变成别的错误 kind。构造方式与
    tests/unit/test_advanced_search_dsl.py::TestLimits.test_too_many_atoms
    一致(21 个不重复的 qcode,互不去重)。
    """
    schema_, _, _ = gql
    query = " OR ".join(f"q{i} = 1" for i in range(21))
    result = await schema_.execute(
        QUERY_CHARACTER_RANKING,
        variable_values={"voteYear": 2026, "query": query},
    )
    assert result.errors is not None
    assert result.errors[0].extensions["error_kind"] == "ADVANCED_SEARCH_TOO_COMPLEX"
