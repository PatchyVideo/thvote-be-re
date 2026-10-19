"""Questionnaire completion check — pure logic, no DB.

Completion = every **visible** question group of every ``required=true``
questionnaire has a substantive answer.  The previous rule ("a row exists for
the group") let a caller submit structurally-valid-but-empty rows and unlock
voting (R-01/D-08), so the gate now also requires real content.

Visibility mirrors the frontend runner (``questionnaireV2Parser.ts``), otherwise
the server would demand answers for groups the UI never shows:

- a group whose ``order`` is 1 is always shown, with its first question;
- other groups are shown by default unless ``hiddenByDefault`` is set;
- a hidden group becomes visible when a selected option of a visible group in
  the same questionnaire lists one of its questions in ``relatedQuestionIds``
  (iterated to a fixpoint, like the frontend's normalisation loop).

A group counts as answered when its active question carries real content:
non-empty text for ``Input`` questions, at least one selected option otherwise
(``validation.is_done_row``).

Legacy fallback: a required questionnaire with no answerable group at all (no
questions imported yet) keeps the old row-coverage rule, so a half-configured
structure does not hard-block voting.
"""
from __future__ import annotations

from typing import Any

from src.apps.questionnaire.structure_index import StructureIndex
from src.apps.questionnaire.validation import is_done_row

_MAX_VISIBILITY_ROUNDS = 8


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _rows_by_group(answers: list[dict]) -> dict[tuple, list[dict]]:
    out: dict[tuple, list[dict]] = {}
    for answer in answers:
        if not isinstance(answer, dict):
            continue
        questionnaire_id = _int_or_none(answer.get("questionnaire_id"))
        group_id = _int_or_none(answer.get("group_id"))
        if questionnaire_id is None or group_id is None:
            continue
        out.setdefault((questionnaire_id, group_id), []).append(answer)
    return out


def _groups_of(questionnaire: dict) -> list[dict]:
    return [g for g in (questionnaire.get("questionGroups") or []) if isinstance(g, dict)]


def _visible_group_ids(
    index: StructureIndex,
    questionnaire: dict,
    rows: dict[tuple, list[dict]],
) -> set[int]:
    """Group ids the frontend would currently render for this questionnaire."""
    qn_id = questionnaire.get("id")
    groups = [g for g in _groups_of(questionnaire) if index.group_has_questions(g)]
    visible = {
        g["id"]
        for g in groups
        if g.get("order") == 1 or not g.get("hiddenByDefault")
    }

    for _ in range(_MAX_VISIBILITY_ROUNDS):
        added: set[int] = set()
        for group_id in list(visible):
            for row in rows.get((qn_id, group_id), []):
                question_id = _int_or_none(row.get("active_question_id"))
                if question_id is None or index.question_group.get(question_id) != group_id:
                    continue
                options = index.question_options.get(question_id, {})
                for raw_option in row.get("selected_option_ids") or []:
                    option = options.get(_int_or_none(raw_option))
                    if option is None:
                        continue
                    for related in option.get("relatedQuestionIds") or []:
                        target = index.question_group.get(_int_or_none(related))
                        if (
                            target is not None
                            and target != group_id
                            and target not in visible
                            and index.group_questionnaire.get(target) == qn_id
                        ):
                            added.add(target)
        if not added:
            break
        visible |= added
    return visible


def is_complete(structure: dict[str, Any], answers: list[dict]) -> bool:
    """True if every required questionnaire is completed (see module docstring)."""
    index = StructureIndex(structure)
    rows = _rows_by_group(answers)
    answered = {
        (qn_id, group_id)
        for (qn_id, group_id), group_rows in rows.items()
        if any(is_done_row(index, row) for row in group_rows)
    }

    for questionnaire in index.questionnaires:
        if not questionnaire.get("required"):
            continue
        qn_id = questionnaire.get("id")
        groups = _groups_of(questionnaire)
        answerable = [g for g in groups if index.group_has_questions(g)]
        if not answerable:
            # Legacy fallback: nothing is answerable yet → old "row exists" rule.
            if all((qn_id, g.get("id")) in rows for g in groups):
                continue
            return False
        visible = _visible_group_ids(index, questionnaire, rows) & {
            g["id"] for g in answerable
        }
        if not visible:
            return False
        if any((qn_id, group_id) not in answered for group_id in visible):
            return False
    return True
