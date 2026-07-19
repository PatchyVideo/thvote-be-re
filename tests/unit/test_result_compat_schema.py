"""排名查询契约桥 SDL 回归:三个 query* 字段签名 + CharacterOrMusicRanking.global。

参照 tests/unit/test_submit_bridge_schema.py 的写法(对 schema.as_str() 断言)。
前端(旧 Rust gateway)按名字严格校验,任何漂移都等于线上 'Cannot query field'。
签名来源:.superpowers/sdd/task-5-brief.md。
"""

from __future__ import annotations

import pytest

from src.api.graphql.schema import schema

EXPECTED_SIGNATURES = [
    # 三个排名查询,签名一致(voteStart 不使用/仅 schema 兼容;query 是高级搜索 DSL)
    (
        "queryCharacterRanking(voteStart: DateTimeUtc = null, voteYear: Int = null, "
        "query: String = null): CharacterOrMusicRanking!"
    ),
    (
        "queryMusicRanking(voteStart: DateTimeUtc = null, voteYear: Int = null, "
        "query: String = null): CharacterOrMusicRanking!"
    ),
    (
        "queryCPRanking(voteStart: DateTimeUtc = null, voteYear: Int = null, "
        "query: String = null): CPRanking!"
    ),
    # global（而非 global_，strawberry.field(name="global") 生效）
    "type CharacterOrMusicRanking {\n  entries: [RankingEntry!]!\n  global: RankingGlobal!\n}",
    "type CPRanking {\n  entries: [CPRankingEntry!]!\n  global: RankingGlobal!\n}",
    # Task 6：单条查询(按唯一序号 rank,不是 displayRank)
    (
        "queryCharacterSingle(rank: Int!, voteStart: DateTimeUtc = null, "
        "voteYear: Int = null, query: String = null): RankingEntry!"
    ),
    (
        "queryMusicSingle(rank: Int!, voteStart: DateTimeUtc = null, "
        "voteYear: Int = null, query: String = null): RankingEntry!"
    ),
    # 大写拼写 queryCPSingle(而非 queryCpSingle)—— strawberry.field(name=...) 生效
    (
        "queryCPSingle(rank: Int!, voteStart: DateTimeUtc = null, "
        "voteYear: Int = null, query: String = null): CPRankingEntry!"
    ),
    # 趋势:names 列表,顺序保留,无 query 参数(前端真实文档不传)
    (
        "queryCharacterTrend(names: [String!]!, voteStart: DateTimeUtc = null, "
        "voteYear: Int = null): [Trends!]!"
    ),
    (
        "queryMusicTrend(names: [String!]!, voteStart: DateTimeUtc = null, "
        "voteYear: Int = null): [Trends!]!"
    ),
    # 全局统计 / 完成率
    (
        "queryGlobalStats(voteStart: DateTimeUtc = null, voteYear: Int = null, "
        "query: String = null): ResultGlobalStats!"
    ),
    (
        "queryCompletionRates(voteStart: DateTimeUtc = null, voteYear: Int = null, "
        "query: String = null): CompletionRate!"
    ),
    # 问卷:questionsOfInterest / questionIds,均返回 QueryQuestionnaireResponse
    (
        "queryQuestionnaire(questionsOfInterest: [String!]!, "
        "voteStart: DateTimeUtc = null, voteYear: Int = null, "
        "query: String = null): QueryQuestionnaireResponse!"
    ),
    (
        "queryQuestionnaireTrend(questionIds: [String!]!, "
        "voteStart: DateTimeUtc = null, voteYear: Int = null, "
        "query: String = null): QueryQuestionnaireResponse!"
    ),
]


@pytest.mark.parametrize("signature", EXPECTED_SIGNATURES)
def test_result_compat_contract_pinned(signature: str) -> None:
    sdl = schema.as_str()
    assert signature in sdl, f"missing or drifted: {signature}"


def test_character_or_music_ranking_exposes_global_not_global_underscore() -> None:
    sdl = schema.as_str()
    block = sdl.split("type CharacterOrMusicRanking {")[1].split("}")[0]
    assert "global:" in block
    assert "global_" not in block
