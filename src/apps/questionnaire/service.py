"""Questionnaire domain service: structure query, structured answers, completion."""
from __future__ import annotations

from src.apps.questionnaire.assembler import assemble_structure
from src.apps.questionnaire.completion import is_complete
from src.apps.questionnaire.dao import QuestionnaireDAO


class QuestionnaireService:
    def __init__(self, dao: QuestionnaireDAO) -> None:
        self.dao = dao

    async def get_structure(self) -> dict:
        qns, groups, questions, options = await self.dao.load_structure_rows()
        return assemble_structure(qns, groups, questions, options)

    async def submit_answers(
        self, vote_id: str, vote_year: int, answers: list[dict]
    ) -> int:
        """Flatten a flat answer array into paper_answer rows."""
        rows = _flatten_answer_state(answers)
        return await self.dao.replace_answers(vote_id, vote_year, rows)

    async def get_answers(self, vote_id: str, vote_year: int) -> list[dict]:
        return await self.dao.get_answers(vote_id, vote_year)

    async def is_complete(self, vote_id: str, vote_year: int) -> bool:
        structure = await self.get_structure()
        answers = await self.dao.get_answers(vote_id, vote_year)
        return is_complete(structure, answers)

    async def import_structure(self, tree: dict) -> int:
        """Replace the questionnaire structure from a questionnaireV2 tree."""
        from src.apps.questionnaire.importer import parse_structure_tree

        qns, groups, questions, options = parse_structure_tree(tree)
        return await self.dao.replace_structure(
            qns, groups, questions, options
        )


def _flatten_answer_state(answers: list[dict]) -> list[dict]:
    """Flat answer array → list of paper_answer row dicts."""
    rows = []
    for a in answers:
        rows.append({
            "questionnaire_id": a.get("questionnaireId"),
            "group_id": a.get("groupId"),
            "active_question_id": a.get("activeQuestionId"),
            "selected_option_ids": a.get("selectedOptionIds") or [],
            "input_text": a.get("input"),
        })
    return rows
