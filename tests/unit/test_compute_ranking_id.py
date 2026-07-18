from datetime import datetime, timezone

from src.apps.result.compute import compute_ranking
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


def test_drops_unknown_ids():
    votes = [_vote("u1", [{"id": "id_a"}, {"id": "UNKNOWN"}])]
    ranking, _ = compute_ranking(votes, _wl(), {}, {}, VS, 1)
    names = {e["name"] for e in ranking}
    assert names == {"角色甲"}  # UNKNOWN 被丢


def test_sort_by_votes_then_first_then_system_id():
    # 甲: 2票0本命; 乙: 2票1本命; 丙: 2票1本命 → 乙丙同票同本命，按系统ID(乙1<丙2)乙在前
    votes = [
        _vote("u1", [{"id": "id_a"}, {"id": "id_b", "first": True}, {"id": "id_c", "first": True}]),
        _vote("u2", [{"id": "id_a"}, {"id": "id_b"}, {"id": "id_c"}]),
    ]
    ranking, _ = compute_ranking(votes, _wl(), {}, {}, VS, 1)
    order = [e["name"] for e in ranking]
    # 乙(2票1本命) / 丙(2票1本命) 在 甲(2票0本命) 之前；乙丙同名次按系统ID
    assert order == ["角色乙", "角色丙", "角色甲"]
    # 乙丙票数相同(2) → display_rank 相同(第1)，甲虚位到第3
    dr = {e["name"]: e["display_rank"] for e in ranking}
    assert dr["角色乙"] == 1 and dr["角色丙"] == 1 and dr["角色甲"] == 3


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
    assert e["favorite_percentage"] == 66.67  # 本命率 2/3
    assert e["rank"][0]["vote_count"] == 3
    # 票数占比 = 3/3 账号 = 100%
    assert e["rank"][0]["vote_percentage"] == 100.0


def test_favorite_percentage_of_all():
    # 甲2本命, 乙1本命 → 总本命票=3；甲本命占比=2/3
    votes = [
        _vote("u1", [{"id": "id_a", "first": True}]),
        _vote("u2", [{"id": "id_a", "first": True}]),
        _vote("u3", [{"id": "id_b", "first": True}]),
    ]
    ranking, _ = compute_ranking(votes, _wl(), {}, {}, VS, 1)
    by = {e["name"]: e for e in ranking}
    assert round(by["角色甲"]["favorite_percentage_of_all"], 4) == round(2 / 3, 4)
