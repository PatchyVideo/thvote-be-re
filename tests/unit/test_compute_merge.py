"""B-040: compute_ranking respects merge name remap."""
from datetime import datetime, timezone


def test_compute_ranking_merges_variant_votes():
    from src.apps.result.compute import CandidateMeta, compute_ranking

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    dt = datetime(2026, 1, 1, 1, tzinfo=timezone.utc)
    # two users: one votes "灵梦", one votes variant "博丽灵梦"
    votes = [
        ("u1", dt, [{"id": "灵梦", "first": True}]),
        ("u2", dt, [{"id": "博丽灵梦", "first": False}]),
    ]
    candidates = {"灵梦": CandidateMeta("灵梦", "", "", "", None)}
    remap = {"博丽灵梦": "灵梦"}

    ranking, _ = compute_ranking(
        votes, candidates, {}, {}, start, 24, remap
    )
    reimu = next(r for r in ranking if r["name"] == "灵梦")
    # both votes counted under canonical 灵梦
    assert reimu["rank"][0]["vote_count"] == 2
    # variant should not appear as its own entry
    assert all(r["name"] != "博丽灵梦" for r in ranking)
