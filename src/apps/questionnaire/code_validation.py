"""Semantic code checks shared by administrative edits and tree replacement."""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


class InvalidCodeError(ValueError):
    """A non-empty code must be an ASCII digit string of the specified length."""


class CodeConflictError(ValueError):
    """Two questions or two options cannot share a non-empty semantic code."""


def normalize_code(value: Any, digits: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidCodeError("编号必须是字符串")
    code = value.strip()
    if not code:
        return None
    if not re.fullmatch(rf"[0-9]{{{digits}}}", code):
        raise InvalidCodeError(f"编号必须是{digits}位数字")
    return code


def validate_tree_codes(tree: dict) -> dict:
    """Validate before deleting anything; do not mutate the submitted definition."""
    tree = deepcopy(tree)
    question_codes: set[str] = set()
    option_codes: set[str] = set()

    def assign(node: dict, digits: int, seen: set[str]) -> None:
        code = normalize_code(node.get("code"), digits)
        if code:
            if code in seen:
                raise CodeConflictError(code)
            seen.add(code)
        node["code"] = code

    for questionnaire in tree.get("questionnaires", []):
        if not isinstance(questionnaire, dict):
            continue
        for group in questionnaire.get("questionGroups", []):
            for question in group.get("questions", []):
                assign(question, 5, question_codes)
                for option in question.get("options", []):
                    assign(option, 7, option_codes)
    return tree
