"""Parse a {"questionnaires":[...]} tree into DB structure row dicts.

Pure functions, no DB. Reverse of the assembler. Used by the admin import
endpoint to load an entire questionnaire definition at once. Each row dict
keeps its ``id`` if present (so an import can preserve stable ids); the DAO
decides whether to honor or reassign.
"""
from __future__ import annotations

from typing import Any


def parse_structure_tree(
    tree: dict[str, Any]
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """Return (questionnaires, groups, questions, options) row dicts."""
    questionnaires: list[dict] = []
    groups: list[dict] = []
    questions: list[dict] = []
    options: list[dict] = []

    for qn in tree.get("questionnaires", []):
        if not isinstance(qn, dict):
            continue
        qn_id = qn.get("id")
        q_row = {
            "key": qn.get("key", ""),
            "title": qn.get("title", ""),
            "introduction": qn.get("introduction", ""),
            "category": qn.get("category", "main"),
            "required": bool(qn.get("required", False)),
            "order": qn.get("order", 0),
        }
        if qn_id is not None:
            q_row["id"] = qn_id
        questionnaires.append(q_row)

        for g in qn.get("questionGroups", []):
            g_id = g.get("id")
            g_row = {
                "questionnaire_id": qn_id,
                "order": g.get("order", 0),
                "hidden_by_default": bool(g.get("hiddenByDefault", False)),
            }
            if g_id is not None:
                g_row["id"] = g_id
            groups.append(g_row)

            for q in g.get("questions", []):
                q_id = q.get("id")
                qn_row = {
                    "group_id": g_id,
                    "type": q.get("type", "Single"),
                    "content": q.get("content", ""),
                    "introduction": q.get("introduction", ""),
                    "order": q.get("order", 0),
                    "max_input_len": q.get("maxInputLen", 1000),
                }
                if q_id is not None:
                    qn_row["id"] = q_id
                questions.append(qn_row)

                for o in q.get("options", []):
                    o_id = o.get("id")
                    o_row = {
                        "question_id": q_id,
                        "content": o.get("content", ""),
                        "related_question_ids": o.get("relatedQuestionIds") or [],
                        "mutex_option_ids": o.get("mutexOptionIds") or [],
                        "option_group": o.get("optionGroup", 0),
                        "order": o.get("order", 0),
                    }
                    if o_id is not None:
                        o_row["id"] = o_id
                    options.append(o_row)

    return questionnaires, groups, questions, options
