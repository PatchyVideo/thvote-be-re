"""Integration tests: questionnaire question/option semantic ``code`` column.

Covers the three behaviors required by the result-graphql-compat plan's
questionnaire foundation (Task 1): import persists ``code``, import without
``code`` stays backward-compatible (None, no error), and the structure
assembler emits ``code`` on question/option nodes.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from src.apps.questionnaire.assembler import assemble_structure
from src.apps.questionnaire.dao import QuestionnaireDAO
from src.db_model.questionnaire_def import OptionDef, QuestionDef


def _tree_with_code() -> dict:
    return {"questionnaires": [
        {"key": "gender", "title": "性别", "questionGroups": [
            {"order": 1, "questions": [
                {"type": "Single", "content": "性别", "code": "11011", "options": [
                    {"content": "男", "code": "1101101"},
                    {"content": "女", "code": "1101102"},
                ]},
            ]},
        ]},
    ]}


def _tree_without_code() -> dict:
    return {"questionnaires": [
        {"key": "legacy", "title": "旧题库", "questionGroups": [
            {"order": 1, "questions": [
                {"type": "Single", "content": "旧题", "options": [
                    {"content": "选项一"},
                ]},
            ]},
        ]},
    ]}


@pytest.mark.asyncio
async def test_import_with_code_persists_to_db(session):
    dao = QuestionnaireDAO(session)
    await dao.replace_structure_tree(_tree_with_code())

    question = (await session.execute(select(QuestionDef))).scalars().one()
    assert question.code == "11011"

    options = (await session.execute(select(OptionDef))).scalars().all()
    codes = {o.code for o in options}
    assert codes == {"1101101", "1101102"}


@pytest.mark.asyncio
async def test_import_without_code_defaults_to_none(session):
    dao = QuestionnaireDAO(session)
    await dao.replace_structure_tree(_tree_without_code())

    question = (await session.execute(select(QuestionDef))).scalars().one()
    assert question.code is None

    option = (await session.execute(select(OptionDef))).scalars().one()
    assert option.code is None


@pytest.mark.asyncio
async def test_assembler_output_includes_code(session):
    dao = QuestionnaireDAO(session)
    await dao.replace_structure_tree(_tree_with_code())

    qns, groups, questions, options = await dao.load_structure_rows()
    structure = assemble_structure(qns, groups, questions, options)

    question_node = structure["questionnaires"][0]["questionGroups"][0]["questions"][0]
    assert question_node["code"] == "11011"

    option_codes = {o["code"] for o in question_node["options"]}
    assert option_codes == {"1101101", "1101102"}
