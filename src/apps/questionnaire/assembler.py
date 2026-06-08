"""Assemble DB structure rows into the frontend ``questionnaireV2`` shape.

Pure functions, no DB. Input rows are plain dicts (one per row). Output is the
``QuestionnaireDefinitionAllV2``-shaped dict the frontend parser consumes.
"""
from __future__ import annotations

from typing import Any

# slot → (category bucket key, output key)
_SLOT_TO_KEY = {
    "required": ("mainQuestionnaire", "requiredQuestionnaire"),
    "optional1": ("mainQuestionnaire", "optionalQuestionnaire1"),
    "optional2": ("mainQuestionnaire", "optionalQuestionnaire2"),
    "ex1": ("extraQuestionnaire", "exQuestionnaire1"),
    "ex2": ("extraQuestionnaire", "exQuestionnaire2"),
    "ex3": ("extraQuestionnaire", "exQuestionnaire3"),
    "ex4": ("extraQuestionnaire", "exQuestionnaire4"),
    "ex5": ("extraQuestionnaire", "exQuestionnaire5"),
}


def _option_out(o: dict) -> dict:
    return {
        "id": o["id"],
        "content": o.get("content", ""),
        "relatedQuestionIds": o.get("related_question_ids") or [],
        "mutexOptionIds": o.get("mutex_option_ids") or [],
        "optionGroup": o.get("option_group", 0),
    }


def _question_out(q: dict, options_by_question: dict) -> dict:
    opts = sorted(
        options_by_question.get(q["id"], []), key=lambda o: o.get("order", 0)
    )
    return {
        "id": q["id"],
        "type": q.get("type", "Single"),
        "content": q.get("content", ""),
        "introduction": q.get("introduction", ""),
        "options": [_option_out(o) for o in opts],
    }


def _group_out(g: dict, questions_by_group: dict, options_by_question: dict) -> dict:
    qs = sorted(
        questions_by_group.get(g["id"], []), key=lambda q: q.get("order", 0)
    )
    return {
        "id": g["id"],
        "questionnaireId": g["questionnaire_id"],
        "order": g.get("order", 0),
        "initialQuestionId": g.get("initial_question_id", 0),
        "questions": [_question_out(q, options_by_question) for q in qs],
    }


def _questionnaire_out(
    qn: dict, groups_by_questionnaire: dict, questions_by_group: dict,
    options_by_question: dict,
) -> dict:
    grps = sorted(
        groups_by_questionnaire.get(qn["id"], []), key=lambda g: g.get("order", 0)
    )
    return {
        "id": qn["id"],
        "name": qn.get("name", ""),
        "introduction": qn.get("introduction", ""),
        "questionGroups": [
            _group_out(g, questions_by_group, options_by_question) for g in grps
        ],
    }


def assemble_structure(
    questionnaires: list[dict],
    groups: list[dict],
    questions: list[dict],
    options: list[dict],
) -> dict[str, Any]:
    """Build the QuestionnaireDefinitionAllV2-shaped dict."""
    groups_by_questionnaire: dict[int, list] = {}
    for g in groups:
        groups_by_questionnaire.setdefault(g["questionnaire_id"], []).append(g)
    questions_by_group: dict[int, list] = {}
    for q in questions:
        questions_by_group.setdefault(q["group_id"], []).append(q)
    options_by_question: dict[int, list] = {}
    for o in options:
        options_by_question.setdefault(o["question_id"], []).append(o)

    out: dict[str, Any] = {"mainQuestionnaire": {}, "extraQuestionnaire": {}}
    for qn in questionnaires:
        mapping = _SLOT_TO_KEY.get(qn["slot"])
        if mapping is None:
            continue
        bucket, key = mapping
        out[bucket][key] = _questionnaire_out(
            qn, groups_by_questionnaire, questions_by_group, options_by_question
        )
    return out
