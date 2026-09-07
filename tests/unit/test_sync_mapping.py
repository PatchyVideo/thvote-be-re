"""Tests for MongoDB → PostgreSQL field mapping functions."""
from datetime import datetime, timezone
from unittest.mock import MagicMock


def _oid(hex_str: str = "507f1f77bcf86cd799439011") -> MagicMock:
    m = MagicMock()
    m.__str__ = MagicMock(return_value=hex_str)
    return m


# ── raw_submit (generic) ──────────────────────────────────────────────────────

def test_map_raw_submit():
    from src.apps.admin.sync.runner import map_raw_submit

    oid = _oid("aabbccddeeff001122334455")
    doc = {
        "_id": oid,
        "characters": [{"id": "c1", "reason": "nice", "first": True}],
        "meta": {
            "vote_id": "voter123", "attempt": 2,
            "created_at": datetime(2024, 3, 1, tzinfo=timezone.utc),
            "user_ip": "10.0.0.1", "additional_fingreprint": "fp1",
        },
    }
    row = map_raw_submit(doc, "characters")

    assert row["legacy_mongo_id"] == "aabbccddeeff001122334455"
    assert row["vote_id"] == "voter123"
    assert row["attempt"] == 2
    assert row["user_ip"] == "10.0.0.1"
    assert row["payload"] == [{"id": "c1", "reason": "nice", "first": True}]


def test_map_raw_submit_missing_meta():
    from src.apps.admin.sync.runner import map_raw_submit

    doc = {"_id": _oid(), "music": [], "meta": {}}
    row = map_raw_submit(doc, "music")

    assert row["vote_id"] == ""
    assert row["attempt"] is None
    assert row["user_ip"] == "<unknown>"


# ── raw_paper ─────────────────────────────────────────────────────────────────

def test_map_raw_paper():
    from src.apps.admin.sync.runner import map_raw_paper

    doc = {
        "_id": _oid(), "papers_json": '{"q1": "a"}',
        "meta": {
            "vote_id": "v1", "attempt": 1,
            "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "user_ip": "1.1.1.1", "additional_fingreprint": None,
        },
    }
    row = map_raw_paper(doc)

    assert row["papers_json"] == '{"q1": "a"}'
    assert row["vote_id"] == "v1"


# ── final_ranking ─────────────────────────────────────────────────────────────

def test_map_final_ranking_char():
    from src.apps.admin.sync.runner import map_final_ranking

    doc = {"name": "Reimu", "vote_year": 2023, "rank": 1,
           "vote_count": 5000, "first_vote_count": 2000,
           "first_vote_percentage": 0.4, "vote_percentage": 0.05}
    row = map_final_ranking(doc, "character")

    assert row["category"] == "character"
    assert row["rank"] == 1
    assert row["vote_count"] == 5000
    assert "first_vote_percentage" not in row


# ── candidates ────────────────────────────────────────────────────────────────

def test_map_candidate_character():
    from src.apps.admin.sync.runner import map_candidate_character

    doc = {"vote_year": 2023, "name": "Reimu", "origname": "博麗霊夢",
           "date": 1996, "kind": ["human", "shrine_maiden"],
           "work": ["EoSD", "PCB"], "album": None}
    row = map_candidate_character(doc)

    assert row["name_jp"] == "博麗霊夢"
    assert row["type"] == "human"
    assert row["origin"] == "EoSD"
    assert row["first_appearance"] == "1996"


def test_map_candidate_character_empty_kind():
    from src.apps.admin.sync.runner import map_candidate_character

    doc = {"vote_year": 2023, "name": "X", "origname": "",
           "date": None, "kind": [], "work": [], "album": None}
    row = map_candidate_character(doc)

    assert row["type"] == ""
    assert row["origin"] == ""
    assert row["first_appearance"] is None


def test_map_candidate_music():
    from src.apps.admin.sync.runner import map_candidate_music

    doc = {"vote_year": 2023, "name": "U.N.オーエンは彼女なのか？",
           "origname": "U.N. Owen was Her?", "date": 2002,
           "kind": ["arrange"], "work": ["EoSD"], "album": "Scarlet"}
    row = map_candidate_music(doc)

    assert row["name_jp"] == "U.N. Owen was Her?"
    assert row["type"] == "arrange"
    assert row["album"] == "Scarlet"
    assert "origin" not in row
