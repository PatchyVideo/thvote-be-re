"""Questionnaire admin service: 4-level CRUD with validation."""
from __future__ import annotations

from src.apps.questionnaire.admin_dao import QuestionnaireAdminDAO

# 显式可写字段集合(question/option):防止请求体里混入非法列名,同时明确
# 声明 admin 编辑器能设置哪些字段——`code` 是语义码(题 5 位/选项 7 位),
# 见 db_model/questionnaire_def.py 的字段注释。
_QUESTION_WRITABLE_FIELDS = {
    "group_id", "type", "content", "introduction", "order", "max_input_len",
    "code",
}
_OPTION_WRITABLE_FIELDS = {
    "question_id", "content", "related_question_ids", "mutex_option_ids",
    "option_group", "order", "code",
}


def _pick_writable(fields: dict, allowed: set[str]) -> dict:
    """Keep only known writable columns from a raw request-body dict."""
    return {k: v for k, v in fields.items() if k in allowed}


class KeyConflictError(Exception):
    """Questionnaire key already exists."""


class ParentNotFoundError(Exception):
    """Parent node (questionnaire/group/question) does not exist."""


class QuestionnaireAdminService:
    def __init__(self, dao: QuestionnaireAdminDAO) -> None:
        self.dao = dao

    async def list_questionnaires(self) -> list[dict]:
        return await self.dao.list_questionnaires()

    async def get_questionnaire(self, qid: int) -> dict | None:
        return await self.dao.get_questionnaire_tree(qid)

    async def get_question(self, qid: int) -> dict | None:
        return await self.dao.get_question(qid)

    async def create_questionnaire(self, fields: dict) -> int:
        if await self.dao.key_exists(fields.get("key")):
            raise KeyConflictError(fields.get("key"))
        return await self.dao.create_questionnaire(fields)

    async def update_questionnaire(self, qid: int, fields: dict) -> bool:
        new_key = fields.get("key")
        if new_key and await self.dao.key_exists(new_key, exclude_id=qid):
            raise KeyConflictError(new_key)
        return await self.dao.update_questionnaire(qid, fields)

    async def delete_questionnaire(self, qid: int) -> bool:
        return await self.dao.delete_questionnaire(qid)

    async def create_group(self, fields: dict) -> int:
        if not await self.dao.questionnaire_exists(fields.get("questionnaire_id")):
            raise ParentNotFoundError("questionnaire")
        return await self.dao.create_group(fields)

    async def update_group(self, gid: int, fields: dict) -> bool:
        return await self.dao.update_group(gid, fields)

    async def delete_group(self, gid: int) -> bool:
        return await self.dao.delete_group(gid)

    async def create_question(self, fields: dict) -> int:
        if not await self.dao.group_exists(fields.get("group_id")):
            raise ParentNotFoundError("group")
        return await self.dao.create_question(
            _pick_writable(fields, _QUESTION_WRITABLE_FIELDS)
        )

    async def update_question(self, qid: int, fields: dict) -> bool:
        return await self.dao.update_question(
            qid, _pick_writable(fields, _QUESTION_WRITABLE_FIELDS)
        )

    async def delete_question(self, qid: int) -> bool:
        return await self.dao.delete_question(qid)

    async def create_option(self, fields: dict) -> int:
        if not await self.dao.question_exists(fields.get("question_id")):
            raise ParentNotFoundError("question")
        return await self.dao.create_option(
            _pick_writable(fields, _OPTION_WRITABLE_FIELDS)
        )

    async def update_option(self, oid: int, fields: dict) -> bool:
        return await self.dao.update_option(
            oid, _pick_writable(fields, _OPTION_WRITABLE_FIELDS)
        )

    async def delete_option(self, oid: int) -> bool:
        return await self.dao.delete_option(oid)
