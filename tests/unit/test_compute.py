"""Unit tests for pure compute functions."""

from datetime import datetime, timedelta, timezone

import pytest

from src.apps.result.compute import (
    build_segment_map,
    compute_completion_rates,
    compute_covote,
    compute_global_stats,
)

VOTE_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
TOTAL_HOURS = 24 * 7  # 7-day voting window


def _dt(hour_offset: int) -> datetime:
    return VOTE_START + timedelta(hours=hour_offset)


# ── build_segment_map ─────────────────────────────────────────────────

def test_build_segment_map_basic():
    q_votes = [
        ("u1", [{"id": "11011", "answer": ["1101101"], "answer_str": None}]),
        ("u2", [{"id": "11011", "answer": ["1101102"], "answer_str": None}]),
        ("u3", [{"id": "11011", "answer": None, "answer_str": None}]),
        ("u4", [{"id": "other_q", "answer": ["1101101"], "answer_str": None}]),
    ]
    label_by_option = {"1101101": "male", "1101102": "female"}
    result = build_segment_map(q_votes, "11011", label_by_option)
    assert result["u1"] == "male"
    assert result["u2"] == "female"
    assert result["u3"] == "unknown"
    assert result["u4"] == "unknown"


def test_build_segment_map_answer_str_fallback():
    q_votes = [
        ("u1", [{"id": "11011", "answer": None, "answer_str": "1101101"}]),
    ]
    label_by_option = {"1101101": "male", "1101102": "female"}
    result = build_segment_map(q_votes, "11011", label_by_option)
    assert result["u1"] == "male"


# ── compute_ranking ───────────────────────────────────────────────────

CHAR_VOTES = [
    ("u1", _dt(1), [{"id": "Alice", "first": True,  "reason": "love her"},
                    {"id": "Bob",   "first": False, "reason": None}]),
    ("u2", _dt(2), [{"id": "Alice", "first": False, "reason": "cute"}]),
    ("u3", _dt(3), [{"id": "Bob",   "first": True,  "reason": None}]),
]


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
