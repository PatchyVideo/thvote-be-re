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


# ── cp structure rules (R-05 / PRD 2.5.4) ──────────────────────────────

def test_validate_cp_blank_member_rejected():
    with pytest.raises(ValueError, match="未填写的角色"):
        v.validate_cp(CPSubmitRest(
            cps=[CPSubmit(id_a="A", id_b="")], meta=META))


def test_validate_cp_duplicate_member_rejected():
    # 三人组合里有相同角色 → PRD 明确禁止
    with pytest.raises(ValueError, match="相同角色"):
        v.validate_cp(CPSubmitRest(
            cps=[CPSubmit(id_a="A", id_b="A", id_c="B")], meta=META))


def test_validate_cp_three_same_member_rejected():
    # A×A 只能停在 2 人；第三人再加同一角色同样拒绝
    with pytest.raises(ValueError, match="相同角色"):
        v.validate_cp(CPSubmitRest(
            cps=[CPSubmit(id_a="A", id_b="A", id_c="A")], meta=META))


def test_validate_cp_same_character_pair_ok():
    # PRD 2.5.4「可选取两个相同的角色」：A×A 是合法组合(R-05 曾误拒)
    cps = [CPSubmit(id_a="A", id_b="A", active="A")]
    data = CPSubmitRest(cps=cps, meta=META)
    assert v.validate_cp(data) is data


def test_validate_cp_same_pair_duplicate_combination_rejected():
    # 组合 key 必须是多重集：(A,A) 与 (A,A) 是同一组合 → 拒绝
    with pytest.raises(ValueError, match="组合重复"):
        v.validate_cp(CPSubmitRest(
            cps=[CPSubmit(id_a="A", id_b="A"),
                 CPSubmit(id_a="A", id_b="A")],
            meta=META))


def test_validate_cp_same_pair_and_mixed_pair_are_distinct():
    # 多重集口径：A×A 与 A×B 是两个不同组合，不能当成重复
    cps = [CPSubmit(id_a="A", id_b="A"), CPSubmit(id_a="A", id_b="B")]
    data = CPSubmitRest(cps=cps, meta=META)
    assert v.validate_cp(data) is data


def test_validate_cp_duplicate_combination_rejected():
    # 顺序不同也算同一个组合
    with pytest.raises(ValueError, match="组合重复"):
        v.validate_cp(CPSubmitRest(
            cps=[CPSubmit(id_a="A", id_b="B"), CPSubmit(id_a="B", id_b="A")],
            meta=META))


def test_validate_cp_three_member_combination_ok():
    cps = [CPSubmit(id_a="A", id_b="B", id_c="C", active="B")]
    data = CPSubmitRest(cps=cps, meta=META)
    assert v.validate_cp(data) is data


def test_validate_cp_distinct_combinations_ok():
    cps = [CPSubmit(id_a="A", id_b="B"), CPSubmit(id_a="A", id_b="C")]
    data = CPSubmitRest(cps=cps, meta=META)
    assert v.validate_cp(data) is data


# ── paper ──────────────────────────────────────────────────────────────
# papers_json 是不透明业务数据(前端真实载荷为嵌套对象,统计侧不读原始表),
# 只验「合法 JSON + UTF-8 ≤ 256KB + 非空容器」。旧的"非空列表+整数id"校验是按
# 想象格式写的会拒掉真实前端载荷(已按 spec 2026-06-07 移除);"空载荷"校验是
# R-03 的止损(空 "{}" 曾能解锁投票)。


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


def test_validate_paper_accepts_any_non_empty_json_container():
    # 列表/对象都放行——内部结构不归后端管
    for payload in ['[{"id": 1}]', '{"mainQuestionnaire": {"id": 11}}']:
        data = PaperSubmitRest(papers_json=payload, meta=META)
        assert v.validate_paper(data) is data


@pytest.mark.parametrize("payload", ["{}", "[]", '"just a string"', "null"])
def test_validate_paper_rejects_empty_or_scalar_payload(payload):
    """R-03: 空载荷("{}")曾被当作「已完成问卷」解锁投票,提交期即拒绝。"""
    with pytest.raises(ValueError, match="问卷数据为空"):
        v.validate_paper(PaperSubmitRest(papers_json=payload, meta=META))


def test_is_paper_meaningful():
    from src.apps.submit.service import SubmitValidator
    assert SubmitValidator.is_paper_meaningful('{"a": 1}') is True
    assert SubmitValidator.is_paper_meaningful('[{"id": 1}]') is True
    assert SubmitValidator.is_paper_meaningful("{}") is False
    assert SubmitValidator.is_paper_meaningful("[]") is False
    assert SubmitValidator.is_paper_meaningful("null") is False
    assert SubmitValidator.is_paper_meaningful("{not json") is False
    assert SubmitValidator.is_paper_meaningful(None) is False


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


# ── dojin limits (R-06 / PRD 2.6) ──────────────────────────────────────

def _dojin(**over):
    base = dict(dojin_type="manga", url="http://a.com", title="T",
                author="A", reason="R")
    base.update(over)
    return DojinSubmit(**base)


def test_validate_dojin_more_than_five_rejected():
    dojins = [_dojin(url=f"http://a.com/{i}") for i in range(6)]
    with pytest.raises(ValueError, match=r"\[1,5\]"):
        v.validate_dojin(DojinSubmitRest(dojins=dojins, meta=META))


def test_validate_dojin_five_accepted():
    dojins = [_dojin(url=f"http://a.com/{i}") for i in range(5)]
    data = DojinSubmitRest(dojins=dojins, meta=META)
    assert v.validate_dojin(data) is data


@pytest.mark.parametrize("field,limit", [
    ("title", 256), ("author", 128), ("url", 2048), ("reason", 1024),
    ("image_url", 2048),
])
def test_validate_dojin_field_limits(field, limit):
    data = DojinSubmitRest(
        dojins=[_dojin(**{field: "x" * (limit + 1)})], meta=META
    )
    with pytest.raises(ValueError, match="过长"):
        v.validate_dojin(data)
    # 正好到上限必须通过(防 off-by-one)
    data = DojinSubmitRest(
        dojins=[_dojin(**{field: "x" * limit})], meta=META
    )
    assert v.validate_dojin(data) is data
