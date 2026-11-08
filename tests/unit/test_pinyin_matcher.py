"""Observable matching rules used by the voting selectors."""

import pytest

from src.apps.autocomplete.pinyin import contains, prepare_text


@pytest.mark.parametrize(("text", "query", "expected"), [
    ("雾雨魔理沙", "mls", True),
    ("雾雨魔理沙", "wuyumolisha", True),
    ("雾雨魔理沙", "mo理sha", True),
    ("博丽灵梦", "灵m", True),
    ("博丽灵梦", "博l灵m", True),
    ("十六夜咲夜", "siliuye", True),
    ("二小姐", "rxiaojie", True),
    ("路米", "lvmi", True),
    ("绿米", "lumi", True),
    ("啊米", "anmi", False),
    ("灵米", "limi", False),
    ("小米", "ximi", False),
    ("魔甲理沙", "mls", False),
    ("重行", "chongxing", True),
    ("重行", "zhonghang", True),
    ("雾雨魔理沙", "molish", True),
    ("Bad Apple!!", "bad apple", True),
    ("U.N.オーエンは彼女なのか？", "オーエン", True),
    ("Bad Apple!!", ".*", False),
    ("[demo]", "[", True),
    ("", "m", False),
    ("灵梦", "", True),
])
def test_contains(text, query, expected):
    assert contains(prepare_text(text), query) is expected
