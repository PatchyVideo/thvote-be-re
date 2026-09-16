"""迁移工件与导入脚本纯函数单测（0019 voteable resources）。"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "import_voteable_resources.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("import_voteable_resources", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_merge_is_order_preserving_union():
    mod = _load_module()
    assert mod._merge(["a", "b"], ["b", "c"]) == ["a", "b", "c"]
    assert mod._merge(None, ["x", " x ", ""]) == ["x"]
    assert mod._merge(["a"], []) == ["a"]
    assert mod._merge([], []) == []


def test_artifact_matches_frontend_counts():
    """迁移工件应覆盖全部有资源的对象，且名称唯一。"""
    data = json.loads(
        (Path(__file__).resolve().parents[2] / "scripts"
         / "voteable_resources.json").read_text(encoding="utf-8")
    )
    chars, music = data["characters"], data["music"]
    # 角色里至少有 image 或 aliases 的才进工件：实测 177
    assert len(chars) == 177
    assert len(music) == 612
    assert len({c["name"] for c in chars}) == len(chars)
    assert len({m["name"] for m in music}) == len(music)
    # 曲目每条都应有试听
    assert all(m.get("music") for m in music)
    # URL 一律 http(s)
    for row in chars + music:
        for key in ("image", "music"):
            if row.get(key):
                assert row[key].startswith(("http://", "https://"))
