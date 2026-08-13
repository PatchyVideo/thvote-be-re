"""result_compat.py 适配器层单元测试：CP ``member_names`` 缺失时的回退分支。

Task 6 review Finding 2：``_cp_ranking_entry_from_dict`` 在 ``member_names``
（compute_cp_ranking 产出的字段，见 compute.py）缺失时会回退用原始
id_a/id_b/id_c 展示，覆盖 Task 6 部署前算出的旧 Redis 缓存这种场景——不崩溃，
只是名字退化成 id token。之前该分支没有测试覆盖。
"""

from __future__ import annotations

from src.api.graphql.resolvers.result_compat import _cp_ranking_entry_from_dict

_ZERO_SEGMENT = {
    "vote_count": 0, "percentage_per_char": 0.0, "percentage_per_total": 0.0,
}


def _base_entry(**overrides: object) -> dict:
    """最小可用的 CP ranking dict——字段集合对齐 compute_cp_ranking() 的产出。"""
    entry = {
        "rank": [{
            "rank": 1, "vote_count": 10, "favorite_vote_count": 4,
            "favorite_percentage": 0.4, "vote_percentage": 0.5,
        }],
        "display_rank": 1,
        "vote_count": 10,
        "id_a": "aaaa1111",
        "id_b": "bbbb2222",
        "id_c": None,
        "favorite_vote_count_weighted": 14,
        "favorite_percentage": 0.4,
        "favorite_percentage_of_all": 0.3,
        "male_vote_count": dict(_ZERO_SEGMENT),
        "female_vote_count": dict(_ZERO_SEGMENT),
        "active_a": 0.6,
        "active_b": 0.4,
        "active_c": 0.0,
        "active_none": 0.0,
        "reasons": [],
        "reasons_count": 0,
        "trend": [],
        "trend_first": [],
    }
    entry.update(overrides)
    return entry


def test_cp_entry_without_member_names_falls_back_to_raw_id_tokens() -> None:
    """旧缓存没有 member_names 字段——不崩溃,退化用 id_a/id_b(/id_c)展示。"""
    e = _base_entry()
    assert "member_names" not in e

    entry = _cp_ranking_entry_from_dict(e)

    assert entry.cp.a == "aaaa1111"
    assert entry.cp.b == "bbbb2222"
    assert entry.cp.c is None


def test_cp_entry_without_member_names_covers_three_member_case() -> None:
    """3 人 CP(id_c 非空)同样要能从原始 id 回退,不能只覆盖 2 人场景。"""
    e = _base_entry(id_c="cccc3333")

    entry = _cp_ranking_entry_from_dict(e)

    assert entry.cp.a == "aaaa1111"
    assert entry.cp.b == "bbbb2222"
    assert entry.cp.c == "cccc3333"


def test_cp_entry_with_member_names_uses_names_not_raw_ids() -> None:
    """member_names 存在(新缓存的正常路径)时优先用人名,不落回 id token。"""
    e = _base_entry(
        id_c="cccc3333",
        member_names=["角色甲", "角色乙", "角色丙"],
    )

    entry = _cp_ranking_entry_from_dict(e)

    assert entry.cp.a == "角色甲"
    assert entry.cp.b == "角色乙"
    assert entry.cp.c == "角色丙"
