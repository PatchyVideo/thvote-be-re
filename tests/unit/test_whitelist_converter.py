import json
from pathlib import Path

from scripts.whitelist_to_import import convert

DATA = Path("src/apps/result/data")


def test_character_snapshot_converts_fully():
    raw = json.loads((DATA / "whitelist_character.json").read_text())
    rows = convert("character", raw)
    assert len(rows) == 244
    r0 = next(r for r in rows if r["name"] == "博丽灵梦")
    assert r0["old_id"] == "4068b1c2" and r0["sort_order"] == 0
    assert r0["work"] == "东方灵异传"        # work[0]
    assert all(set(r) <= {"name", "name_jp", "type", "old_id", "work",
                          "work_type", "sort_order", "first_appearance"}
               for r in rows)


def test_music_snapshot_converts_fully():
    raw = json.loads((DATA / "whitelist_music.json").read_text())
    rows = convert("music", raw)
    assert len(rows) == 612
    assert all(r.get("old_id") for r in rows)
    # 音乐 work ← album
    sample = next(r for r in rows if r["name"] == "A Sacred Lot")
    assert sample["work"] == "东方灵异传"
