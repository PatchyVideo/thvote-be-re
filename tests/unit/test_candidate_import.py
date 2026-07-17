"""Unit tests for candidate parse/validate/field-spec pure functions."""


# ── field specs ─────────────────────────────────────────────────────────────

def test_field_specs_character():
    from src.apps.admin.candidate_service import candidate_field_specs

    specs = candidate_field_specs("character")
    by_name = {s["name"]: s["required"] for s in specs}
    assert "id" not in by_name
    assert "vote_year" not in by_name
    assert by_name["name"] is True
    assert by_name["name_jp"] is False
    assert by_name["origin"] is False
    assert by_name["type"] is False
    assert by_name["first_appearance"] is False


def test_field_specs_music():
    from src.apps.admin.candidate_service import candidate_field_specs

    by_name = {s["name"]: s["required"] for s in candidate_field_specs("music")}
    assert by_name["name"] is True
    assert by_name["album"] is False
    assert "origin" not in by_name


def test_candidate_field_specs_excludes_merged_into():
    from src.apps.admin.candidate_service import candidate_field_specs

    character_names = [f["name"] for f in candidate_field_specs("character")]
    assert "merged_into" not in character_names
    assert "name" in character_names
    assert "name_jp" in character_names

    music_names = [f["name"] for f in candidate_field_specs("music")]
    assert "merged_into" not in music_names
    assert "name" in music_names


# ── parse_content ───────────────────────────────────────────────────────────

def test_parse_json_array():
    from src.apps.admin.candidate_service import parse_content

    rows, errs = parse_content("auto", '[{"name":"A"},{"name":"B"}]')
    assert errs == []
    assert rows == [{"name": "A"}, {"name": "B"}]


def test_parse_json_not_array():
    from src.apps.admin.candidate_service import parse_content

    rows, errs = parse_content("auto", '{"name":"A"}')
    assert rows == []
    assert errs and "数组" in errs[0]["reason"]


def test_parse_csv_with_header():
    from src.apps.admin.candidate_service import parse_content

    csv_text = "name,name_jp,type\n博丽灵梦,博麗霊夢,human\n雾雨魔理沙,霧雨魔理沙,human\n"
    rows, errs = parse_content("auto", csv_text)
    assert errs == []
    assert rows[0]["name"] == "博丽灵梦"
    assert rows[0]["name_jp"] == "博麗霊夢"
    assert rows[1]["name"] == "雾雨魔理沙"


def test_parse_csv_quoted_comma():
    from src.apps.admin.candidate_service import parse_content

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

    rows, errs = parse_content("csv", "name\nA\n")
    assert errs == []
    assert rows[0]["name"] == "A"


# ── validate_items ──────────────────────────────────────────────────────────

def test_validate_drops_empty_and_unknown():
    from src.apps.admin.candidate_service import validate_items

    rows = [{"name": "灵梦", "name_jp": "", "album": "x", "type": "human"}]
    valid, rejected = validate_items("character", rows)
    assert rejected == []
    assert valid == [{"name": "灵梦", "type": "human"}]


def test_validate_missing_name_rejected():
    from src.apps.admin.candidate_service import validate_items

    rows = [{"name": "灵梦"}, {"type": "human"}, {"name": "  "}]
    valid, rejected = validate_items("character", rows)
    assert len(valid) == 1
    assert valid[0]["name"] == "灵梦"
    assert len(rejected) == 2
    assert rejected[0]["line"] == 2
    assert rejected[1]["line"] == 3
    assert all("name" in r["reason"] for r in rejected)


def test_validate_music_keeps_album():
    from src.apps.admin.candidate_service import validate_items

    rows = [{"name": "曲", "album": "Scarlet", "origin": "x"}]
    valid, rejected = validate_items("music", rows)
    assert valid == [{"name": "曲", "album": "Scarlet"}]
