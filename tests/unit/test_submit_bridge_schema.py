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
    "submitDojin(content: DojinSubmitGQL!): DojinNominationResult!",
    # queries
    "getSubmitCharacterVote(voteToken: String!): CharacterSubmitRestQuery!",
    "getSubmitMusicVote(voteToken: String!): MusicSubmitRestQuery!",
    "getSubmitCPVote(voteToken: String!): CPSubmitRestQuery!",
    "getSubmitDojinVote(voteToken: String!): DojinSubmitRestQuery!",
    "getSubmitPaperVote(voteToken: String!): PaperSubmitRestQuery!",
    # 顶层输入类型字段(camelCase + 复数 musics 怪癖)
    (
        "input CharacterSubmitGQL {\n"
        "  voteToken: String!\n"
        "  characters: [CharacterSubmitInput!]!\n"
        "}"
    ),
    (
        "input MusicSubmitGQL {\n"
        "  voteToken: String!\n"
        "  musics: [MusicSubmitInput!]!\n"
        "}"
    ),
    (
        "input CPSubmitGQL {\n"
        "  voteToken: String!\n"
        "  cps: [CPSubmitInput!]!\n"
        "}"
    ),
    (
        "input PaperSubmitGQL {\n"
        "  voteToken: String!\n"
        "  paperJson: String!\n"
        "}"
    ),
    (
        "input DojinSubmitGQL {\n"
        "  voteToken: String!\n"
        "  dojins: [DojinSubmitItemGQL!]!\n"
        "}"
    ),
    # 回读结果字段(music 单数怪癖 + papersJson)
    "type MusicSubmitRestQuery {\n  music: [MusicSubmit!]!\n}",
    "type PaperSubmitRestQuery {\n  papersJson: String!\n}",
    "type CharacterSubmitRestQuery {\n  characters: [CharacterSubmit!]!\n}",
    "type CPSubmitRestQuery {\n  cps: [CPSubmit!]!\n}",
    "type DojinSubmitRestQuery {\n  dojins: [DojinSubmit!]!\n}",
    # 二创提名逐条结果(B-037)
    (
        "type DojinNominationResult {\n"
        "  accepted: Int!\n"
        "  rejected: [NominationItemResultGQL!]!\n"
        "  skipped: [NominationItemResultGQL!]!\n"
        "}"
    ),
]

DOJIN_ENUM_VALUES = [
    "MUSIC",
    "VIDEO",
    "DRAWING",
    "SOFTWARE",
    "ARTICLE",
    "CRAFT",
    "OTHER",
]


@pytest.mark.parametrize("signature", EXPECTED_SIGNATURES)
def test_submit_bridge_contract_pinned(signature: str) -> None:
    sdl = schema.as_str()
    assert signature in sdl, f"missing or drifted: {signature}"


def test_dojin_type_enum_values() -> None:
    sdl = schema.as_str()
    enum_block = sdl.split("enum DojinType {")[1].split("}")[0]
    for value in DOJIN_ENUM_VALUES:
        assert value in enum_block, f"missing DojinType enum value: {value}"
