"""Unit tests for candidate parse/validate/field-spec pure functions.

After the voteable refactor, candidate_* tables only have id, vote_year, voteable_id.
Metadata (name, origin, etc.) lives on voteable_* tables.
"""


# ── field specs ─────────────────────────────────────────────────────────────

def test_field_specs_character():
    from src.apps.admin.candidate_service import candidate_field_specs

    specs = candidate_field_specs("character")
    by_name = {s["name"]: s["required"] for s in specs}
    assert "id" not in by_name
    assert "vote_year" not in by_name
    # After voteable refactor: only voteable_id remains
    assert by_name["voteable_id"] is True
    assert "name" not in by_name       # moved to voteable
    assert "origin" not in by_name     # moved to work table


def test_field_specs_music():
    from src.apps.admin.candidate_service import candidate_field_specs

    by_name = {s["name"]: s["required"] for s in candidate_field_specs("music")}
    assert by_name["voteable_id"] is True
    assert "album" not in by_name      # moved to work table via voteable


def test_candidate_field_specs_excludes_merged_into():
    from src.apps.admin.candidate_service import candidate_field_specs

    character_names = [f["name"] for f in candidate_field_specs("character")]
    assert "merged_into" not in character_names
    assert "voteable_id" in character_names

    music_names = [f["name"] for f in candidate_field_specs("music")]
    assert "merged_into" not in music_names
    assert "voteable_id" in music_names


# ── parse_content ───────────────────────────────────────────────────────────

def test_parse_json_array():
    from src.apps.admin.candidate_service import parse_content

    rows, errs = parse_content("auto", '[{"voteable_id":"1"},{"voteable_id":"2"}]')
    assert errs == []
    assert rows == [{"voteable_id": "1"}, {"voteable_id": "2"}]


def test_parse_json_not_array():
    from src.apps.admin.candidate_service import parse_content

    rows, errs = parse_content("auto", '{"voteable_id":"1"}')
    assert rows == []
    assert errs and "数组" in errs[0]["reason"]


def test_parse_csv_with_header():
    from src.apps.admin.candidate_service import parse_content

    csv_text = "voteable_id\n100\n101\n"
    rows, errs = parse_content("auto", csv_text)
    assert errs == []
    assert rows[0]["voteable_id"] == "100"
    assert rows[1]["voteable_id"] == "101"


def test_parse_csv_quoted_comma():
    from src.apps.admin.candidate_service import parse_content

    # CSV parser handles quoted fields with commas
    csv_text = 'name,origin\n灵梦,"东方,红魔乡"\n'
    rows, errs = parse_content("auto", csv_text)
    assert errs == []
    assert rows[0]["origin"] == "东方,红魔乡"


def test_parse_empty():
    from src.apps.admin.candidate_service import parse_content

    rows, errs = parse_content("auto", "   ")
    assert rows == []
    assert errs


def test_parse_explicit_csv_format():
    from src.apps.admin.candidate_service import parse_content

    rows, errs = parse_content("csv", "voteable_id\n10\n")
    assert errs == []
    assert rows[0]["voteable_id"] == "10"


# ── validate_items ──────────────────────────────────────────────────────────

def test_validate_keeps_voteable_id():
    from src.apps.admin.candidate_service import validate_items

    rows = [{"voteable_id": "10", "name": "ignored", "unknown": "x"}]
    valid, rejected = validate_items("character", rows)
    # After refactor: only voteable_id is a valid column
    assert rejected == []
    assert valid == [{"voteable_id": "10"}]


def test_validate_missing_voteable_id_rejected():
    from src.apps.admin.candidate_service import validate_items

    rows = [{"voteable_id": "10"}, {"name": "no_id"}, {"voteable_id": "  "}]
    valid, rejected = validate_items("character", rows)
    assert len(valid) == 1
    assert valid[0]["voteable_id"] == "10"
    assert len(rejected) == 2
