"""Completion consumes the same validated rule evaluation as submissions.

The stored-read wrapper ignores orphaned groups. Questionnaires without
answerable questions never count as complete; new submissions reject unknown IDs.
"""
from __future__ import annotations

from typing import Any

from src.apps.questionnaire.rules import RuleEvaluation
from src.apps.questionnaire.structure_index import StructureIndex
from src.apps.questionnaire.validation import assess_answers


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def completed_from_evaluation(
    index: StructureIndex, evaluation: RuleEvaluation,
) -> set[int]:
    completed: set[int] = set()
    for questionnaire in index.questionnaires:
        qn_id = questionnaire["id"]
        if qn_id in evaluation.invalid_questionnaire_ids:
            continue
        groups = index.questionnaire_groups[qn_id]
        answerable = {g["id"] for g in groups if index.group_has_questions(g)}
        visible = evaluation.visible_group_ids & answerable
        if visible and visible <= evaluation.answered_group_ids:
            completed.add(qn_id)
    return completed


def completed_questionnaire_ids(index: StructureIndex, answers: list[dict]) -> set[int]:
    """Assess latest stored rows; a bad questionnaire cannot abort batch reports."""
    known_rows = []
    for row in answers:
        if not isinstance(row, dict):
            continue
        gid = _int_or_none(row.get("group_id"))
        qn_id = _int_or_none(row.get("questionnaire_id"))
        if gid not in index.groups or qn_id is None:
            continue
        known_rows.append({**row, "group_id": gid, "questionnaire_id": qn_id})
    return completed_from_evaluation(index, assess_answers(index, known_rows))


def meets_completion_policy(questionnaires: list[dict], completed: set[int]) -> bool:
    """Overall voting policy: all required plus one optional extra questionnaire.

    Keep this policy separate from per-questionnaire answer evaluation. See
    docs/architecture/backend-overview.md for configuration and gate callers.
    """
    required = {qn["id"] for qn in questionnaires if qn.get("required")}
    extra = {qn["id"] for qn in questionnaires
             if qn.get("category") == "extra" and not qn.get("required")}
    return bool(required) and required <= completed and bool(extra & completed)


def is_complete(structure: dict[str, Any], answers: list[dict]) -> bool:
    index = StructureIndex(structure)
    completed = completed_questionnaire_ids(index, answers)
    return meets_completion_policy(index.questionnaires, completed)
