"""双键 Whitelist 单元测试（设计稿 §4.2/§4.4）。"""
import pytest

from src.apps.result.whitelist import (
    SORT_ORDER_TAIL_BASE, Whitelist, WhitelistEntry,
)


def _entry(cid, old_id, name, sort=0):
    return WhitelistEntry(cid, cid, old_id, name, "", "", "旧作", None, None, sort)


def test_dual_token_hits_same_entry():
    wl = Whitelist([_entry(22, "4068b1c2", "博丽灵梦")])
    assert "22" in wl and "4068b1c2" in wl
    assert wl.get("22") is wl.get("4068b1c2")
    assert wl.canonical("4068b1c2") == "22"
    assert wl.canonical("22") == "22"
    assert wl.canonical("deadbeef") is None
    assert wl.name_of("4068b1c2") == "博丽灵梦"


def test_old_id_absent_only_candidate_token():
    wl = Whitelist([_entry(7, None, "无旧id角色")])
    assert "7" in wl
    assert wl.canonical("7") == "7"
    assert wl.ids == {"7"}


def test_token_collision_raises():
    # old_id 与另一条的 candidate_id 字符串同形 → 构造期必须炸
    with pytest.raises(ValueError):
        Whitelist([_entry(22, None, "甲"), _entry(9, "22", "乙")])


def test_sort_order_null_falls_to_tail_by_candidate_id():
    wl = Whitelist([
        WhitelistEntry(5, 5, None, "有序", "", "", "旧作", None, None, 3),
        WhitelistEntry(2, 2, None, "无序", "", "", "旧作", None, None,
                       SORT_ORDER_TAIL_BASE + 2),
    ])
    assert wl.system_id_of("5") == 3
    assert wl.system_id_of("2") == SORT_ORDER_TAIL_BASE + 2
