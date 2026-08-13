"""高级搜索 DSL 解析单测(设计稿 §四/§五)。"""

from __future__ import annotations

import pytest

from src.apps.result.advanced_search.dsl import (
    And,
    CharAny,
    CharFirst,
    MusicAny,
    MusicFirst,
    Or,
    QCond,
    parse_query,
)
from src.common.exceptions import ValidationError


class TestAtoms:
    def test_q_cond(self):
        assert parse_query("q11011 = 1101101") == QCond(qcode="11011", ocode="1101101")

    def test_chars_any(self):
        node = parse_query('chars: ["东风谷早苗", "博丽灵梦"]')
        assert isinstance(node, CharAny)
        assert set(node.names) == {"东风谷早苗", "博丽灵梦"}

    def test_chars_first(self):
        assert parse_query('chars_first="东风谷早苗"') == CharFirst(name="东风谷早苗")

    def test_musics_any(self):
        node = parse_query('musics: ["信仰是为了虚幻之人", "Native Faith"]')
        assert isinstance(node, MusicAny)
        assert set(node.names) == {"信仰是为了虚幻之人", "Native Faith"}

    def test_musics_first(self):
        assert parse_query('musics_first="信仰是为了虚幻之人"') == MusicFirst(
            name="信仰是为了虚幻之人"
        )


class TestCombinators:
    def test_and_of_three(self):
        node = parse_query(
            'q11011 = 1101101 AND chars: ["东风谷早苗"] AND chars: ["博丽灵梦"]'
        )
        assert isinstance(node, And)
        assert len(node.children) == 3

    def test_or(self):
        node = parse_query('q11011 = 1101101 OR chars: ["东风谷早苗"]')
        assert isinstance(node, Or)
        assert len(node.children) == 2

    def test_and_binds_tighter_than_or(self):
        node = parse_query('q1 = 2 OR q3 = 4 AND q5 = 6')
        assert isinstance(node, Or)
        assert node.children[0] == QCond(qcode="1", ocode="2")
        assert isinstance(node.children[1], And)

    def test_parens_requirement_example(self):
        node = parse_query(
            '(q11011 = 1101101 AND chars: ["东风谷早苗"])'
            ' OR musics_first="信仰是为了虚幻之人"'
        )
        assert isinstance(node, Or)
        kinds = {type(c) for c in node.children}
        assert And in kinds and MusicFirst in kinds


class TestErrors:
    @pytest.mark.parametrize("bad", [
        "chars:[",                       # 括号不闭合
        'chars ["a"]',                   # 缺冒号
        "q11011 == 1101101",             # 双等号
        'chars: ["a"] and chars: ["b"]', # 小写 and 不是关键字
        "",                              # 空串不该走到解析(调用方保证),真走到也报语法错
    ])
    def test_syntax_error(self, bad: str):
        with pytest.raises(ValidationError) as exc_info:
            parse_query(bad)
        assert exc_info.value.message == "ADVANCED_SEARCH_SYNTAX_ERROR"

    def test_query_too_long(self):
        with pytest.raises(ValidationError) as exc_info:
            parse_query("q1 = 1 " + "OR q1 = 1 " * 200)  # > 1024 字符
        assert exc_info.value.message == "ADVANCED_SEARCH_TOO_COMPLEX"
