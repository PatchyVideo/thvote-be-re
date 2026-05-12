"""Unit tests for pure compute functions."""

from datetime import datetime, timedelta, timezone

import pytest

from src.apps.result.compute import (
    CandidateMeta,
    compute_completion_rates,
    compute_covote,
    compute_cp_ranking,
    compute_gender_map,
    compute_global_stats,
    compute_paper_results,
    compute_ranking,
)

VOTE_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
TOTAL_HOURS = 24 * 7  # 7-day voting window


def _dt(hour_offset: int) -> datetime:
    return VOTE_START + timedelta(hours=hour_offset)


# ── compute_gender_map ────────────────────────────────────────────────

def test_compute_gender_map_basic():
    q_votes = [
        ("u1", [{"id": "q11011", "answer": ["male"], "answer_str": None}]),
        ("u2", [{"id": "q11011", "answer": ["female"], "answer_str": None}]),
        ("u3", [{"id": "q11011", "answer": None, "answer_str": None}]),
        ("u4", [{"id": "other_q", "answer": ["male"], "answer_str": None}]),
    ]
    result = compute_gender_map(q_votes, "q11011", "male", "female")
    assert result["u1"] == "male"
    assert result["u2"] == "female"
    assert result["u3"] == "unknown"
    assert result["u4"] == "unknown"


def test_compute_gender_map_answer_str_fallback():
    q_votes = [
        ("u1", [{"id": "q11011", "answer": None, "answer_str": "male"}]),
    ]
    result = compute_gender_map(q_votes, "q11011", "male", "female")
    assert result["u1"] == "male"


# ── compute_ranking ───────────────────────────────────────────────────

CANDIDATES = {
    "Alice": CandidateMeta(name="Alice", name_jp="アリス", origin="EoSD", type="旧作", first_appearance="2002"),
    "Bob":   CandidateMeta(name="Bob",   name_jp="ボブ",   origin="PCB",  type="旧作", first_appearance="2003"),
}

CHAR_VOTES = [
    ("u1", _dt(1), [{"id": "Alice", "first": True,  "reason": "love her"},
                    {"id": "Bob",   "first": False, "reason": None}]),
    ("u2", _dt(2), [{"id": "Alice", "first": False, "reason": "cute"}]),
    ("u3", _dt(3), [{"id": "Bob",   "first": True,  "reason": None}]),
]
GENDER_MAP = {"u1": "male", "u2": "female", "u3": "male"}


def test_compute_ranking_vote_counts():
    ranking, global_stats = compute_ranking(
        CHAR_VOTES, CANDIDATES, GENDER_MAP, {}, VOTE_START, TOTAL_HOURS
    )
    by_name = {e["name"]: e for e in ranking}
    assert by_name["Alice"]["rank"][0]["vote_count"] == 2
    assert by_name["Bob"]["rank"][0]["vote_count"] == 2
    assert by_name["Alice"]["rank"][0]["favorite_vote_count"] == 1
    assert by_name["Bob"]["rank"][0]["favorite_vote_count"] == 1


def test_compute_ranking_reasons():
    ranking, _ = compute_ranking(
        CHAR_VOTES, CANDIDATES, GENDER_MAP, {}, VOTE_START, TOTAL_HOURS
    )
    by_name = {e["name"]: e for e in ranking}
    assert "love her" in by_name["Alice"]["reasons"]
    assert "cute" in by_name["Alice"]["reasons"]
    assert by_name["Bob"]["reasons"] == []


def test_compute_ranking_gender_breakdown():
    ranking, _ = compute_ranking(
        CHAR_VOTES, CANDIDATES, GENDER_MAP, {}, VOTE_START, TOTAL_HOURS
    )
    by_name = {e["name"]: e for e in ranking}
    assert by_name["Alice"]["male_vote_count"]["vote_count"] == 1   # u1
    assert by_name["Alice"]["female_vote_count"]["vote_count"] == 1  # u2


def test_display_rank_ties():
    # All 3 users vote differently — Alice, Bob, and Carol each get 1 vote / 0 first → tied
    votes = [
        ("u1", _dt(1), [{"id": "Alice", "first": False, "reason": None}]),
        ("u2", _dt(2), [{"id": "Bob",   "first": False, "reason": None}]),
        ("u3", _dt(3), [{"id": "Carol", "first": False, "reason": None}]),
    ]
    candidates = {
        "Alice": CandidateMeta("Alice", "", "", "", None),
        "Bob":   CandidateMeta("Bob",   "", "", "", None),
        "Carol": CandidateMeta("Carol", "", "", "", None),
    }
    ranking, _ = compute_ranking(votes, candidates, {}, {}, VOTE_START, TOTAL_HOURS)
    display_ranks = sorted(e["display_rank"] for e in ranking)
    # All tied → all should be display_rank 1
    assert display_ranks == [1, 1, 1]
    # Add a 4th entity with different score
    votes2 = votes + [("u4", _dt(4), [{"id": "Dave", "first": True, "reason": None}])]
    candidates2 = {**candidates, "Dave": CandidateMeta("Dave", "", "", "", None)}
    ranking2, _ = compute_ranking(votes2, candidates2, {}, {}, VOTE_START, TOTAL_HOURS)
    dave = next(e for e in ranking2 if e["name"] == "Dave")
    others = [e for e in ranking2 if e["name"] != "Dave"]
    assert dave["display_rank"] == 1  # Dave has first=True, highest weighted score
    assert all(e["display_rank"] == 2 for e in others)  # Others all tie at position 2


