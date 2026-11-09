"""Strict submission checks; shared assessments also feed completion queries."""
from __future__ import annotations

from typing import Any

from src.apps.questionnaire.rules import (
    AnswerIssue, RuleEvaluation, evaluate_rules,
)
from src.apps.questionnaire.rules import is_done_row  # noqa: F401
from src.apps.questionnaire.structure_index import StructureIndex
from src.common.exceptions import ValidationError

INVALID_ANSWER = "INVALID_PAPER_ANSWER"


def _fail(message: str, code: str = "INVALID_REFERENCE") -> None:
    raise ValidationError(
        INVALID_ANSWER, details=422, error_message=code,
        human_readable_message=message,
    )


def _as_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _validate_row(index: StructureIndex, row: dict, seen: set[tuple]) -> dict:
    if not isinstance(row, dict):
        _fail("问卷作答格式不正确")
    qn_id = _as_int(row.get("questionnaire_id"))
    gid = _as_int(row.get("group_id"))
    if qn_id is None or gid is None:
        _fail("问卷作答缺少问卷/题组编号")
    if gid not in index.groups:
        _fail(f"题组{gid}不存在")
    if index.group_questionnaire[gid] != qn_id:
        _fail(f"题组{gid}不属于问卷{qn_id}")
    if (qn_id, gid) in seen:
        _fail(f"问卷{qn_id}的题组{gid}重复作答")
    seen.add((qn_id, gid))
    qid = _as_int(row.get("active_question_id"))
    if row.get("active_question_id") is not None:
        if qid is None:
            _fail(f"题组{gid}的题目编号无效")
        if index.question_group.get(qid) != gid:
            _fail(f"题目{qid}不属于题组{gid}")
    options = row.get("selected_option_ids")
    if options is None:
        options = []
    if not isinstance(options, list):
        _fail(f"题组{gid}的选项格式不正确")
    seen_options: set[int] = set()
    for oid in options:
        if _as_int(oid) is None:
            _fail(f"题组{gid}的选项编号无效")
        if oid in seen_options:
            _fail(f"题组{gid}重复选择选项{oid}")
        seen_options.add(oid)
        if qid is None:
            _fail(f"题组{gid}未选择题目却提交了选项")
        if oid not in index.question_options[qid]:
            _fail(f"选项{oid}不属于题目{qid}")
    text = row.get("input_text")
    if text is None:
        text = ""
    if not isinstance(text, str):
        _fail(f"题组{gid}的文本作答格式不正确")
    if text:
        if qid is None:
            _fail(f"题组{gid}未选择题目却提交了文本作答")
        limit = index.max_input_len(index.questions[qid])
        if len(text) > limit:
            _fail(f"题组{gid}的文本作答超过{limit}字上限")
    if qid is not None:
        question = index.questions[qid]
        kind = question.get("type")
        if kind == "Input" and options:
            _fail(f"题组{gid}的输入题不能提交选项", "ANSWER_TYPE_MISMATCH")
        if kind in ("Single", "Multiple") and text:
            _fail(f"题组{gid}的选择题不能提交文本", "ANSWER_TYPE_MISMATCH")
        if kind == "Single" and len(options) > 1:
            _fail(f"题组{gid}的单选题只能选择一个选项", "SINGLE_CHOICE_LIMIT")
        if kind == "Multiple" and len({
            index.question_options[qid][oid].get("optionGroup", 0) for oid in options
        }) > 1:
            _fail(f"题组{gid}选择了不同选项组的互斥选项", "OPTION_GROUP_CONFLICT")
    return {**row, "active_question_id": qid,
            "selected_option_ids": options, "input_text": text}


def assess_answers(index: StructureIndex, rows: list[dict]) -> RuleEvaluation:
    """Record errors per questionnaire so stored data cannot abort batch reports."""
    checked: dict[tuple[int, int], dict] = {}
    rejected = RuleEvaluation()
    seen: set[tuple] = set()
    if not isinstance(rows, list):
        rejected.reject(AnswerIssue(
            "INVALID_SHAPE", None, None, None, "问卷作答格式不正确",
        ))
        return rejected
    for row in rows:
        try:
            valid = _validate_row(index, row, seen)
            checked[(valid["questionnaire_id"], valid["group_id"])] = valid
        except ValidationError as error:
            item = row if isinstance(row, dict) else {}
            qn_id = _as_int(item.get("questionnaire_id"))
            gid = _as_int(item.get("group_id"))
            rejected.reject(AnswerIssue(
                error.error_message or "INVALID_REFERENCE", qn_id, gid,
                _as_int(item.get("active_question_id")),
                error.human_readable_message or "问卷作答无效",
            ))
            owner = index.group_questionnaire.get(gid)
            if owner is not None:
                rejected.invalid_questionnaire_ids.add(owner)
    result = evaluate_rules(index, checked)
    result.invalid_questionnaire_ids.update(rejected.invalid_questionnaire_ids)
    if rejected.first_issue is not None:
        result.first_issue = rejected.first_issue
    return result


def require_valid(evaluation: RuleEvaluation) -> None:
    issue = evaluation.configuration_issue or evaluation.first_issue
    if issue is None:
        return
    kind = ("QUESTIONNAIRE_CONFIGURATION_ERROR" if evaluation.configuration_issue
            else INVALID_ANSWER)
    raise ValidationError(
        kind, details=422, error_message=issue.code,
        human_readable_message=issue.message,
    )


def validate_answer_rows(structure: dict[str, Any], rows: list[dict]) -> None:
    require_valid(assess_answers(StructureIndex(structure), rows))
