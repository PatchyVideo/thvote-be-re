"""Parse a questionnaireV2-shaped tree into DB structure rows (reverse assembler).

Pure functions, no DB. Used by the admin tree-import endpoint to load an entire
questionnaire definition at once.
"""
from __future__ import annotations

from typing import Any

# output key → (slot, category)
_KEY_TO_SLOT = {
    "requiredQuestionnaire": ("required", "main"),
    "optionalQuestionnaire1": ("optional1", "main"),
    "optionalQuestionnaire2": ("optional2", "main"),
    "exQuestionnaire1": ("ex1", "extra"),
    "exQuestionnaire2": ("ex2", "extra"),
    "exQuestionnaire3": ("ex3", "extra"),
    "exQuestionnaire4": ("ex4", "extra"),
    "exQuestionnaire5": ("ex5", "extra"),
}


def parse_structure_tree(
    tree: dict[str, Any]
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """Return (questionnaires, groups, questions, options) row dicts."""
    questionnaires: list[dict] = []
    groups: list[dict] = []
    questions: list[dict] = []
    options: list[dict] = []

    for bucket_key in ("mainQuestionnaire", "extraQuestionnaire"):
        bucket = tree.get(bucket_key) or {}
        for key, qn in bucket.items():
            mapping = _KEY_TO_SLOT.get(key)
            if mapping is None or not isinstance(qn, dict):
                continue
            slot, category = mapping
            qn_id = qn["id"]
            questionnaires.append({
                "id": qn_id,
                "slot": slot,
                "category": category,
                "name": qn.get("name", ""),
                "introduction": qn.get("introduction", ""),
                "order": qn.get("order", 0),
            })
            for g in qn.get("questionGroups", []):
                groups.append({
                    "id": g["id"],
                    "questionnaire_id": qn_id,
                    "order": g.get("order", 0),
                    "initial_question_id": g.get("initialQuestionId", 0),
                })
                for q in g.get("questions", []):
                    questions.append({
                        "id": q["id"],
                        "group_id": g["id"],
                        "type": q.get("type", "Single"),
                        "content": q.get("content", ""),
                        "introduction": q.get("introduction", ""),
                        "order": q.get("order", 0),
                        "max_input_len": q.get("maxInputLen", 1000),
                    })
                    for o in q.get("options", []):
                        options.append({
                            "id": o["id"],
                            "question_id": q["id"],
                            "content": o.get("content", ""),
                            "related_question_ids": o.get("relatedQuestionIds")
                            or [],
                            "mutex_option_ids": o.get("mutexOptionIds") or [],
                            "option_group": o.get("optionGroup", 0),
                            "order": o.get("order", 0),
                        })
    return questionnaires, groups, questions, options
