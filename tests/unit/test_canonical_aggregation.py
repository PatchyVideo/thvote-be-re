"""混合 id 格式聚合 + 丢弃分类（设计稿 §4.3）。"""
from datetime import datetime, timezone

from src.apps.result.compute import (
    classify_dropped_token, compute_cp_ranking, compute_ranking,
)
from src.apps.result.whitelist import Whitelist, WhitelistEntry

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _wl():
    return Whitelist([
        WhitelistEntry(22, 22, "4068b1c2", "灵梦", "", "", "旧作", None, None, 0),
        WhitelistEntry(31, 31, "aabbccdd", "魔理沙", "", "", "旧作", None, None, 1),
    ])


def test_mixed_formats_aggregate_to_one_entity():
    votes = [
        ("u1", T0, [{"id": "4068b1c2", "first": True}]),   # 旧格式
        ("u2", T0, [{"id": "22", "first": False}]),          # 新格式,同一实体
        ("u3", T0, [{"id": "undefined"}]),                   # 前端漂移期垃圾
        ("u4", T0, [{"id": "deadbeef"}]),                    # 8hex 未匹配
        ("u5", T0, [{"id": "999"}]),                         # 未知 candidateId
    ]
    ranking, gstats = compute_ranking(votes, _wl(), {}, {}, T0, 1)
    reimu = next(e for e in ranking if e["name"] == "灵梦")
    assert reimu["vote_count"] == 2          # 两种格式聚合
    assert gstats["dropped"] == {
        "legacy_8hex_unmatched": 1, "candidate_id_unknown": 1, "malformed": 1,
    }


def test_cp_multiset_not_split_by_format():
    votes = [
        ("u1", T0, [{"id_a": "4068b1c2", "id_b": "aabbccdd", "active": "a"}]),
        ("u2", T0, [{"id_a": "31", "id_b": "22", "active": "b"}]),
    ]
    ranking, _ = compute_cp_ranking(votes, _wl(), {}, {}, T0, 1)
    assert len(ranking) == 1                 # 同一无序组合,一个条目
    assert ranking[0]["vote_count"] == 2
    assert sorted(ranking[0]["member_names"]) == ["灵梦", "魔理沙"]


def test_classify():
    assert classify_dropped_token("deadbeef") == "legacy_8hex_unmatched"
    assert classify_dropped_token("999") == "candidate_id_unknown"
    assert classify_dropped_token("undefined") == "malformed"
    assert classify_dropped_token("") == "malformed"
