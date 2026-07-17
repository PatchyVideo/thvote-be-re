"""Assemble DB structure rows into the frontend questionnaire array shape.

Pure functions, no DB. Input rows are plain dicts (one per row). Output is
``{"questionnaires": [...]}`` sorted by ``order`` — the shape the frontend
parser consumes (B-041: free-form list, replaces the old fixed-8-slot object).
"""
from __future__ import annotations

from typing import Any


def _option_out(o: dict) -> dict:
    return {
        "id": o["id"],
        "order": o.get("order", 0),
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
        "order": q.get("order", 0),
        "type": q.get("type", "Single"),
        "content": q.get("content", ""),
        "introduction": q.get("introduction", ""),
        "maxInputLen": q.get("max_input_len", 1000),
        "options": [_option_out(o) for o in opts],
    }


def _group_out(g: dict, questions_by_group: dict, options_by_question: dict) -> dict:
    qs = sorted(
        questions_by_group.get(g["id"], []), key=lambda q: q.get("order", 0)
    )
    return {
        "id": g["id"],
        "order": g.get("order", 0),
        "hiddenByDefault": bool(g.get("hidden_by_default", False)),
        "questions": [_question_out(q, options_by_question) for q in qs],
    }


def _questionnaire_out(
    qn: dict, groups_by_q: dict, questions_by_group: dict, options_by_question: dict
) -> dict:
    grps = sorted(
        groups_by_q.get(qn["id"], []), key=lambda g: g.get("order", 0)
    )
    return {
        "id": qn["id"],
        "key": qn.get("key", ""),
        "title": qn.get("title", ""),
        "introduction": qn.get("introduction", ""),
        "category": qn.get("category", "main"),
        "required": bool(qn.get("required", False)),
        "order": qn.get("order", 0),
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
    """Build the {"questionnaires": [...]} dict, sorted by order."""
    groups_by_q: dict[int, list] = {}
    for g in groups:
        groups_by_q.setdefault(g["questionnaire_id"], []).append(g)
    questions_by_group: dict[int, list] = {}
    for q in questions:
        questions_by_group.setdefault(q["group_id"], []).append(q)
    options_by_question: dict[int, list] = {}
    for o in options:
        options_by_question.setdefault(o["question_id"], []).append(o)

    ordered = sorted(questionnaires, key=lambda q: q.get("order", 0))
    return {
        "questionnaires": [
            _questionnaire_out(qn, groups_by_q, questions_by_group, options_by_question)
            for qn in ordered
        ]
    }
