"""Questionnaire completion check — pure logic, no DB.

Block 1 used a weak gate ("any paper submitted"). Block 3 upgrades it to:
"every question group in the required questionnaire has at least one answer".

The "required" questionnaire is the ``requiredQuestionnaire`` slot under
``mainQuestionnaire``. A group is considered answered when a paper_answer row
exists for that (questionnaire_id, group_id). This intentionally tracks
group-level coverage rather than per-question — a simplification noted in the
plan; it can be tightened later with frontend agreement.
"""
from __future__ import annotations

from typing import Any


def _required_groups(structure: dict[str, Any]) -> list[tuple[int, int]]:
    """Return [(questionnaire_id, group_id)] for the required questionnaire."""
    main = structure.get("mainQuestionnaire") or {}
    req = main.get("requiredQuestionnaire") or {}
    qid = req.get("id")
    out = []
    for g in req.get("questionGroups", []):
        out.append((qid, g["id"]))
    return out


def is_complete(structure: dict[str, Any], answers: list[dict]) -> bool:
    """True if every required question group has an answer."""
    required = _required_groups(structure)
    if not required:
        return True
    answered = {(a["questionnaire_id"], a["group_id"]) for a in answers}
    return all(pair in answered for pair in required)
