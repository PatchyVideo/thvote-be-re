"""Unit tests for SubmitValidator."""

import json

import pytest

from src.apps.submit.schemas import (
    CPSubmit,
    CPSubmitRest,
    CharacterSubmit,
    CharacterSubmitRest,
    DojinSubmit,
    DojinSubmitRest,
    MusicSubmit,
    MusicSubmitRest,
    PaperSubmitRest,
    SubmitMetadata,
)
from src.apps.submit.service import SubmitValidator

v = SubmitValidator()
META = SubmitMetadata()


# ── character ──────────────────────────────────────────────────────────

def test_validate_character_ok():
    data = CharacterSubmitRest(
        characters=[CharacterSubmit(id="A", first=True, reason="good"),
                    CharacterSubmit(id="B")],
        meta=META,
    )
    assert v.validate_character(data) is data


def test_validate_character_too_many():
    chars = [CharacterSubmit(id=str(i)) for i in range(9)]
    with pytest.raises(ValueError, match="不在范围内"):
        v.validate_character(CharacterSubmitRest(characters=chars, meta=META))


def test_validate_character_too_few():
    with pytest.raises(ValueError, match="不在范围内"):
        v.validate_character(CharacterSubmitRest(characters=[], meta=META))


def test_validate_character_duplicate():
    chars = [CharacterSubmit(id="A"), CharacterSubmit(id="A")]
    with pytest.raises(ValueError, match="已存在"):
        v.validate_character(CharacterSubmitRest(characters=chars, meta=META))


def test_validate_character_multiple_first():
    chars = [CharacterSubmit(id="A", first=True), CharacterSubmit(id="B", first=True)]
    with pytest.raises(ValueError, match="多个本命"):
        v.validate_character(CharacterSubmitRest(characters=chars, meta=META))


def test_validate_character_reason_too_long():
    chars = [CharacterSubmit(id="A", reason="x" * 4097)]
    with pytest.raises(ValueError, match="理由过长"):
        v.validate_character(CharacterSubmitRest(characters=chars, meta=META))


# ── music ──────────────────────────────────────────────────────────────

def test_validate_music_ok():
    music = [MusicSubmit(id=str(i)) for i in range(5)]
    data = MusicSubmitRest(music=music, meta=META)
    assert v.validate_music(data) is data


def test_validate_music_too_many():
    music = [MusicSubmit(id=str(i)) for i in range(13)]
    with pytest.raises(ValueError, match="不在范围内"):
        v.validate_music(MusicSubmitRest(music=music, meta=META))


# ── cp ─────────────────────────────────────────────────────────────────

def test_validate_cp_ok():
    cps = [CPSubmit(id_a="A", id_b="B", active="A", first=True)]
    data = CPSubmitRest(cps=cps, meta=META)
    assert v.validate_cp(data) is data


def test_validate_cp_invalid_active():
    cps = [CPSubmit(id_a="A", id_b="B", active="C")]
    with pytest.raises(ValueError, match="主动方"):
        v.validate_cp(CPSubmitRest(cps=cps, meta=META))


def test_validate_cp_too_many():
    cps = [CPSubmit(id_a="A", id_b=str(i)) for i in range(5)]
    with pytest.raises(ValueError, match="不在范围内"):
        v.validate_cp(CPSubmitRest(cps=cps, meta=META))


# ── paper ──────────────────────────────────────────────────────────────
# papers_json 是不透明业务数据(前端真实载荷为嵌套对象,统计侧不读原始表),
# 只验「合法 JSON + UTF-8 ≤ 256KB」。旧的"非空列表+整数id"校验是按想象格式写的,
# 会拒掉真实前端载荷,已按 spec 2026-06-07 移除。


def test_validate_paper_accepts_real_frontend_payload():
    # 前端 Questionnaire.vue 实际提交的嵌套结构(精简版)
    payload = json.dumps({
        "mainQuestionnaire": {
            "requiredQuestionnaire": {
                "id": 11,
                "answers": [{"id": 11011, "options": [1, 2], "input": ""}],
            },
            "optionalQuestionnaire1": {"id": 12, "answers": []},
        },
        "extraQuestionnaire": {"exQuestionnaire1": {"id": 21, "answers": []}},
    })
    data = PaperSubmitRest(papers_json=payload, meta=META)
    assert v.validate_paper(data) is data


def test_validate_paper_accepts_any_valid_json_shape():
    # 列表、对象、甚至标量都放行——结构不归后端管
    for payload in ['[{"id": 1}]', "{}", '"just a string"']:
        data = PaperSubmitRest(papers_json=payload, meta=META)
        assert v.validate_paper(data) is data


def test_validate_paper_invalid_json():
    with pytest.raises(ValueError, match="不是合法 JSON"):
        v.validate_paper(PaperSubmitRest(papers_json="{not json", meta=META))


def test_validate_paper_oversize_rejected():
    big = json.dumps({"x": "a" * (256 * 1024)})  # 编码后必然 > 256KB
    with pytest.raises(ValueError, match="问卷数据过大"):
        v.validate_paper(PaperSubmitRest(papers_json=big, meta=META))


def test_validate_paper_exactly_at_limit_accepted():
    # 上限是严格大于(>):正好 256KB 必须通过,防住未来 > 改 >= 的 off-by-one
    overhead = len(json.dumps({"x": ""}).encode("utf-8"))
    payload = json.dumps({"x": "a" * (256 * 1024 - overhead)})
    assert len(payload.encode("utf-8")) == 256 * 1024
    data = PaperSubmitRest(papers_json=payload, meta=META)
    assert v.validate_paper(data) is data


# ── dojin ──────────────────────────────────────────────────────────────

def test_validate_dojin_ok():
    dojins = [DojinSubmit(dojin_type="manga", url="http://a.com",
                          title="T", author="A", reason="R")]
    data = DojinSubmitRest(dojins=dojins, meta=META)
    assert v.validate_dojin(data) is data


def test_validate_dojin_reason_too_long():
    dojins = [DojinSubmit(dojin_type="manga", url="http://a.com",
                          title="T", author="A", reason="x" * 4097)]
    with pytest.raises(ValueError, match="理由过长"):
        v.validate_dojin(DojinSubmitRest(dojins=dojins, meta=META))
