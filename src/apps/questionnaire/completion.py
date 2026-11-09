"""Completion consumes the same validated rule evaluation as submissions.

Only the stored-read wrapper ignores orphaned groups and preserves row coverage
for unconfigured questionnaires. New submissions still reject unknown IDs.
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
        if not answerable:
            # Historical gate fallback only; statistics explicitly excludes these.
            if all((qn_id, g["id"]) in evaluation.supplied_groups for g in groups):
                completed.add(qn_id)
            continue
        visible = evaluation.visible_group_ids & answerable
        if visible and visible <= evaluation.answered_group_ids:
            completed.add(qn_id)
    return completed


def completed_questionnaire_ids(index: StructureIndex, answers: list[dict]) -> set[int]:
    """Assess latest stored rows; a bad questionnaire cannot abort batch reports."""
    known_rows = []
    unconfigured = {
        qn["id"] for qn in index.questionnaires
        if not any(index.group_has_questions(g)
                   for g in index.questionnaire_groups[qn["id"]])
    }
    covered: set[tuple[int, int]] = set()
    for row in answers:
        if not isinstance(row, dict):
            continue
        gid = _int_or_none(row.get("group_id"))
        qn_id = _int_or_none(row.get("questionnaire_id"))
        if gid not in index.groups or qn_id is None:
            continue
        if qn_id in unconfigured and index.group_questionnaire[gid] == qn_id:
            # No definitions remain to interpret old payloads. Preserve only
            # historical row coverage, including duplicate stored rows.
            if (qn_id, gid) not in covered:
                known_rows.append({"questionnaire_id": qn_id, "group_id": gid})
                covered.add((qn_id, gid))
        else:
            known_rows.append({**row, "group_id": gid, "questionnaire_id": qn_id})
    return completed_from_evaluation(index, assess_answers(index, known_rows))


def is_complete(structure: dict[str, Any], answers: list[dict]) -> bool:
    index = StructureIndex(structure)
    completed = completed_questionnaire_ids(index, answers)
    return all(
        qn["id"] in completed for qn in index.questionnaires if qn.get("required")
    )
