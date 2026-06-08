"""Tests for candidate merge detection (B-040)."""


def test_character_same_name_merges_to_min_id():
    from src.apps.admin.candidate_merge import detect_merges

    rows = [
        {"id": 5, "vote_year": 2026, "name": "灵梦", "album": None},
        {"id": 2, "vote_year": 2026, "name": "灵梦", "album": None},
        {"id": 9, "vote_year": 2026, "name": "魔理沙", "album": None},
    ]
    merges = detect_merges("character", rows)
    # id 5 (dup) → canonical 2 (min id of the 灵梦 group); 魔理沙 untouched
    assert (5, 2) in merges
    assert all(dup != 9 for dup, _ in merges)
    assert len(merges) == 1


def test_music_same_name_different_album_merges():
    from src.apps.admin.candidate_merge import detect_merges

    rows = [
        {"id": 3, "vote_year": 2026, "name": "U.N.オーエン", "album": "A"},
        {"id": 7, "vote_year": 2026, "name": "U.N.オーエン", "album": "B"},
    ]
    merges = detect_merges("music", rows)
    assert (7, 3) in merges
    assert len(merges) == 1


def test_no_duplicates_returns_empty():
    from src.apps.admin.candidate_merge import detect_merges

    rows = [
        {"id": 1, "vote_year": 2026, "name": "灵梦", "album": None},
        {"id": 2, "vote_year": 2026, "name": "魔理沙", "album": None},
    ]
    assert detect_merges("character", rows) == []


def test_different_years_not_merged():
    from src.apps.admin.candidate_merge import detect_merges

    rows = [
        {"id": 1, "vote_year": 2025, "name": "灵梦", "album": None},
        {"id": 2, "vote_year": 2026, "name": "灵梦", "album": None},
    ]
    assert detect_merges("character", rows) == []
