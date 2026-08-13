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
    # active 用真实 token（不再是不命中任何人的占位符 "a"/"b"），顺带验证
    # active 归因也不因格式被拆分——两票的 active 都指向魔理沙（旧格式
    # old_id "aabbccdd" / 新格式 candidateId "31"），应合并进同一个桶。
    votes = [
        ("u1", T0, [{"id_a": "4068b1c2", "id_b": "aabbccdd", "active": "aabbccdd"}]),
        ("u2", T0, [{"id_a": "31", "id_b": "22", "active": "31"}]),
    ]
    ranking, _ = compute_cp_ranking(votes, _wl(), {}, {}, T0, 1)
    assert len(ranking) == 1                 # 同一无序组合,一个条目
    assert ranking[0]["vote_count"] == 2
    assert sorted(ranking[0]["member_names"]) == ["灵梦", "魔理沙"]
    # canonical key 排序后 "22"(灵梦) < "31"(魔理沙) → a=灵梦、b=魔理沙。
    assert ranking[0]["active_a"] == 0.0
    assert ranking[0]["active_b"] == 1.0     # 2/2 票都记到魔理沙,不管来源格式
    assert ranking[0]["active_none"] == 0.0


def test_cp_active_rate_mixed_format_attribution():
    """CP active 归因跨混合格式回归（review Finding 2）：同一 canonical 成员
    在一票里以旧格式(old_id)投出、在另一票里以新格式(candidateId)投出，且
    ``active`` 字段本身也分别用两种格式指向同一个人时，active 率必须正确
    合并到同一个 canonical 桶，不能因为格式不同被拆散或静默清零。
    """
    votes = [
        # 旧格式：id_a/id_b 都是 8-hex old_id，active 也是 old_id。
        ("u1", T0, [{"id_a": "4068b1c2", "id_b": "aabbccdd", "active": "4068b1c2"}]),
        # 新格式：id_a/id_b 都是 candidateId 十进制串，active 也是 candidateId。
        ("u2", T0, [{"id_a": "22", "id_b": "31", "active": "22"}]),
    ]
    ranking, _ = compute_cp_ranking(votes, _wl(), {}, {}, T0, 1)
    assert len(ranking) == 1
    entry = ranking[0]
    assert entry["vote_count"] == 2
    assert sorted(entry["member_names"]) == ["灵梦", "魔理沙"]
    # canonical key 排序后 "22"(灵梦) < "31"(魔理沙) → a=灵梦、b=魔理沙。
    assert entry["id_a"] == "22" and entry["id_b"] == "31"
    assert entry["active_a"] == 1.0   # 灵梦两票都主动,不管 old_id 还是 candidateId
    assert entry["active_b"] == 0.0
    assert entry["active_none"] == 0.0


def test_classify():
    assert classify_dropped_token("deadbeef") == "legacy_8hex_unmatched"
    assert classify_dropped_token("999") == "candidate_id_unknown"
    assert classify_dropped_token("undefined") == "malformed"
    assert classify_dropped_token("") == "malformed"


def test_classify_non_str_does_not_raise():
    # 历史 raw_submit 行里可能是裸 JSON 数字/布尔/None，不能让 TypeError
    # 冒出来把整年计票炸掉（review Finding 1）。
    assert classify_dropped_token(123) == "malformed"
    assert classify_dropped_token(True) == "malformed"
    assert classify_dropped_token(None) == "malformed"
    assert classify_dropped_token([1, 2]) == "malformed"


def test_compute_ranking_non_str_id_counts_malformed_not_crash():
    votes = [("u1", T0, [{"id": 123, "first": False}])]
    ranking, gstats = compute_ranking(votes, _wl(), {}, {}, T0, 1)
    assert ranking == []
    assert gstats["dropped"]["malformed"] == 1


def test_compute_cp_ranking_unhashable_id_counts_malformed_not_crash():
    # id_a 是 list（不可 hash），Whitelist._by_token 是 dict，未经 _as_token
    # 归一直接传给 dict.get 会 TypeError；这里验证不炸、按 malformed 计数。
    votes = [
        ("u1", T0, [{"id_a": ["x"], "id_b": "aabbccdd"}]),
        ("u2", T0, [{"id_a": ["x"], "id_b": "aabbccdd"}]),
    ]
    ranking, gstats = compute_cp_ranking(votes, _wl(), {}, {}, T0, 1)
    assert ranking == []
    assert gstats["dropped"]["malformed"] == 2
