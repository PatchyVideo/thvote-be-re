from datetime import datetime, timezone

from src.apps.result.compute import compute_cp_ranking
from src.apps.result.whitelist import Whitelist, WhitelistEntry

VS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _wl():
    return Whitelist([
        WhitelistEntry("A", "甲", "", "", "旧作", None, None, 0),
        WhitelistEntry("B", "乙", "", "", "旧作", None, None, 1),
        WhitelistEntry("C", "丙", "", "", "旧作", None, None, 2),
    ])


def _v(vid, items):
    return (vid, VS, items)


def test_unordered_key_merges_and_drops_singletons():
    # (A,B) 与 (B,A) 应合并为同一组合；共 2 票（≥2 保留）
    votes = [
        _v("u1", [{"id_a": "A", "id_b": "B"}]),
        _v("u2", [{"id_a": "B", "id_b": "A"}]),
    ]
    ranking, _ = compute_cp_ranking(votes, _wl(), {}, {}, VS, 1)
    assert len(ranking) == 1
    e = ranking[0]
    assert e["id_a"] == "A" and e["id_b"] == "B"  # 排序后
    assert e["name"] == "甲×乙"
    assert e["rank"][0]["vote_count"] == 2


def test_singleton_cp_excluded():
    votes = [_v("u1", [{"id_a": "A", "id_b": "B"}])]  # 只有1票
    ranking, _ = compute_cp_ranking(votes, _wl(), {}, {}, VS, 1)
    assert ranking == []  # 组合票数为1不计入


def test_drop_cp_if_any_member_unknown():
    votes = [
        _v("u1", [{"id_a": "A", "id_b": "UNKNOWN"}]),
        _v("u2", [{"id_a": "A", "id_b": "UNKNOWN"}]),
    ]
    ranking, _ = compute_cp_ranking(votes, _wl(), {}, {}, VS, 1)
    assert ranking == []


def test_active_rates_by_position_sum_100():
    # (A,B) 4票：2票A主动、1票B主动、1票无主动
    votes = [
        _v("u1", [{"id_a": "A", "id_b": "B", "active": "A"}]),
        _v("u2", [{"id_a": "A", "id_b": "B", "active": "A"}]),
        _v("u3", [{"id_a": "A", "id_b": "B", "active": "B"}]),
        _v("u4", [{"id_a": "A", "id_b": "B"}]),
    ]
    ranking, _ = compute_cp_ranking(votes, _wl(), {}, {}, VS, 1)
    e = ranking[0]
    assert e["active_a"] == 0.5    # 2/4
    assert e["active_b"] == 0.25   # 1/4
    assert e["active_c"] == 0.0    # 无C
    assert e["active_none"] == 0.25
    assert round(e["active_a"] + e["active_b"] + e["active_c"] + e["active_none"], 4) == 1.0


def test_self_cp_preserved():
    # (A,A) 自CP：multiset 保留重复，2票
    votes = [
        _v("u1", [{"id_a": "A", "id_b": "A"}]),
        _v("u2", [{"id_a": "A", "id_b": "A"}]),
    ]
    ranking, _ = compute_cp_ranking(votes, _wl(), {}, {}, VS, 1)
    assert len(ranking) == 1
    assert ranking[0]["id_a"] == "A" and ranking[0]["id_b"] == "A"
    assert ranking[0]["name"] == "甲×甲"
