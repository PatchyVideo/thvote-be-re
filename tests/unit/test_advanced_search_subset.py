"""子集圈选单测:事实索引 / 名字解析 / AST 求值(设计稿 §五/§六)。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.apps.result.advanced_search.dsl import parse_query
from src.apps.result.advanced_search.subset import (
    build_facts,
    evaluate_subset,
    resolve_names,
)
from src.apps.result.whitelist import Whitelist, WhitelistEntry
from src.common.exceptions import ValidationError

_DT = datetime(2026, 1, 2, tzinfo=timezone.utc)


def _entry(cid: int, name: str, name_jp: str = "") -> WhitelistEntry:
    return WhitelistEntry(
        candidate_id=cid, voteable_id=cid, old_id=None, name=name,
        name_jp=name_jp, origin="", type="", first_appearance=None,
        album=None, system_id=cid,
    )


@pytest.fixture
def char_wl() -> Whitelist:
    return Whitelist([_entry(1, "东风谷早苗", "東風谷早苗"), _entry(2, "博丽灵梦")])


@pytest.fixture
def music_wl() -> Whitelist:
    return Whitelist([_entry(10, "信仰是为了虚幻之人", "Native Faith")])


def _votes(*rows):
    """rows: (vote_id, [(id, first)])。"""
    return [
        (vid, _DT, [{"id": str(i), "first": f, "reason": None} for i, f in items])
        for vid, items in rows
    ]


@pytest.fixture
def facts(char_wl, music_wl):
    char_votes = _votes(
        ("u1", [(1, True), (2, False)]),   # 投早苗(本命)+灵梦
        ("u2", [(2, True)]),               # 只投灵梦(本命)
    )
    music_votes = _votes(("u1", [(10, False)]))
    q_votes = [
        ("u1", [{"id": "11011", "answer": ["1101101"], "answer_str": None}]),
        ("u3", [{"id": "11011", "answer": ["1101102"], "answer_str": None}]),
    ]
    return build_facts(char_votes, music_votes, [], q_votes, char_wl, music_wl)


class TestResolveNames:
    def test_resolves_name_and_name_jp(self, char_wl, music_wl):
        query = 'chars: ["東風谷早苗"] AND musics: ["Native Faith"]'
        node = parse_query(query)
        resolved = resolve_names(node, char_wl, music_wl)
        assert resolved[("character", "東風谷早苗")] == {"1"}
        assert resolved[("music", "Native Faith")] == {"10"}

    def test_unknown_name_raises_with_names_listed(self, char_wl, music_wl):
        query = 'chars: ["雾雨魔理沙"] AND musics: ["不存在的曲子"]'
        node = parse_query(query)
        with pytest.raises(ValidationError) as exc_info:
            resolve_names(node, char_wl, music_wl)
        assert exc_info.value.message == "ADVANCED_SEARCH_UNKNOWN_NAME"
        msg = exc_info.value.human_readable_message or ""
        assert "雾雨魔理沙" in msg


def _eval(query: str, facts, char_wl, music_wl) -> set[str]:
    node = parse_query(query)
    resolved = resolve_names(node, char_wl, music_wl)
    return evaluate_subset(node, facts, resolved)


class TestEvaluate:
    def test_chars_any_is_or_within_group(self, facts, char_wl, music_wl):
        result = _eval('chars: ["东风谷早苗", "博丽灵梦"]', facts, char_wl,
                       music_wl)
        assert result == {"u1", "u2"}

    def test_two_chars_atoms_anded_means_voted_both(
        self, facts, char_wl, music_wl
    ):
        result = _eval('chars: ["东风谷早苗"] AND chars: ["博丽灵梦"]',
                       facts, char_wl, music_wl)
        assert result == {"u1"}

    def test_chars_first(self, facts, char_wl, music_wl):
        result = _eval('chars_first="博丽灵梦"', facts, char_wl, music_wl)
        assert result == {"u2"}

    def test_cross_section_and_missing_section_is_false(
        self, facts, char_wl, music_wl
    ):
        # u2 没投音乐 → musics 原子判 False
        result1 = _eval('chars: ["博丽灵梦"] AND musics: ["Native Faith"]',
                        facts, char_wl, music_wl)
        assert result1 == {"u1"}
        result2 = _eval(
            'chars: ["东风谷早苗"] AND musics: ["Native Faith"]',
            facts, char_wl, music_wl
        )
        assert result2 == {"u1"}

    def test_q_cond_and_or(self, facts, char_wl, music_wl):
        result1 = _eval("q11011 = 1101101", facts, char_wl, music_wl)
        assert result1 == {"u1"}
        # u3 只答了问卷没投票,也在全集里
        result2 = _eval(
            'q11011 = 1101102 OR chars_first="博丽灵梦"',
            facts, char_wl, music_wl
        )
        assert result2 == {"u2", "u3"}

    def test_empty_subset(self, facts, char_wl, music_wl):
        result = _eval(
            'chars_first="东风谷早苗" AND chars_first="博丽灵梦"',
            facts, char_wl, music_wl
        )
        assert result == set()
