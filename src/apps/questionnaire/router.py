"""Questionnaire public router: structure query."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.questionnaire.dao import QuestionnaireDAO
from src.apps.questionnaire.service import QuestionnaireService
from src.common.database import get_db_session

router = APIRouter(prefix="/questionnaire", tags=["questionnaire"])


async def get_questionnaire_service(
    session: AsyncSession = Depends(get_db_session),
) -> QuestionnaireService:
    return QuestionnaireService(QuestionnaireDAO(session))


@router.get("/structure")
async def get_structure(
    service: QuestionnaireService = Depends(get_questionnaire_service),
) -> dict:
    return await service.get_structure()
