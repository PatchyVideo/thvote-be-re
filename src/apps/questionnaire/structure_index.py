"""Index for the assembled questionnaire structure (``{"questionnaires": [...]}``).

Pure, no DB. ``assemble_structure`` output is the single structure shape the
frontend also consumes, so both answer validation and the completion gate read
it through this index instead of re-walking nested dicts.

Ids are whatever the structure carries (ints from DB rows); lookups use
``int`` keys and callers must coerce/validate before hitting the index.
"""
from __future__ import annotations

from typing import Any


class StructureIndex:
    """id → row lookups over the assembled structure tree."""

    def __init__(self, structure: dict[str, Any]):
        self.questionnaires: list[dict] = []
        # group id → group dict
        self.groups: dict[int, dict] = {}
        # group id → owning questionnaire id
        self.group_questionnaire: dict[int, int] = {}
        # question id → question dict
        self.questions: dict[int, dict] = {}
        # question id → owning group id
        self.question_group: dict[int, int] = {}
        # question id → {option id: option dict}
        self.question_options: dict[int, dict[int, dict]] = {}

        for qn in structure.get("questionnaires") or []:
            if not isinstance(qn, dict):
                continue
            self.questionnaires.append(qn)
            qn_id = qn.get("id")
            for group in qn.get("questionGroups") or []:
                if not isinstance(group, dict):
                    continue
                gid = group.get("id")
                self.groups[gid] = group
                self.group_questionnaire[gid] = qn_id
                for question in group.get("questions") or []:
                    if not isinstance(question, dict):
                        continue
                    qid = question.get("id")
                    self.questions[qid] = question
                    self.question_group[qid] = gid
                    self.question_options[qid] = {
                        option.get("id"): option
                        for option in (question.get("options") or [])
                        if isinstance(option, dict)
                    }

    def group_has_questions(self, group: dict) -> bool:
        return bool(group.get("questions"))

    def max_input_len(self, question: dict) -> int:
        """``maxInputLen`` 兜底与 importer 落库默认值一致(1000)。"""
        value = question.get("maxInputLen")
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        return 1000
