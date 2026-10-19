"""Structured questionnaire answers (``submitPaperV2``) — reference validation.

The GraphQL payload is an opaque ``JSON`` scalar, so nothing below the resolver
can rely on a schema: before this module existed, a caller could post rows with
made-up ``questionnaireId``/``groupId``/``activeQuestionId``/``selectedOptionIds``
and they were stored verbatim (R-01/D-08).  Because the completion gate counts
stored rows, such forged rows unlocked voting and polluted every
questionnaire-derived statistic.

Checks are structural only (existence + ownership + option membership + input
length).  Whether a row carries a *substantive* answer is the completion gate's
concern (``completion.py``) — the frontend legitimately submits one row per
group, including untouched groups with ``activeQuestionId: null``.
"""
from __future__ import annotations

from typing import Any

from src.apps.questionnaire.structure_index import StructureIndex
from src.common.exceptions import ValidationError

INVALID_ANSWER = "INVALID_PAPER_ANSWER"


def _fail(human_readable_message: str) -> None:
    raise ValidationError(
        INVALID_ANSWER, details=422, human_readable_message=human_readable_message
    )


def _as_int(value: Any) -> int | None:
    """Ids are integers in the structure; bool is an int subclass, reject it."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def validate_answer_rows(structure: dict[str, Any], rows: list[dict]) -> None:
    """Raise ``ValidationError`` unless every row references the stored structure.

    Rejects (all as ``INVALID_PAPER_ANSWER``):
    - unknown questionnaire/group, or a group belonging to another questionnaire;
    - duplicate ``(questionnaire_id, group_id)``;
    - ``active_question_id`` outside the row's group;
    - ``selected_option_ids`` outside the active question (or options supplied
      without an active question, or repeated options);
    - ``input_text`` longer than the question's ``maxInputLen``, or non-empty
      text without an active question.
    """
    index = StructureIndex(structure)
    seen: set[tuple[int, int]] = set()

    for row in rows:
        qn_id = _as_int(row.get("questionnaire_id"))
        group_id = _as_int(row.get("group_id"))
        if qn_id is None or group_id is None:
            _fail("问卷作答缺少问卷/题组编号")
        group = index.groups.get(group_id)
        if group is None:
            _fail(f"题组{group_id}不存在")
        if index.group_questionnaire.get(group_id) != qn_id:
            _fail(f"题组{group_id}不属于问卷{qn_id}")

        key = (qn_id, group_id)
        if key in seen:
            _fail(f"问卷{qn_id}的题组{group_id}重复作答")
        seen.add(key)

        question_id = _as_int(row.get("active_question_id"))
        if row.get("active_question_id") is not None:
            if question_id is None:
                _fail(f"题组{group_id}的题目编号无效")
            if index.question_group.get(question_id) != group_id:
                _fail(f"题目{question_id}不属于题组{group_id}")

        raw_options = row.get("selected_option_ids") or []
        if not isinstance(raw_options, list):
            _fail(f"题组{group_id}的选项格式不正确")
        option_ids: list[int] = []
        for raw_option in raw_options:
            option_id = _as_int(raw_option)
            if option_id is None:
                _fail(f"题组{group_id}的选项编号无效")
            if option_id in option_ids:
                _fail(f"题组{group_id}重复选择选项{option_id}")
            option_ids.append(option_id)
        if option_ids:
            if question_id is None:
                _fail(f"题组{group_id}未选择题目却提交了选项")
            valid_options = index.question_options.get(question_id, {})
            for option_id in option_ids:
                if option_id not in valid_options:
                    _fail(f"选项{option_id}不属于题目{question_id}")

        input_text = row.get("input_text")
        if input_text is None:
            input_text = ""
        if not isinstance(input_text, str):
            _fail(f"题组{group_id}的文本作答格式不正确")
        if input_text:
            if question_id is None:
                _fail(f"题组{group_id}未选择题目却提交了文本作答")
            limit = index.max_input_len(index.questions[question_id])
            if len(input_text) > limit:
                _fail(f"题组{group_id}的文本作答超过{limit}字上限")


def is_done_row(index: StructureIndex, row: dict) -> bool:
    """True when a stored row carries a real answer for a *visible* group.

    Mirrors the frontend runner: ``Input`` questions need non-empty text, every
    other type needs at least one selected option.  Options that no longer
    belong to the question (structure re-import, legacy junk) do not count.
    """
    question_id = _as_int(row.get("active_question_id"))
    if question_id is None:
        return False
    question = index.questions.get(question_id)
    if question is None:
        return False
    if index.question_group.get(question_id) != row.get("group_id"):
        return False

    if question.get("type") == "Input":
        text = row.get("input_text") or ""
        return isinstance(text, str) and bool(text.strip())

    options = row.get("selected_option_ids") or []
    if not isinstance(options, list):
        return False
    valid_options = index.question_options.get(question_id, {})
    return any(_as_int(o) in valid_options for o in options)
