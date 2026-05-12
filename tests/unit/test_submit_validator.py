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

def test_validate_paper_ok():
    papers = json.dumps([{"id": 1, "answer": [2]}, {"id": 2, "answer_str": "男"}])
    data = PaperSubmitRest(papers_json=papers, meta=META)
    assert v.validate_paper(data) is data


def test_validate_paper_invalid_json():
    with pytest.raises(ValueError, match="合法 JSON"):
        v.validate_paper(PaperSubmitRest(papers_json="{not json", meta=META))


def test_validate_paper_empty_list():
    with pytest.raises(ValueError, match="非空列表"):
        v.validate_paper(PaperSubmitRest(papers_json="[]", meta=META))


def test_validate_paper_missing_id():
    with pytest.raises(ValueError, match="整数 id"):
        v.validate_paper(PaperSubmitRest(
            papers_json=json.dumps([{"question": 1}]), meta=META
        ))


def test_validate_paper_string_id_rejected():
    with pytest.raises(ValueError, match="整数 id"):
        v.validate_paper(PaperSubmitRest(
            papers_json=json.dumps([{"id": "not-int"}]), meta=META
        ))


def test_validate_paper_answer_str_too_long():
    with pytest.raises(ValueError, match="answer_str 过长"):
        v.validate_paper(PaperSubmitRest(
            papers_json=json.dumps([{"id": 1, "answer_str": "x" * 4097}]), meta=META
        ))


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
