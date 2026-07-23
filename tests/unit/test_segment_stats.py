"""Unit tests for segment (generalized gender) statistics.

Task 3: gender becomes just "the question designated as the demographic
axis" — build_segment_map replaces compute_gender_map, and compute_ranking /
compute_cp_ranking / compute_paper_results all accept a segment_map keyed by
arbitrary labels (not just male/female), while still projecting the legacy
male_vote_count / female_vote_count fields for existing consumers.
"""

from datetime import datetime, timezone

from src.apps.result.compute import (
    build_segment_map,
    compute_cp_ranking,
    compute_paper_results,
    compute_ranking,
)
from src.apps.result.whitelist import Whitelist, WhitelistEntry

VS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _wl():
    return Whitelist([
        WhitelistEntry("id_a", "角色甲", "", "", "旧作", None, None, 0),
        WhitelistEntry("id_b", "角色乙", "", "", "旧作", None, None, 1),
    ])


def _vote(vid, items):
    return (vid, VS, items)


def _v(vid, items):
    return (vid, VS, items)


def test_build_segment_map():
    q_votes = [
        ("u1", [{"id": "11011", "answer": ["1101101"], "answer_str": None}]),
        ("u2", [{"id": "11011", "answer": ["1101102"], "answer_str": None}]),
        ("u3", [{"id": "11021", "answer": ["1102101"], "answer_str": None}]),  # 别的题
    ]
    m = build_segment_map(q_votes, "11011", {"1101101": "male", "1101102": "female"})
    assert m == {"u1": "male", "u2": "female", "u3": "unknown"}


def test_ranking_segments_and_legacy_projection():
    # u1=male 投 id_a；u2=female 投 id_a → id_a segments male1/female1
    votes = [_vote("u1", [{"id": "id_a"}]), _vote("u2", [{"id": "id_a"}])]
    seg = {"u1": "male", "u2": "female"}
    ranking, _ = compute_ranking(votes, _wl(), seg, {}, VS, 1)
    e = ranking[0]
    assert e["segments"]["male"]["vote_count"] == 1
    assert e["segments"]["female"]["vote_count"] == 1
    # legacy 投影仍在
    assert e["male_vote_count"]["vote_count"] == 1
    assert e["female_vote_count"]["vote_count"] == 1


def test_cp_ranking_has_gender_fields():
    votes = [_v("u1", [{"id_a": "id_a", "id_b": "id_b"}]),
             _v("u2", [{"id_a": "id_a", "id_b": "id_b"}])]
    ranking, _ = compute_cp_ranking(votes, _wl(), {"u1": "male"}, {}, VS, 1)
    e = ranking[0]
    assert e["male_vote_count"]["vote_count"] == 1
    assert e["female_vote_count"]["vote_count"] == 0


# ── MUST FIX 2 回归(2026-07-19 fix-wave):percentage_per_total 分母必须是
# 该 label 自己的总人数，不是全体投票人数 ─────────────────────────────────


def test_percentage_per_total_uses_per_label_denominator_not_total_voters():
    # 4 个投票人：2 男(u1 投 id_a、u2 投 id_b) + 2 女(u3、u4 都投 id_a)。
    # id_a 的 male 分段：vote_count=1，分母=total_male=2 → percentage_per_total=0.5。
    # 若误用全体投票人数(4)做分母会得到 0.25——这条测试专门抓这个回归
    # （旧网关口径 male_percentage_per_total = male_count / total_male，
    # "占总体男性比例"，不是"占全体人数比例"）。
    votes = [
        _vote("u1", [{"id": "id_a"}]),
        _vote("u2", [{"id": "id_b"}]),
        _vote("u3", [{"id": "id_a"}]),
        _vote("u4", [{"id": "id_a"}]),
    ]
    seg = {"u1": "male", "u2": "male", "u3": "female", "u4": "female"}
    ranking, _ = compute_ranking(votes, _wl(), seg, {}, VS, 1)
    e = next(x for x in ranking if x["id"] == "id_a")
    assert e["segments"]["male"]["percentage_per_total"] == 0.5


def test_paper_results_gender_crosstab():
    q_votes = [
        ("u1", [{"id": "11011", "answer": ["1101101"], "answer_str": None}]),
        ("u2", [{"id": "11011", "answer": ["1101102"], "answer_str": None}]),
    ]
    seg = {"u1": "male", "u2": "female"}
    res = compute_paper_results(q_votes, seg)
    q = res["11011"]
    assert q["total_male"] == 1 and q["total_female"] == 1
    cat = {c["aid"]: c for c in q["answers_cat"]}
    assert cat["1101101"]["male_votes"] == 1 and cat["1101101"]["female_votes"] == 0
