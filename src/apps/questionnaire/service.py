"""Questionnaire domain service: structure query, structured answers, completion."""
from __future__ import annotations

from src.apps.questionnaire.assembler import assemble_structure
from src.apps.questionnaire.completion import is_complete
from src.apps.questionnaire.dao import QuestionnaireDAO


class QuestionnaireService:
    def __init__(self, dao: QuestionnaireDAO) -> None:
        self.dao = dao

    async def get_structure(self, vote_year: int) -> dict:
        qns, groups, questions, options = await self.dao.load_structure_rows(
            vote_year
        )
        return assemble_structure(qns, groups, questions, options)

    async def submit_answers(
        self, vote_id: str, vote_year: int, answer_state: dict
    ) -> int:
        """Flatten a QuestionnaireAnswerStateV2 into paper_answer rows."""
        rows = _flatten_answer_state(answer_state)
        return await self.dao.replace_answers(vote_id, vote_year, rows)

    async def get_answers(self, vote_id: str, vote_year: int) -> list[dict]:
        return await self.dao.get_answers(vote_id, vote_year)

    async def is_complete(self, vote_id: str, vote_year: int) -> bool:
        structure = await self.get_structure(vote_year)
        answers = await self.dao.get_answers(vote_id, vote_year)
        return is_complete(structure, answers)

    async def import_structure(self, vote_year: int, tree: dict) -> int:
        """Replace a year's questionnaire structure from a questionnaireV2 tree."""
        from src.apps.questionnaire.importer import parse_structure_tree

        qns, groups, questions, options = parse_structure_tree(tree)
        return await self.dao.replace_structure(
            vote_year, qns, groups, questions, options
        )


def _flatten_answer_state(answer_state: dict) -> list[dict]:
    """QuestionnaireAnswerStateV2 → list of paper_answer row dicts.

    Walks both mainQuestionnaire and extraQuestionnaire buckets; each
    questionnaire draft has groups[] with selected options / input.
    """
    rows: list[dict] = []
    for bucket_key in ("mainQuestionnaire", "extraQuestionnaire"):
        bucket = answer_state.get(bucket_key) or {}
        for draft in bucket.values():
            if not isinstance(draft, dict):
                continue
            qid = draft.get("questionnaireId")
            for g in draft.get("groups", []):
                rows.append({
                    "questionnaire_id": qid,
                    "group_id": g.get("groupId"),
                    "active_question_id": g.get("activeQuestionId"),
                    "selected_option_ids": g.get("selectedOptionIds") or [],
                    "input_text": g.get("input"),
                })
    return rows
