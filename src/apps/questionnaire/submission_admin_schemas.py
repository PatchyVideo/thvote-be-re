"""Admin contracts for structured questionnaire submission batches."""
from datetime import datetime

from pydantic import BaseModel, StrictBool


class QuestionnaireProgress(BaseModel):
    id: int
    key: str
    title: str
    required: bool
    completed: bool


class SubmissionSummary(BaseModel):
    vote_id: str
    vote_year: int
    attempt: int
    created_at: datetime
    row_count: int
    invalidated: bool
    is_latest: bool
    completed: bool
    eligible: bool
    progress: list[QuestionnaireProgress]


class SubmissionsPage(BaseModel):
    items: list[SubmissionSummary]
    total: int
    page: int
    page_size: int


class SelectedOption(BaseModel):
    id: int
    content: str | None


class ReadableAnswer(BaseModel):
    id: int
    group_id: int
    active_question_id: int | None
    question_content: str | None
    question_type: str | None
    selected_options: list[SelectedOption]
    input_text: str | None
    missing_references: list[str]


class SubmissionQuestionnaire(BaseModel):
    id: int
    title: str | None
    answers: list[ReadableAnswer]


class SubmissionBatch(SubmissionSummary):
    questionnaires: list[SubmissionQuestionnaire]


class SubmissionDetail(BaseModel):
    vote_id: str
    vote_year: int
    batches: list[SubmissionBatch]


class SubmissionStatusUpdate(BaseModel):
    invalidated: StrictBool


class SubmissionActionResult(BaseModel):
    affected_rows: int
    invalidated: bool
    detail: str
