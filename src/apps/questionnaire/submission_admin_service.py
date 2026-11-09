"""Readable V2 answers and shared completion policy for the administration UI."""
from src.apps.questionnaire.assembler import assemble_structure
from src.apps.questionnaire.completion import (
    completed_questionnaire_ids, meets_completion_policy,
)
from src.apps.questionnaire.dao import QuestionnaireDAO
from src.apps.questionnaire.structure_index import StructureIndex
from src.apps.questionnaire.submission_admin_dao import SubmissionAdminDAO
from src.apps.questionnaire.submission_admin_schemas import (
    QuestionnaireProgress, ReadableAnswer, SelectedOption, SubmissionActionResult,
    SubmissionBatch, SubmissionDetail, SubmissionQuestionnaire, SubmissionSummary,
    SubmissionsPage,
)
from src.db_model.questionnaire_def import PaperAnswer


class SubmissionAdminService:
    def __init__(
        self, dao: SubmissionAdminDAO, questionnaire_dao: QuestionnaireDAO,
    ) -> None:
        self.dao = dao
        self.questionnaire_dao = questionnaire_dao

    async def _index(self) -> StructureIndex:
        rows = await self.questionnaire_dao.load_structure_rows()
        return StructureIndex(assemble_structure(*rows))

    @staticmethod
    def _summary(
        rows: list[PaperAnswer], index: StructureIndex, latest: int,
    ) -> SubmissionSummary:
        fields = (
            "questionnaire_id", "group_id", "active_question_id",
            "selected_option_ids", "input_text",
        )
        completed_ids = completed_questionnaire_ids(index, [
            {key: getattr(row, key) for key in fields} for row in rows
        ])
        completed = meets_completion_policy(index.questionnaires, completed_ids)
        invalidated = any(row.invalidated for row in rows)
        attempt = rows[0].attempt or 0
        return SubmissionSummary(
            vote_id=rows[0].vote_id, vote_year=rows[0].vote_year, attempt=attempt,
            created_at=max(row.created_at for row in rows), row_count=len(rows),
            invalidated=invalidated, is_latest=attempt == latest, completed=completed,
            eligible=completed and not invalidated and attempt == latest,
            progress=[QuestionnaireProgress(
                id=qn["id"], key=qn["key"], title=qn["title"], required=qn["required"],
                completed=qn["id"] in completed_ids,
            ) for qn in index.questionnaires],
        )

    async def list_latest(
        self, vote_year: int, vote_id: str | None, invalidated: bool | None,
        page: int, page_size: int,
    ) -> SubmissionsPage:
        batches, total = await self.dao.list_latest(
            vote_year, vote_id, invalidated, page, page_size,
        )
        index = await self._index()
        return SubmissionsPage(
            items=[
                self._summary(rows, index, rows[0].attempt or 0) for rows in batches
            ],
            total=total, page=page, page_size=page_size,
        )

    @staticmethod
    def _answer(row: PaperAnswer, index: StructureIndex) -> ReadableAnswer:
        missing = []
        group_valid = (
            index.group_questionnaire.get(row.group_id) == row.questionnaire_id
        )
        question_valid = (
            group_valid
            and index.question_group.get(row.active_question_id) == row.group_id
        )
        question = (
            index.questions.get(row.active_question_id) if question_valid else None
        )
        if not group_valid:
            missing.append("题组定义不存在或归属已变化")
        if row.active_question_id is not None and not question:
            missing.append("题目定义不存在或归属已变化")
        options = (
            index.question_options.get(row.active_question_id, {}) if question else {}
        )
        selected = []
        for oid in row.selected_option_ids or []:
            option = options.get(oid)
            if option is None:
                missing.append(f"选项定义不存在或归属已变化：{oid}")
            selected.append(SelectedOption(
                id=oid, content=option["content"] if option else None,
            ))
        return ReadableAnswer(
            id=row.id, group_id=row.group_id, active_question_id=row.active_question_id,
            question_content=question["content"] if question else None,
            question_type=question["type"] if question else None,
            selected_options=selected, input_text=row.input_text,
            missing_references=missing,
        )

    async def detail(
        self, vote_id: str, vote_year: int,
    ) -> SubmissionDetail | None:
        rows = await self.dao.history(vote_id, vote_year)
        if not rows:
            return None
        index = await self._index()
        definitions = {qn["id"]: qn for qn in index.questionnaires}
        batches: dict[int, list[PaperAnswer]] = {}
        for row in rows:
            batches.setdefault(row.attempt or 0, []).append(row)
        latest = max(batches)
        result = []
        group_order = {gid: i for i, gid in enumerate(index.groups)}
        qn_order = {qn["id"]: i for i, qn in enumerate(index.questionnaires)}
        for attempt, batch in batches.items():
            questionnaires: dict[int, list[ReadableAnswer]] = {}
            ordered_rows = sorted(batch, key=lambda r: (
                qn_order.get(r.questionnaire_id, len(qn_order)),
                group_order.get(r.group_id, len(group_order)), r.id,
            ))
            for row in ordered_rows:
                questionnaires.setdefault(row.questionnaire_id, []).append(
                    self._answer(row, index)
                )
            result.append(SubmissionBatch(
                **self._summary(batch, index, latest).model_dump(),
                questionnaires=[SubmissionQuestionnaire(
                    id=qid,
                    title=definitions[qid]["title"] if qid in definitions else None,
                    answers=answers,
                ) for qid, answers in questionnaires.items()],
            ))
        return SubmissionDetail(vote_id=vote_id, vote_year=vote_year, batches=result)

    async def set_invalidated(
        self, vote_id: str, vote_year: int, attempt: int, invalidated: bool,
    ) -> SubmissionActionResult | None:
        count = await self.dao.set_invalidated(vote_id, vote_year, attempt, invalidated)
        if not count:
            return None
        return SubmissionActionResult(
            affected_rows=count, invalidated=invalidated,
            detail="已更新整次答卷状态；已有统计和筛选缓存需要重新计票后更新",
        )
