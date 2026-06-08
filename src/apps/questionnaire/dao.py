"""Questionnaire domain DAO — structure tables + paper_answer."""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db_model.questionnaire_def import (
    OptionDef,
    PaperAnswer,
    QuestionDef,
    QuestionGroupDef,
    QuestionnaireDef,
)


def _row_to_dict(obj) -> dict:
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns}


class QuestionnaireDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def load_structure_rows(
        self, vote_year: int
    ) -> tuple[list, list, list, list]:
        """Return (questionnaires, groups, questions, options) as dict lists."""
        qns = (await self.session.execute(
            select(QuestionnaireDef).where(QuestionnaireDef.vote_year == vote_year)
        )).scalars().all()
        qn_dicts = [_row_to_dict(q) for q in qns]
        qn_ids = [q["id"] for q in qn_dicts]
        if not qn_ids:
            return [], [], [], []

        groups = (await self.session.execute(
            select(QuestionGroupDef).where(
                QuestionGroupDef.questionnaire_id.in_(qn_ids)
            )
        )).scalars().all()
        group_dicts = [_row_to_dict(g) for g in groups]
        group_ids = [g["id"] for g in group_dicts]

        questions = []
        if group_ids:
            questions = (await self.session.execute(
                select(QuestionDef).where(QuestionDef.group_id.in_(group_ids))
            )).scalars().all()
        question_dicts = [_row_to_dict(q) for q in questions]
        question_ids = [q["id"] for q in question_dicts]

        options = []
        if question_ids:
            options = (await self.session.execute(
                select(OptionDef).where(OptionDef.question_id.in_(question_ids))
            )).scalars().all()
        option_dicts = [_row_to_dict(o) for o in options]

        return qn_dicts, group_dicts, question_dicts, option_dicts

    async def replace_answers(
        self, vote_id: str, vote_year: int, rows: list[dict]
    ) -> int:
        """Upsert structured answers by replacing this user's rows for the year."""
        await self.session.execute(
            delete(PaperAnswer).where(
                PaperAnswer.vote_id == vote_id,
                PaperAnswer.vote_year == vote_year,
            )
        )
        for r in rows:
            self.session.add(PaperAnswer(vote_id=vote_id, vote_year=vote_year, **r))
        await self.session.commit()
        return len(rows)

    async def get_answers(self, vote_id: str, vote_year: int) -> list[dict]:
        rows = (await self.session.execute(
            select(PaperAnswer).where(
                PaperAnswer.vote_id == vote_id,
                PaperAnswer.vote_year == vote_year,
            )
        )).scalars().all()
        return [_row_to_dict(r) for r in rows]

    async def replace_structure(
        self,
        vote_year: int,
        questionnaires: list[dict],
        groups: list[dict],
        questions: list[dict],
        options: list[dict],
    ) -> int:
        """Replace a year's structure: delete existing rows, insert new tree.

        Deletes are scoped to the year's questionnaires and their descendants.
        Returns the number of questionnaires written.
        """
        existing = (await self.session.execute(
            select(QuestionnaireDef.id).where(
                QuestionnaireDef.vote_year == vote_year
            )
        )).scalars().all()
        if existing:
            group_ids = (await self.session.execute(
                select(QuestionGroupDef.id).where(
                    QuestionGroupDef.questionnaire_id.in_(existing)
                )
            )).scalars().all()
            question_ids = []
            if group_ids:
                question_ids = (await self.session.execute(
                    select(QuestionDef.id).where(
                        QuestionDef.group_id.in_(group_ids)
                    )
                )).scalars().all()
            if question_ids:
                await self.session.execute(
                    delete(OptionDef).where(
                        OptionDef.question_id.in_(question_ids)
                    )
                )
                await self.session.execute(
                    delete(QuestionDef).where(QuestionDef.id.in_(question_ids))
                )
            if group_ids:
                await self.session.execute(
                    delete(QuestionGroupDef).where(
                        QuestionGroupDef.id.in_(group_ids)
                    )
                )
            await self.session.execute(
                delete(QuestionnaireDef).where(
                    QuestionnaireDef.id.in_(existing)
                )
            )

        for qn in questionnaires:
            self.session.add(QuestionnaireDef(vote_year=vote_year, **qn))
        for g in groups:
            self.session.add(QuestionGroupDef(**g))
        for q in questions:
            self.session.add(QuestionDef(**q))
        for o in options:
            self.session.add(OptionDef(**o))
        await self.session.commit()
        return len(questionnaires)
