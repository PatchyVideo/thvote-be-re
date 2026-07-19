"""契约层剩余九个查询的行为集成测:单条(按唯一序号)/趋势/全局统计/完成率/问卷。

fixture 照抄 tests/integration/test_result_compat_ranking.py 顶部的写法
（fake_redis/settings/_patch_result_service/schema.execute），seed 数据专门
制造了一组"票数相同、display_rank 并列"的角色，用来验证
queryCharacterSingle 按 rank[0].rank（唯一序号）而不是 display_rank 取值。
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

import src.api.graphql.resolvers.result as result_resolver_module
from src.api.graphql.schema import schema
from src.apps.result.compute_dao import ComputeDAO
from src.apps.result.compute_service import ComputeService
from src.apps.result.whitelist import load_whitelist
from src.common.config import Settings
from src.db_model.questionnaire_def import OptionDef, PaperAnswer, QuestionDef
from src.db_model.raw_submit import RawCharacterSubmit, RawCPSubmit, RawMusicSubmit

QUERY_CHARACTER_SINGLE = """
query($rank: Int!, $voteYear: Int, $query: String) {
  queryCharacterSingle(rank: $rank, voteYear: $voteYear, query: $query) {
    name
    rank
    displayRank
  }
}
"""

QUERY_MUSIC_SINGLE = """
query($rank: Int!, $voteYear: Int) {
  queryMusicSingle(rank: $rank, voteYear: $voteYear) {
    name
    rank
    displayRank
  }
}
"""

QUERY_CP_SINGLE = """
query($rank: Int!, $voteYear: Int) {
  queryCPSingle(rank: $rank, voteYear: $voteYear) {
    rank
    displayRank
    voteCount
    cp { a b c }
  }
}
"""

QUERY_CHARACTER_TREND = """
query($names: [String!]!, $voteYear: Int) {
  queryCharacterTrend(names: $names, voteYear: $voteYear) {
    trend { hrs cnt }
    trendFirst { hrs cnt }
  }
}
"""

QUERY_MUSIC_TREND = """
query($names: [String!]!, $voteYear: Int) {
  queryMusicTrend(names: $names, voteYear: $voteYear) {
    trend { hrs cnt }
  }
}
"""

QUERY_GLOBAL_STATS = """
query($voteYear: Int) {
  queryGlobalStats(voteYear: $voteYear) {
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
query($voteYear: Int) {
  queryCompletionRates(voteYear: $voteYear) {
    voteYear
    items { name rate numComplete total }
  }
}
"""

QUERY_QUESTIONNAIRE = """
query($ids: [String!]!, $voteYear: Int) {
  queryQuestionnaire(questionsOfInterest: $ids, voteYear: $voteYear) {
    entries {
      questionId
      answersCat { aid totalVotes maleVotes femaleVotes }
      answersStr
      totalAnswers
      totalMale
      totalFemale
    }
  }
}
"""

QUERY_QUESTIONNAIRE_TREND = """
query($ids: [String!]!, $voteYear: Int) {
  queryQuestionnaireTrend(questionIds: $ids, voteYear: $voteYear) {
    trend { hrs cnt }
    trendFirst { hrs cnt }
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
    async def _fake_get_redis():
        return fake_redis

    monkeypatch.setattr(result_resolver_module, "get_redis", _fake_get_redis)
    monkeypatch.setattr(result_resolver_module, "get_settings", lambda: settings)


async def _seed_and_compute(session: AsyncSession, fake_redis, settings) -> None:
    """两个并列票数的角色(id1/id2,各 2 票、各 1 本命 -> display_rank 相同但
    rank[0].rank 不同)+ 一个单独名次的角色(id3,1 票)+ 两首音乐(m1 2 票/m2 1
    票)+ 一组 2 人 CP(id1×id2,2 票)+ 两道问卷题(性别单选 11011 + 填空 11021)
    -> compute_all 落 Redis(2026)。

    角色的提交时间刻意错开(day2/3/4/5/6),换算成 hour_bucket 后彼此不重叠
    （相对 vote_start=2026-01-01 分别是 24/48/72/96/120 小时），用于验证
    queryCharacterTrend 按输入 name 顺序返回、且每个 name 的 trend 小时桶
    与其真实提交时间一致（不是随便凑出的空/非空判断）。
    """
    char_wl = load_whitelist("character")
    music_wl = load_whitelist("music")
    id1, id2, id3 = sorted(char_wl.ids)[:3]
    m1, m2 = sorted(music_wl.ids)[:2]

    def _char_vote(vote_id: str, oid: str, first: bool, day: int) -> RawCharacterSubmit:
        return RawCharacterSubmit(
            vote_id=vote_id, attempt=1,
            created_at=datetime(2026, 1, day, tzinfo=timezone.utc), user_ip="",
            payload=[{"id": oid, "first": first, "reason": None}],
        )

    def _music_vote(vote_id: str, oid: str, first: bool, day: int) -> RawMusicSubmit:
        return RawMusicSubmit(
            vote_id=vote_id, attempt=1,
            created_at=datetime(2026, 1, day, tzinfo=timezone.utc), user_ip="",
            payload=[{"id": oid, "first": first, "reason": None}],
        )

    session.add_all([
        # id1/id2 并列:各 2 票、各 1 本命
        _char_vote("user-1", id1, True, 2),
        _char_vote("user-2", id1, False, 3),
        _char_vote("user-3", id2, True, 4),
        _char_vote("user-4", id2, False, 5),
        # id3 单独名次:1 票
        _char_vote("user-5", id3, False, 6),
        # 音乐:m1 2 票 / m2 1 票
        _music_vote("user-1", m1, True, 2),
        _music_vote("user-2", m1, False, 3),
        _music_vote("user-3", m2, True, 4),
        # 2 人 CP:id1×id2,2 票(>=2 才计入排名)
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
    ])

    gender_q = QuestionDef(group_id=1, type="Single", content="性别", code="11011")
    input_q = QuestionDef(group_id=2, type="Input", content="备注", code="11021")
    session.add_all([gender_q, input_q])
    await session.flush()
    opt_male = OptionDef(question_id=gender_q.id, content="男", code="1101101")
    opt_female = OptionDef(question_id=gender_q.id, content="女", code="1101102")
    session.add_all([opt_male, opt_female])
    await session.flush()
    session.add_all([
        # user-1=male, user-3=female -> 性别题总答 2、总男 1、总女 1
        PaperAnswer(
            vote_id="user-1", vote_year=2026, questionnaire_id=1, group_id=1,
            active_question_id=gender_q.id, selected_option_ids=[opt_male.id],
        ),
        PaperAnswer(
            vote_id="user-3", vote_year=2026, questionnaire_id=1, group_id=1,
            active_question_id=gender_q.id, selected_option_ids=[opt_female.id],
        ),
        # 填空题只有 user-1(male)答了
        PaperAnswer(
            vote_id="user-1", vote_year=2026, questionnaire_id=1, group_id=2,
            active_question_id=input_q.id, selected_option_ids=[],
            input_text="喜欢",
        ),
    ])
    await session.commit()

    dao = ComputeDAO(session)
    svc = ComputeService(dao, fake_redis, settings)
    result = await svc.compute_all(2026)
    assert result["ok"] is True
    assert result["counts"]["chars"] == 3
    assert result["counts"]["musics"] == 2
    assert result["counts"]["cps"] == 1
    assert result["counts"]["questions"] == 2


@pytest_asyncio.fixture
async def gql_schema(monkeypatch, session, fake_redis, settings):
    await _seed_and_compute(session, fake_redis, settings)
    _patch_result_service(monkeypatch, fake_redis, settings)
    return schema


@pytest_asyncio.fixture
async def gql_schema_uncomputed(monkeypatch, fake_redis, settings):
    """schema，指向一个从未跑过 compute_all 的空 fake_redis(模拟全新部署)。"""
    _patch_result_service(monkeypatch, fake_redis, settings)
    return schema


# ── queryCharacterSingle / queryMusicSingle / queryCPSingle ───────────────


@pytest.mark.asyncio
async def test_query_character_single_uses_unique_ordinal_not_display_rank(
    gql_schema,
) -> None:
    """id1/id2 票数相同 -> display_rank 并列(都是 1),但 rank[0].rank 不同
    (1/2)。用唯一序号取出的两条必须是不同的、可区分的条目。"""
    char_wl = load_whitelist("character")
    id1, id2, _ = sorted(char_wl.ids)[:3]
    names = {char_wl.name_of(id1), char_wl.name_of(id2)}

    r1 = await gql_schema.execute(
        QUERY_CHARACTER_SINGLE,
        variable_values={"rank": 1, "voteYear": None, "query": None},
    )
    r2 = await gql_schema.execute(
        QUERY_CHARACTER_SINGLE,
        variable_values={"rank": 2, "voteYear": None, "query": None},
    )
    assert r1.errors is None and r2.errors is None
    e1, e2 = r1.data["queryCharacterSingle"], r2.data["queryCharacterSingle"]

    assert e1["rank"] == 1 and e2["rank"] == 2
    assert e1["displayRank"] == 1 and e2["displayRank"] == 1  # 并列
    assert e1["name"] != e2["name"]
    assert {e1["name"], e2["name"]} == names


@pytest.mark.asyncio
async def test_query_music_single_returns_top_entry(gql_schema) -> None:
    music_wl = load_whitelist("music")
    m1, _ = sorted(music_wl.ids)[:2]

    result = await gql_schema.execute(
        QUERY_MUSIC_SINGLE, variable_values={"rank": 1, "voteYear": None}
    )
    assert result.errors is None
    entry = result.data["queryMusicSingle"]
    assert entry["name"] == music_wl.name_of(m1)
    assert entry["rank"] == 1
    assert entry["displayRank"] == 1


@pytest.mark.asyncio
async def test_query_music_single_rank_not_found_is_recognizable_error(
    gql_schema,
) -> None:
    """只有 2 首歌入榜,rank=999 找不到 -> 可辨识错误,不是 INTERNAL_ERROR,
    也不是把 null 悄悄塞进必填的 RankingEntry!。"""
    result = await gql_schema.execute(
        QUERY_MUSIC_SINGLE, variable_values={"rank": 999, "voteYear": None}
    )
    assert result.errors is not None
    error_kind = result.errors[0].extensions["error_kind"]
    assert error_kind == "ENTITY_NOT_FOUND"
    assert error_kind != "INTERNAL_ERROR"


@pytest.mark.asyncio
async def test_query_cp_single_returns_entry(gql_schema) -> None:
    char_wl = load_whitelist("character")
    id1, id2, _ = sorted(char_wl.ids)[:3]

    result = await gql_schema.execute(
        QUERY_CP_SINGLE, variable_values={"rank": 1, "voteYear": None}
    )
    assert result.errors is None
    entry = result.data["queryCPSingle"]
    assert entry["voteCount"] == 2
    assert entry["cp"]["a"] == char_wl.name_of(id1)
    assert entry["cp"]["b"] == char_wl.name_of(id2)
    assert entry["cp"]["c"] is None


# ── queryCharacterTrend / queryMusicTrend ─────────────────────────────────


@pytest.mark.asyncio
async def test_query_character_trend_preserves_order_and_empty_for_unknown_name(
    gql_schema,
) -> None:
    char_wl = load_whitelist("character")
    id1, id2, _ = sorted(char_wl.ids)[:3]
    name1, name2 = char_wl.name_of(id1), char_wl.name_of(id2)

    result = await gql_schema.execute(
        QUERY_CHARACTER_TREND,
        variable_values={"names": [name2, "不存在的名字", name1], "voteYear": None},
    )
    assert result.errors is None
    trends = result.data["queryCharacterTrend"]
    assert len(trends) == 3

    # 顺序与入参一致:trends[0] 对应 name2(day4/5 -> hrs 72/96)
    assert {t["hrs"] for t in trends[0]["trend"]} == {72, 96}
    # 缺失的 name -> 空 trend,不报错
    assert trends[1]["trend"] == []
    assert trends[1]["trendFirst"] == []
    # trends[2] 对应 name1(day2/3 -> hrs 24/48)
    assert {t["hrs"] for t in trends[2]["trend"]} == {24, 48}


@pytest.mark.asyncio
async def test_query_music_trend_returns_populated_trend(gql_schema) -> None:
    music_wl = load_whitelist("music")
    m1, _ = sorted(music_wl.ids)[:2]

    result = await gql_schema.execute(
        QUERY_MUSIC_TREND,
        variable_values={"names": [music_wl.name_of(m1)], "voteYear": None},
    )
    assert result.errors is None
    trends = result.data["queryMusicTrend"]
    assert len(trends) == 1
    assert sum(t["cnt"] for t in trends[0]["trend"]) == 2


# ── queryGlobalStats ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_global_stats_uses_resolved_year_and_matches_seed(
    gql_schema,
) -> None:
    """voteYear=11(legacy,无数据)-> 回落到 settings.vote_year(2026);
    返回的 voteYear 字段是解析后的年份,不是原始传参。"""
    result = await gql_schema.execute(
        QUERY_GLOBAL_STATS, variable_values={"voteYear": 11}
    )
    assert result.errors is None
    stats = result.data["queryGlobalStats"]
    assert stats["voteYear"] == 2026
    assert stats["numChar"] == 5  # user-1..5 都投了角色票
    assert stats["numMusic"] == 3  # user-1..3 投了音乐票
    assert stats["numCp"] == 2  # cp-user-1/2
    assert stats["numDoujin"] == 0
    assert stats["numMale"] == 1  # 只有 user-1 选了男
    assert stats["numFemale"] == 1  # 只有 user-3 选了女
    assert stats["numVote"] == 7  # 5 角色 + 2 CP 投票人(并集,音乐票人已含其中)


# ── queryCompletionRates ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_completion_rates_returns_items_with_counts(gql_schema) -> None:
    result = await gql_schema.execute(
        QUERY_COMPLETION_RATES, variable_values={"voteYear": None}
    )
    assert result.errors is None
    payload = result.data["queryCompletionRates"]
    assert payload["voteYear"] == 2026
    by_name = {item["name"]: item for item in payload["items"]}
    assert set(by_name) == {"character", "music", "cp", "questionnaire"}
    assert by_name["character"]["numComplete"] == 5
    assert by_name["character"]["total"] == 7
    assert by_name["music"]["numComplete"] == 3
    assert by_name["cp"]["numComplete"] == 2
    assert by_name["questionnaire"]["numComplete"] == 2  # user-1、user-3 答过题
    assert by_name["character"]["rate"] == pytest.approx(5 / 7)


# ── queryQuestionnaire / queryQuestionnaireTrend ────────────────────────────


@pytest.mark.asyncio
async def test_query_questionnaire_accepts_q_prefix_and_bare_code_and_skips_missing(
    gql_schema,
) -> None:
    """覆盖 brief 要求的两种写法('q11011' 与裸码 '11021')都要命中同一份数据；
    第三个 id 是从未算过的题,必须被跳过而不是报错。"""
    result = await gql_schema.execute(
        QUERY_QUESTIONNAIRE,
        variable_values={"ids": ["q11011", "11021", "q99999"], "voteYear": None},
    )
    assert result.errors is None
    entries = result.data["queryQuestionnaire"]["entries"]
    assert len(entries) == 2  # q99999 被跳过

    gender_entry, input_entry = entries[0], entries[1]
    assert gender_entry["questionId"] == "q11011"  # 对外统一输出带 q 前缀
    assert gender_entry["totalAnswers"] == 2
    assert gender_entry["totalMale"] == 1
    assert gender_entry["totalFemale"] == 1
    cat_by_aid = {c["aid"]: c for c in gender_entry["answersCat"]}
    assert cat_by_aid["1101101"]["totalVotes"] == 1
    assert cat_by_aid["1101101"]["maleVotes"] == 1
    assert cat_by_aid["1101101"]["femaleVotes"] == 0
    assert cat_by_aid["1101102"]["femaleVotes"] == 1

    assert input_entry["questionId"] == "q11021"  # 裸码输入 -> 输出补回 q 前缀
    assert input_entry["answersStr"] == ["喜欢"]
    assert input_entry["totalAnswers"] == 1
    assert input_entry["totalMale"] == 1
    assert input_entry["totalFemale"] == 0


@pytest.mark.asyncio
async def test_query_questionnaire_not_computed_is_stable_error_not_empty_success(
    gql_schema_uncomputed,
) -> None:
    """全新部署(该年从未跑过 compute_all)时,queryQuestionnaire 必须报稳定的
    RESULT_NOT_COMPUTED,不能把"每道题都查不到"悄悄跳成一个看似成功的
    {entries: []}——两者是完全不同的状态,前者是"系统还没算过",后者是"算过了
    但这些具体题没人答"。"""
    result = await gql_schema_uncomputed.execute(
        QUERY_QUESTIONNAIRE,
        variable_values={"ids": ["q11011"], "voteYear": None},
    )
    assert result.errors is not None
    assert result.data is None
    error_kind = result.errors[0].extensions["error_kind"]
    assert error_kind == "RESULT_NOT_COMPUTED"


@pytest.mark.asyncio
async def test_query_questionnaire_trend_returns_empty_series_in_input_order(
    gql_schema,
) -> None:
    """后端没有问卷时间维度(compute_paper_results 不产出按小时数据),但真实
    前端按 [Trends!]! 消费这个字段(entries[0].trend);返回形状必须正确、
    数量与入参 questionIds 一致、顺序保留,内容退化成空(而不是报错或者
    返回 QueryQuestionnaireResponse 那种不匹配的形状)。"""
    result = await gql_schema.execute(
        QUERY_QUESTIONNAIRE_TREND,
        variable_values={"ids": ["q11011", "11021", "q99999"], "voteYear": None},
    )
    assert result.errors is None
    trends = result.data["queryQuestionnaireTrend"]
    assert len(trends) == 3  # 3 个入参 id -> 3 个出参条目(不跳过任何一个)
    for entry in trends:
        assert entry["trend"] == []
        assert entry["trendFirst"] == []
