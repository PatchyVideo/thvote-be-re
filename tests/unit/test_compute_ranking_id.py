from datetime import datetime, timezone

from src.apps.result.compute import compute_cp_ranking, compute_ranking
from src.apps.result.whitelist import Whitelist, WhitelistEntry

VS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _wl():
    return Whitelist([
        WhitelistEntry("id_a", "角色甲", "", "", "旧作", None, None, 0),
        WhitelistEntry("id_b", "角色乙", "", "", "旧作", None, None, 1),
        WhitelistEntry("id_c", "角色丙", "", "", "旧作", None, None, 2),
    ])


def _vote(vid, items):
    return (vid, VS, items)


def test_dedup_same_id_within_one_vote():
    # 同一账号同一票内重复投同一 id 只计一次
    votes = [_vote("u1", [{"id": "id_a"}, {"id": "id_a", "first": True}])]
    ranking, _ = compute_ranking(votes, _wl(), {}, {}, VS, 1)
    assert len(ranking) == 1
    assert ranking[0]["id"] == "id_a"
    assert ranking[0]["rank"][0]["vote_count"] == 1


def test_drops_unknown_ids():
    votes = [_vote("u1", [{"id": "id_a"}, {"id": "UNKNOWN"}])]
    ranking, _ = compute_ranking(votes, _wl(), {}, {}, VS, 1)
    names = {e["name"] for e in ranking}
    assert names == {"角色甲"}  # UNKNOWN 被丢


def test_sort_by_votes_then_first_then_system_id():
    # 甲: 2票0本命; 乙: 2票1本命; 丙: 2票1本命 → 乙丙同票同本命，按系统ID(乙1<丙2)乙在前
    votes = [
        _vote("u1", [
            {"id": "id_a"},
            {"id": "id_b", "first": True},
            {"id": "id_c", "first": True},
        ]),
        _vote("u2", [{"id": "id_a"}, {"id": "id_b"}, {"id": "id_c"}]),
    ]
    ranking, _ = compute_ranking(votes, _wl(), {}, {}, VS, 1)
    order = [e["name"] for e in ranking]
    # 乙(2票1本命) / 丙(2票1本命) 在 甲(2票0本命) 之前；乙丙同名次按系统ID
    assert order == ["角色乙", "角色丙", "角色甲"]
    # 甲乙丙票数相同(2) → display_rank 全部相同(第1)，只按票数并列，本命数只影响组内顺序
    dr = {e["name"]: e["display_rank"] for e in ranking}
    assert dr["角色乙"] == 1 and dr["角色丙"] == 1 and dr["角色甲"] == 1  # 同票数(2)同名次


def test_metrics_weighted_and_ratios():
    # 甲: 3票2本命
    votes = [
        _vote("u1", [{"id": "id_a", "first": True}]),
        _vote("u2", [{"id": "id_a", "first": True}]),
        _vote("u3", [{"id": "id_a"}]),
    ]
    ranking, gstats = compute_ranking(votes, _wl(), {}, {}, VS, 1)
    e = ranking[0]
    assert e["id"] == "id_a" and e["name"] == "角色甲"
    assert e["favorite_vote_count_weighted"] == 3 + 2  # 票数+本命数
    # 百分比字段是 0..1 的分数(旧网关口径,前端自己 *100 拼 '%'),不是 0..100。
    assert e["favorite_percentage"] == 0.6667  # 本命率 2/3
    assert e["rank"][0]["vote_count"] == 3
    # 票数占比 = 3/3 账号 = 1.0(即 100%,但存的是分数)
    assert e["rank"][0]["vote_percentage"] == 1.0


def test_favorite_percentage_of_all():
    # 甲2本命, 乙1本命 → 总本命票=3；甲本命占比=2/3
    votes = [
        _vote("u1", [{"id": "id_a", "first": True}]),
        _vote("u2", [{"id": "id_a", "first": True}]),
        _vote("u3", [{"id": "id_b", "first": True}]),
    ]
    ranking, _ = compute_ranking(votes, _wl(), {}, {}, VS, 1)
    by = {e["name"]: e for e in ranking}
    # 本命占比 2/3 → 分数 0.6667,不是百分数 66.67
    assert by["角色甲"]["favorite_percentage_of_all"] == 0.6667


# ── MUST FIX 1 回归(2026-07-19 fix-wave):百分比字段必须是分数,不是 0..100 ──
#
# 前端 toPercentageString(num) = (num*100).toFixed(2)+'%' 自己乘 100；如果
# compute 已经乘过一次,前端会再乘一次，得到形如 8000.00% 这种荒谬值。


def test_vote_percentage_is_fraction_in_0_1_character():
    # 5 个投票人,4 个投 id_a → vote_percentage 必须是分数 0.8,不是 80.0
    votes = [
        _vote("u1", [{"id": "id_a"}]),
        _vote("u2", [{"id": "id_a"}]),
        _vote("u3", [{"id": "id_a"}]),
        _vote("u4", [{"id": "id_a"}]),
        _vote("u5", [{"id": "id_b"}]),
    ]
    ranking, _ = compute_ranking(votes, _wl(), {}, {}, VS, 1)
    e = next(x for x in ranking if x["id"] == "id_a")
    assert e["rank"][0]["vote_percentage"] == 0.8
    assert 0.0 <= e["rank"][0]["vote_percentage"] <= 1.0


def test_vote_percentage_is_fraction_in_0_1_cp():
    # 5 个 CP 投票人,4 个投 id_a×id_b → vote_percentage 必须是分数 0.8,不是 80.0；
    # 第 5 个投 id_a×id_c,组合票数==1 被排名过滤掉，但仍计入 total_voters 分母
    # （与 total_male/total_female 分母不同，vote_percentage 分母始终是全体
    # 本类别投票人数）。
    votes = [
        ("u1", VS, [{"id_a": "id_a", "id_b": "id_b"}]),
        ("u2", VS, [{"id_a": "id_a", "id_b": "id_b"}]),
        ("u3", VS, [{"id_a": "id_a", "id_b": "id_b"}]),
        ("u4", VS, [{"id_a": "id_a", "id_b": "id_b"}]),
        ("u5", VS, [{"id_a": "id_a", "id_b": "id_c"}]),
    ]
    ranking, _ = compute_cp_ranking(votes, _wl(), {}, {}, VS, 1)
    assert len(ranking) == 1  # id_a×id_c 只 1 票，被"组合票数==1 不计入"过滤
    e = ranking[0]
    assert e["rank"][0]["vote_percentage"] == 0.8
    assert 0.0 <= e["rank"][0]["vote_percentage"] <= 1.0
