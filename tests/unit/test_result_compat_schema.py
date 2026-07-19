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
