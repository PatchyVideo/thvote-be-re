from src.apps.result.whitelist import Whitelist, WhitelistEntry, load_whitelist


def _wl() -> Whitelist:
    return Whitelist([
        WhitelistEntry(1, 1, "aaaa1111", "博丽灵梦", "博麗霊夢", "东方红魔乡",
                        "旧作", "19961103", None, 0),
        WhitelistEntry(2, 2, "bbbb2222", "雾雨魔理沙", "霧雨魔理沙", "东方封魔录",
                        "旧作", "19970815", None, 1),
    ])


def test_contains_and_ids():
    wl = _wl()
    assert "aaaa1111" in wl  # old_id 旧 token 仍可命中
    assert "1" in wl  # candidate_id 才是 canonical token
    assert "zzzz9999" not in wl
    assert wl.ids == {"1", "2"}  # ids 是 canonical token 集合，不是 old_id


def test_name_and_system_id_lookup():
    wl = _wl()
    assert wl.name_of("aaaa1111") == "博丽灵梦"
    assert wl.system_id_of("bbbb2222") == 1
    # 未知 id：name 原样返回、system_id 巨大（排最后）
    assert wl.name_of("zzzz9999") == "zzzz9999"
    assert wl.system_id_of("zzzz9999") == 10**9


def test_load_real_snapshot_character_count():
    wl = load_whitelist("character")
    assert len(wl.ids) == 244  # 与 candidate_character 一致
    # 系统ID 覆盖 0..243 连续
    sids = sorted(wl.system_id_of(i) for i in wl.ids)
    assert sids[0] == 0 and sids[-1] == 243


def test_load_real_snapshot_music_nonempty():
    wl = load_whitelist("music")
    assert len(wl.ids) > 0
