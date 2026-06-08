"""Questionnaire completion check — pure logic, no DB.

Completion = every question group of every ``required=true`` questionnaire has
at least one answer. A group is answered when a paper_answer row exists for
that (questionnaire_id, group_id). Group-level coverage (not per-question) —
a deliberate simplification, tightenable later with frontend agreement.
"""
from __future__ import annotations

from typing import Any


def _required_groups(structure: dict[str, Any]) -> list[tuple[int, int]]:
    """Return [(questionnaire_id, group_id)] across all required questionnaires."""
    out = []
    for qn in structure.get("questionnaires", []):
        if qn.get("required"):
            for g in qn.get("questionGroups", []):
                out.append((qn["id"], g["id"]))
    return out


def is_complete(structure: dict[str, Any], answers: list[dict]) -> bool:
    """True if every required question group has an answer."""
    required = _required_groups(structure)
    if not required:
        return True
    answered = {(a["questionnaire_id"], a["group_id"]) for a in answers}
    return all(pair in answered for pair in required)
