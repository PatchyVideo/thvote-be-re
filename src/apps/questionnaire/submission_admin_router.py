"""Protected administration endpoints for structured questionnaire submissions."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.admin.deps import require_admin
from src.apps.questionnaire.dao import QuestionnaireDAO
from src.apps.questionnaire.submission_admin_dao import SubmissionAdminDAO
from src.apps.questionnaire.submission_admin_schemas import (
    SubmissionActionResult, SubmissionDetail, SubmissionsPage, SubmissionStatusUpdate,
)
from src.apps.questionnaire.submission_admin_service import SubmissionAdminService
from src.common.config import Settings, get_settings
from src.common.database import get_db_session

router = APIRouter(
    prefix="/admin/questionnaire-submissions", tags=["questionnaire-submissions"],
    dependencies=[Depends(require_admin)],
)


def service(
    session: AsyncSession = Depends(get_db_session),
) -> SubmissionAdminService:
    return SubmissionAdminService(
        SubmissionAdminDAO(session), QuestionnaireDAO(session),
    )


@router.get("", response_model=SubmissionsPage)
async def list_submissions(
    vote_year: Annotated[int | None, Query(gt=0)] = None,
    vote_id: Annotated[str | None, Query(max_length=255)] = None,
    invalidated: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    svc: SubmissionAdminService = Depends(service),
    settings: Settings = Depends(get_settings),
) -> SubmissionsPage:
    return await svc.list_latest(
        vote_year or settings.vote_year, vote_id, invalidated, page, page_size,
    )


@router.get("/{vote_year}/{vote_id}", response_model=SubmissionDetail)
async def submission_detail(
    vote_year: Annotated[int, Path(gt=0)], vote_id: str,
    svc: SubmissionAdminService = Depends(service),
) -> SubmissionDetail:
    result = await svc.detail(vote_id, vote_year)
    if result is None:
        raise HTTPException(status_code=404, detail="答卷不存在")
    return result


@router.patch("/{vote_year}/{vote_id}/{attempt}", response_model=SubmissionActionResult)
async def update_submission(
    vote_year: Annotated[int, Path(gt=0)], vote_id: str,
    attempt: Annotated[int, Path(ge=0)], body: SubmissionStatusUpdate,
    svc: SubmissionAdminService = Depends(service),
) -> SubmissionActionResult:
    result = await svc.set_invalidated(vote_id, vote_year, attempt, body.invalidated)
    if result is None:
        raise HTTPException(status_code=404, detail="答卷批次不存在")
    return result