def test_compute_ranking_metadata_filled():
    ranking, _ = compute_ranking(
        CHAR_VOTES, CANDIDATES, GENDER_MAP, {}, VOTE_START, TOTAL_HOURS
    )
    alice = next(e for e in ranking if e["name"] == "Alice")
    assert alice["type"] == "旧作"
    assert alice["origin"] == "EoSD"
    assert alice["name_jp"] == "アリス"


def test_compute_ranking_unknown_candidate_fallback():
    votes = [("u1", _dt(1), [{"id": "Unknown", "first": False, "reason": None}])]
    ranking, _ = compute_ranking(votes, {}, {}, {}, VOTE_START, TOTAL_HOURS)
    assert ranking[0]["type"] == "未知"
    assert ranking[0]["origin"] == "未知"


def test_compute_historical_delta():
    historical = {
        "Alice": {"rank_1": 3, "votes_1": 80, "first_1": 20, "rank_2": 5, "votes_2": 60, "first_2": 15}
    }
    ranking, _ = compute_ranking(
        CHAR_VOTES, CANDIDATES, GENDER_MAP, historical, VOTE_START, TOTAL_HOURS
    )
    alice = next(e for e in ranking if e["name"] == "Alice")
    assert len(alice["rank"]) == 3  # current + 2 historical snapshots
    assert alice["rank"][1]["rank"] == 3  # last year


# ── compute_global_stats ──────────────────────────────────────────────

def test_compute_global_stats():
    music_votes = [("u1", _dt(1), [{"id": "Song A", "first": True, "reason": None}])]
    cp_votes = []
    # questionnaire_votes are 2-tuples (user_id, list[dict]) — no datetime
    q_votes = [("u1", [{"id": "q11011", "answer": ["male"], "answer_str": None}])]
    gender_map = {"u1": "male", "u3": "male"}
    stats = compute_global_stats(CHAR_VOTES, music_votes, cp_votes, q_votes, gender_map)
    assert stats["num_vote"] == 3   # 3 distinct users voted chars
    assert stats["num_char"] == 3
    assert stats["num_music"] == 1
    assert stats["num_male"] == 2   # u1, u3


# ── compute_completion_rates ──────────────────────────────────────────

def test_compute_completion_rates():
    all_voters = {"u1", "u2", "u3"}
    music_votes = [("u1", _dt(1), [])]
    cp_votes = []
    q_votes = []
    rates = compute_completion_rates(
        CHAR_VOTES, music_votes, cp_votes, q_votes, all_voters
    )
    assert rates["character"] == pytest.approx(1.0)   # 3/3
    assert rates["music"] == pytest.approx(1/3)        # 1/3
    assert rates["cp"] == pytest.approx(0.0)


# ── compute_covote ────────────────────────────────────────────────────

def test_compute_covote():
    votes = [
        ("u1", _dt(1), [{"id": "Alice", "first": False, "reason": None},
                         {"id": "Bob",   "first": False, "reason": None}]),
        ("u2", _dt(2), [{"id": "Alice", "first": False, "reason": None}]),
        ("u3", _dt(3), [{"id": "Bob",   "first": False, "reason": None}]),
    ]
    items = compute_covote(votes, top_k=10)
    pair = next((i for i in items if set([i["a"], i["b"]]) == {"Alice", "Bob"}), None)
    assert pair is not None
    assert pair["m11"] == 1  # u1 voted both
    assert pair["m10"] == 1  # u2 voted only Alice
    assert pair["m01"] == 1  # u3 voted only Bob


# ── compute_cp_ranking ────────────────────────────────────────────────

def test_compute_cp_ranking():
    cp_votes = [
        ("u1", _dt(1), [{"id_a": "A", "id_b": "B", "id_c": None, "active": "A", "first": True, "reason": None}]),
        ("u2", _dt(2), [{"id_a": "A", "id_b": "B", "id_c": None, "active": "B", "first": False, "reason": None}]),
    ]
    ranking, global_stats = compute_cp_ranking(cp_votes, {}, {}, VOTE_START, TOTAL_HOURS)
    assert len(ranking) == 1
    assert ranking[0]["id_a"] == "A"
    assert ranking[0]["id_b"] == "B"
    assert ranking[0]["rank"][0]["vote_count"] == 2
    assert ranking[0]["rank"][0]["favorite_vote_count"] == 1
