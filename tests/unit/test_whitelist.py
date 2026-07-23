from src.apps.result.whitelist import Whitelist, WhitelistEntry


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


# JSON 快照直读的两条测试(test_load_real_snapshot_character_count /
# test_load_real_snapshot_music_nonempty)随 Task 6 一并删除——它们验证的是
# 已退役的 load_whitelist() JSON loader；快照→DB 的等价覆盖见
# tests/integration/test_result_compute.py(经 seed_voteables_from_snapshot
# 导入通道 + load_whitelist_db 读回）。
