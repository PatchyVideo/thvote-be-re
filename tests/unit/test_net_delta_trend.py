"""net_delta_trends 纯函数——真实净增量 trend 的核心语义(B-050-后补2 Step 2)。

历史行 = (vote_id, created_at, attempt, items);对每个选民按
(created_at, attempt) 升序遍历快照序列做集合 diff:首快照全体 +1,
后续快照新增 +1、消失 -1,落在该快照的小时桶;trend_first 对本命
子集同理。核心不变量:任一 key 全桶净增量之和 == 最终快照里的计数。
"""

import random
from collections import Counter
from datetime import datetime, timedelta, timezone

from src.apps.result.trend import net_delta_trends

VS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _h(vid, hours, att, ids, first=None):
    items = [{"id": i, "first": (i == first)} for i in ids]
    return (vid, VS + timedelta(hours=hours), att, items)


def _keys(item):
    return [item["id"]]


def _first(item):
    return bool(item.get("first"))


def test_add_then_remove_produces_negative_bucket():
    hist = [_h("v1", 0, 1, ["A", "B"]), _h("v1", 3, 2, ["A"])]  # 第3小时撤掉B
    t = net_delta_trends(hist, _keys, _first, VS, 720)
    assert t["B"]["trend"] == [{"hrs": 0, "cnt": 1}, {"hrs": 3, "cnt": -1}]
    assert t["A"]["trend"] == [{"hrs": 0, "cnt": 1}]  # 未变动不重复计


def test_first_flag_migration():
    hist = [
        _h("v1", 0, 1, ["A", "B"], first="A"),
        _h("v1", 2, 2, ["A", "B"], first="B"),  # 本命 A→B
    ]
    t = net_delta_trends(hist, _keys, _first, VS, 720)
    assert t["A"]["trend_first"] == [{"hrs": 0, "cnt": 1}, {"hrs": 2, "cnt": -1}]
    assert t["B"]["trend_first"] == [{"hrs": 2, "cnt": 1}]
    assert t["A"]["trend"] == [{"hrs": 0, "cnt": 1}]  # 总票不受本命转移影响
    assert t["B"]["trend"] == [{"hrs": 0, "cnt": 1}]


def test_single_snapshot_degenerates_to_approximation():
    hist = [_h("v1", 5, 1, ["A"])]
    t = net_delta_trends(hist, _keys, _first, VS, 720)
    assert t["A"]["trend"] == [{"hrs": 5, "cnt": 1}]
    assert t["A"]["trend_first"] == []


def test_same_hour_add_remove_cancels_to_no_bucket():
    # 同一小时内加了又撤 → 净增量 0,稀疏输出不含该桶(cnt==0 不输出)。
    hist = [_h("v1", 0, 1, ["A", "B"]), _h("v1", 0, 2, ["A"])]
    t = net_delta_trends(hist, _keys, _first, VS, 720)
    assert "B" not in t or t["B"]["trend"] == []


def test_same_timestamp_ordered_by_attempt():
    # created_at 完全相同(同秒提交)时 attempt 决定先后。
    hist = [_h("v1", 1, 2, ["B"]), _h("v1", 1, 1, ["A"])]
    t = net_delta_trends(hist, _keys, _first, VS, 720)
    # 正序应为 attempt1(A) → attempt2(B):A +1-1,B +1
    assert t["A"]["trend"] == []
    assert t["B"]["trend"] == [{"hrs": 1, "cnt": 1}]


def test_out_of_window_clamped():
    hist = [_h("v1", -9, 1, ["A"]), _h("v1", 9999, 2, [])]
    t = net_delta_trends(hist, _keys, _first, VS, 10)
    assert t["A"]["trend"] == [{"hrs": 0, "cnt": 1}, {"hrs": 9, "cnt": -1}]


def test_naive_timestamp_treated_as_utc():
    hist = [("v1", datetime(2026, 1, 1, 2, 0, 0), 1, [{"id": "A"}])]
    t = net_delta_trends(hist, _keys, _first, VS, 720)
    assert t["A"]["trend"] == [{"hrs": 2, "cnt": 1}]


def test_multi_member_tuple_keys_and_empty_keys_dropped():
    # CP 场景:item_keys 返回 tuple key;白名单外返回 [] 表示整条丢弃。
    def cp_keys(item):
        if item.get("bad"):
            return []
        return [tuple(sorted([item["a"], item["b"]]))]

    hist = [
        ("v1", VS, 1, [{"a": "x", "b": "y"}, {"a": "q", "b": "r", "bad": True}]),
        ("v1", VS + timedelta(hours=1), 2, [{"a": "y", "b": "x"}]),  # 无序同 key
    ]
    t = net_delta_trends(hist, cp_keys, _first, VS, 720)
    assert t[("x", "y")]["trend"] == [{"hrs": 0, "cnt": 1}]
    assert all(not isinstance(k, tuple) or k == ("x", "y") for k in t)


def test_invariant_net_sum_equals_final_count_random_edits():
    rng = random.Random(42)
    pool = ["A", "B", "C", "D"]
    hist = []
    final: Counter = Counter()
    for v in range(30):
        picks: list[str] = []
        n_edits = rng.randint(1, 4)
        hours = 0
        for att in range(1, n_edits + 1):
            picks = rng.sample(pool, rng.randint(1, 3))
            hours += rng.randint(1, 20)  # 时间严格递增 → "最终快照"无歧义
            hist.append(_h(f"v{v}", hours, att, picks))
        final.update(picks)  # 最后一次快照 = 终榜口径
    t = net_delta_trends(hist, _keys, _first, VS, 720)
    for k in pool:
        got = sum(x["cnt"] for x in t.get(k, {"trend": []})["trend"])
        assert got == final[k], f"{k}: net={got} final={final[k]}"
