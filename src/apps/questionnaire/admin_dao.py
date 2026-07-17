"""Questionnaire admin DAO: 4-level CRUD with cascade delete (B-041).

Pure data access over the questionnaire structure tables. The service layer
(``admin_service.py``) owns validation (key uniqueness, parent existence).
"""
from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.questionnaire.assembler import assemble_structure
from src.db_model.questionnaire_def import (
    OptionDef,
    QuestionDef,
    QuestionGroupDef,
    QuestionnaireDef,
)


def _row_to_dict(obj) -> dict:
    """Map a mapped ORM instance's columns to a plain dict."""
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


class QuestionnaireAdminDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _assign(obj, fields: dict) -> None:
        """Set only known columns, never the primary key ``id``."""
        cols = {c.name for c in obj.__table__.columns}
        for key, value in fields.items():
            if key == "id" or key not in cols:
                continue
            setattr(obj, key, value)

    # ------------------------------------------------------------------ create
    async def create_questionnaire(self, fields: dict) -> int:
        obj = QuestionnaireDef(**{k: v for k, v in fields.items() if k != "id"})
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj.id

    async def create_group(self, fields: dict) -> int:
        obj = QuestionGroupDef(**{k: v for k, v in fields.items() if k != "id"})
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj.id

    async def create_question(self, fields: dict) -> int:
        obj = QuestionDef(**{k: v for k, v in fields.items() if k != "id"})
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj.id

    async def create_option(self, fields: dict) -> int:
        obj = OptionDef(**{k: v for k, v in fields.items() if k != "id"})
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj.id

    # ----------------------------------------------------------------- existence
    async def questionnaire_exists(self, qid) -> bool:
        if qid is None:
            return False
        res = await self.session.execute(
            select(QuestionnaireDef.id).where(QuestionnaireDef.id == qid)
        )
        return res.scalar_one_or_none() is not None

    async def group_exists(self, gid) -> bool:
        if gid is None:
            return False
        res = await self.session.execute(
            select(QuestionGroupDef.id).where(QuestionGroupDef.id == gid)
        )
        return res.scalar_one_or_none() is not None

    async def question_exists(self, qid) -> bool:
        if qid is None:
            return False
        res = await self.session.execute(
            select(QuestionDef.id).where(QuestionDef.id == qid)
        )
        return res.scalar_one_or_none() is not None

    async def key_exists(self, key, exclude_id=None) -> bool:
        if key is None:
            return False
        stmt = select(QuestionnaireDef.id).where(QuestionnaireDef.key == key)
        if exclude_id is not None:
            stmt = stmt.where(QuestionnaireDef.id != exclude_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none() is not None

    # --------------------------------------------------------------------- read
    async def get_questionnaire_tree(self, qid: int) -> dict | None:
        res = await self.session.execute(
            select(QuestionnaireDef).where(QuestionnaireDef.id == qid)
        )
        qn = res.scalar_one_or_none()
        if qn is None:
            return None

        grp_res = await self.session.execute(
            select(QuestionGroupDef).where(
                QuestionGroupDef.questionnaire_id == qid
            )
        )
        groups = [_row_to_dict(g) for g in grp_res.scalars().all()]
        group_ids = [g["id"] for g in groups]

        questions: list[dict] = []
        if group_ids:
            q_res = await self.session.execute(
                select(QuestionDef).where(QuestionDef.group_id.in_(group_ids))
            )
            questions = [_row_to_dict(q) for q in q_res.scalars().all()]
        question_ids = [q["id"] for q in questions]

        options: list[dict] = []
        if question_ids:
            o_res = await self.session.execute(
                select(OptionDef).where(OptionDef.question_id.in_(question_ids))
            )
            options = [_row_to_dict(o) for o in o_res.scalars().all()]

        assembled = assemble_structure(
            [_row_to_dict(qn)], groups, questions, options
        )
        return assembled["questionnaires"][0]

    async def get_question(self, qid: int) -> dict | None:
        res = await self.session.execute(
            select(QuestionDef).where(QuestionDef.id == qid)
        )
        obj = res.scalar_one_or_none()
        return _row_to_dict(obj) if obj is not None else None

    async def list_questionnaires(self) -> list[dict]:
        res = await self.session.execute(select(QuestionnaireDef))
        questionnaires = list(res.scalars().all())

        count_res = await self.session.execute(
            select(
                QuestionGroupDef.questionnaire_id,
                func.count(QuestionGroupDef.id),
            ).group_by(QuestionGroupDef.questionnaire_id)
        )
        counts = {row[0]: row[1] for row in count_res.all()}

        # 每问卷的题目数(题 → 组 → 问卷),供列表卡片显示;此前只有 group_count,
        # 前端"问题"数恒显示 0。
        qcount_res = await self.session.execute(
            select(
                QuestionGroupDef.questionnaire_id,
                func.count(QuestionDef.id),
            )
            .join(QuestionDef, QuestionDef.group_id == QuestionGroupDef.id)
            .group_by(QuestionGroupDef.questionnaire_id)
        )
        qcounts = {row[0]: row[1] for row in qcount_res.all()}

        return [
            {
                "id": qn.id,
                "key": qn.key,
                "title": qn.title,
                "category": qn.category,
                "required": qn.required,
                "order": qn.order,
                "group_count": counts.get(qn.id, 0),
                "question_count": qcounts.get(qn.id, 0),
            }
            for qn in questionnaires
        ]

    # ------------------------------------------------------------------- update
    async def update_questionnaire(self, qid: int, fields: dict) -> bool:
        res = await self.session.execute(
            select(QuestionnaireDef).where(QuestionnaireDef.id == qid)
        )
        obj = res.scalar_one_or_none()
        if obj is None:
            return False
        self._assign(obj, fields)
        await self.session.commit()
        return True

    async def update_group(self, gid: int, fields: dict) -> bool:
        res = await self.session.execute(
            select(QuestionGroupDef).where(QuestionGroupDef.id == gid)
        )
        obj = res.scalar_one_or_none()
        if obj is None:
            return False
        self._assign(obj, fields)
        await self.session.commit()
        return True

    async def update_question(self, qid: int, fields: dict) -> bool:
        res = await self.session.execute(
            select(QuestionDef).where(QuestionDef.id == qid)
        )
        obj = res.scalar_one_or_none()
        if obj is None:
            return False
        self._assign(obj, fields)
        await self.session.commit()
        return True

    async def update_option(self, oid: int, fields: dict) -> bool:
        res = await self.session.execute(
            select(OptionDef).where(OptionDef.id == oid)
        )
        obj = res.scalar_one_or_none()
        if obj is None:
            return False
        self._assign(obj, fields)
        await self.session.commit()
        return True

    # ------------------------------------------------------------------- delete
    async def delete_questionnaire(self, qid: int) -> bool:
        if not await self.questionnaire_exists(qid):
            return False

        grp_res = await self.session.execute(
            select(QuestionGroupDef.id).where(
                QuestionGroupDef.questionnaire_id == qid
            )
        )
        group_ids = [row[0] for row in grp_res.all()]

        question_ids: list[int] = []
        if group_ids:
            q_res = await self.session.execute(
                select(QuestionDef.id).where(
                    QuestionDef.group_id.in_(group_ids)
                )
            )
            question_ids = [row[0] for row in q_res.all()]

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
            delete(QuestionnaireDef).where(QuestionnaireDef.id == qid)
        )
        await self.session.commit()
        return True

    async def delete_group(self, gid: int) -> bool:
        if not await self.group_exists(gid):
            return False

        q_res = await self.session.execute(
            select(QuestionDef.id).where(QuestionDef.group_id == gid)
        )
        question_ids = [row[0] for row in q_res.all()]

        if question_ids:
            await self.session.execute(
                delete(OptionDef).where(
                    OptionDef.question_id.in_(question_ids)
                )
            )
            await self.session.execute(
                delete(QuestionDef).where(QuestionDef.id.in_(question_ids))
            )
        await self.session.execute(
            delete(QuestionGroupDef).where(QuestionGroupDef.id == gid)
        )
        await self.session.commit()
        return True

    async def delete_question(self, qid: int) -> bool:
        if not await self.question_exists(qid):
            return False
        await self.session.execute(
            delete(OptionDef).where(OptionDef.question_id == qid)
        )
        await self.session.execute(
            delete(QuestionDef).where(QuestionDef.id == qid)
        )
        await self.session.commit()
        return True

    async def delete_option(self, oid: int) -> bool:
        res = await self.session.execute(
            select(OptionDef.id).where(OptionDef.id == oid)
        )
        if res.scalar_one_or_none() is None:
            return False
        await self.session.execute(
            delete(OptionDef).where(OptionDef.id == oid)
        )
        await self.session.commit()
        return True
