"""Questionnaire domain service: structure query, structured answers, completion."""
from __future__ import annotations

from src.apps.questionnaire.assembler import assemble_structure
from src.apps.questionnaire.completion import is_complete
from src.apps.questionnaire.dao import QuestionnaireDAO
from src.apps.questionnaire.validation import INVALID_ANSWER, validate_answer_rows
from src.common.exceptions import ValidationError


class QuestionnaireService:
    def __init__(self, dao: QuestionnaireDAO) -> None:
        self.dao = dao

    async def get_structure(self) -> dict:
        qns, groups, questions, options = await self.dao.load_structure_rows()
        return assemble_structure(qns, groups, questions, options)

    async def submit_answers(
        self, vote_id: str, vote_year: int, answers: list[dict]
    ) -> int:
        """Flatten a flat answer array into paper_answer rows.

        Every row is checked against the stored structure first
        (``validation.validate_answer_rows``) — an opaque JSON payload must not
        be able to write rows that alias another questionnaire's group or
        reference options that do not exist (R-01/D-08).
        """
        rows = _flatten_answer_state(answers)
        if not rows:
            # append-only(B-050-后补2)下空批次无行可落,旧批次会保持可见——
            # 旧实现的"空提交=清空整卷"语义已不可表达;完成度门禁本就要求答
            # 满,清空不是产品流程,显式拒绝好过静默泄漏旧答案。
            raise ValidationError("EMPTY_PAPER_SUBMIT", details=422)
        validate_answer_rows(await self.get_structure(), rows)
        return await self.dao.replace_answers(vote_id, vote_year, rows)

    async def get_answers(self, vote_id: str, vote_year: int) -> list[dict]:
        return await self.dao.get_answers(vote_id, vote_year)

    async def is_complete(self, vote_id: str, vote_year: int) -> bool:
        structure = await self.get_structure()
        answers = await self.dao.get_answers(vote_id, vote_year)
        return is_complete(structure, answers)

    async def import_structure(self, tree: dict) -> int:
        """Replace the whole questionnaire structure from a questionnaireV2 tree.

        Inserts hierarchically so id-less trees work — autoincrement parent ids
        are resolved (flushed) before children are wired to them.
        """
        return await self.dao.replace_structure_tree(tree)


def _flatten_answer_state(answers: list[dict]) -> list[dict]:
    """Flat answer array → list of paper_answer row dicts."""
    if not isinstance(answers, list):
        raise ValidationError(
            INVALID_ANSWER, details=422, human_readable_message="问卷作答格式不正确"
        )
    rows = []
    for a in answers:
        if not isinstance(a, dict):
            raise ValidationError(
                INVALID_ANSWER,
                details=422,
                human_readable_message="问卷作答格式不正确",
            )
        rows.append({
            "questionnaire_id": a.get("questionnaireId"),
            "group_id": a.get("groupId"),
            "active_question_id": a.get("activeQuestionId"),
            "selected_option_ids": a.get("selectedOptionIds") or [],
            "input_text": a.get("input"),
        })
    return rows
