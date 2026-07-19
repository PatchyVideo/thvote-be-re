"""Questionnaire domain DAO — structure tables + paper_answer."""
from __future__ import annotations

from datetime import datetime

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
    """ORM row → plain dict with datetime → ISO string conversion."""
    out = {}
    for c in obj.__table__.columns:
        v = getattr(obj, c.key)
        if isinstance(v, datetime):
            v = v.isoformat()
        out[c.key] = v
    return out


class QuestionnaireDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def load_structure_rows(
        self,
    ) -> tuple[list, list, list, list]:
        """Return (questionnaires, groups, questions, options) as dict lists."""
        qns = (await self.session.execute(
            select(QuestionnaireDef)
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

    async def _delete_all_structure(self) -> None:
        """Delete all questionnaires and their descendants (year-less structure)."""
        existing = (await self.session.execute(
            select(QuestionnaireDef.id)
        )).scalars().all()
        if not existing:
            return
        group_ids = (await self.session.execute(
            select(QuestionGroupDef.id).where(
                QuestionGroupDef.questionnaire_id.in_(existing)
            )
        )).scalars().all()
        question_ids = []
        if group_ids:
            question_ids = (await self.session.execute(
                select(QuestionDef.id).where(QuestionDef.group_id.in_(group_ids))
            )).scalars().all()
        if question_ids:
            await self.session.execute(
                delete(OptionDef).where(OptionDef.question_id.in_(question_ids))
            )
            await self.session.execute(
                delete(QuestionDef).where(QuestionDef.id.in_(question_ids))
            )
        if group_ids:
            await self.session.execute(
                delete(QuestionGroupDef).where(QuestionGroupDef.id.in_(group_ids))
            )
        await self.session.execute(
            delete(QuestionnaireDef).where(QuestionnaireDef.id.in_(existing))
        )

    async def replace_structure_tree(self, tree: dict) -> int:
        """Replace the whole structure from a {"questionnaires":[...]} tree.

        Inserts hierarchically: each parent is flushed to obtain its
        autoincrement id, then children are wired to that id. Explicit ids in
        the tree are honored (preserves related/mutex cross-references); when
        absent, the DB assigns ids. Returns the questionnaire count.
        """
        await self._delete_all_structure()
        count = 0
        for qn in tree.get("questionnaires", []):
            if not isinstance(qn, dict):
                continue
            qn_kwargs = {
                "key": qn.get("key", ""),
                "title": qn.get("title", ""),
                "introduction": qn.get("introduction", ""),
                "category": qn.get("category", "main"),
                "required": bool(qn.get("required", False)),
                "order": qn.get("order", 0),
            }
            if qn.get("id") is not None:
                qn_kwargs["id"] = qn["id"]
            qobj = QuestionnaireDef(**qn_kwargs)
            self.session.add(qobj)
            await self.session.flush()
            count += 1
            for g in qn.get("questionGroups", []):
                g_kwargs = {
                    "questionnaire_id": qobj.id,
                    "order": g.get("order", 0),
                    "hidden_by_default": bool(g.get("hiddenByDefault", False)),
                }
                if g.get("id") is not None:
                    g_kwargs["id"] = g["id"]
                gobj = QuestionGroupDef(**g_kwargs)
                self.session.add(gobj)
                await self.session.flush()
                for q in g.get("questions", []):
                    q_kwargs = {
                        "group_id": gobj.id,
                        "type": q.get("type", "Single"),
                        "content": q.get("content", ""),
                        "introduction": q.get("introduction", ""),
                        "order": q.get("order", 0),
                        "max_input_len": q.get("maxInputLen", 1000),
                        "code": q.get("code"),
                    }
                    if q.get("id") is not None:
                        q_kwargs["id"] = q["id"]
                    quobj = QuestionDef(**q_kwargs)
                    self.session.add(quobj)
                    await self.session.flush()
                    for o in q.get("options", []):
                        o_kwargs = {
                            "question_id": quobj.id,
                            "content": o.get("content", ""),
                            "related_question_ids": o.get("relatedQuestionIds") or [],
                            "mutex_option_ids": o.get("mutexOptionIds") or [],
                            "option_group": o.get("optionGroup", 0),
                            "order": o.get("order", 0),
                            "code": o.get("code"),
                        }
                        if o.get("id") is not None:
                            o_kwargs["id"] = o["id"]
                        self.session.add(OptionDef(**o_kwargs))
        await self.session.commit()
        return count
