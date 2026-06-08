"""Questionnaire admin CRUD router (B-041). All endpoints require X-Admin-Secret."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.questionnaire.admin_dao import QuestionnaireAdminDAO
from src.apps.questionnaire.admin_service import (
    KeyConflictError,
    ParentNotFoundError,
    QuestionnaireAdminService,
)
from src.apps.questionnaire.dao import QuestionnaireDAO
from src.apps.questionnaire.service import QuestionnaireService
from src.common.config import Settings, get_settings
from src.common.database import get_db_session

router = APIRouter(prefix="/admin", tags=["questionnaire-admin"])


def _check_admin_secret(settings: Settings, secret: Optional[str]) -> None:
    if settings.admin_secret and secret != settings.admin_secret:
        raise HTTPException(status_code=403, detail="FORBIDDEN")


async def _svc(session: AsyncSession) -> QuestionnaireAdminService:
    return QuestionnaireAdminService(QuestionnaireAdminDAO(session))


# ── questionnaires ──────────────────────────────────────────────────────────


@router.get("/questionnaires")
async def list_questionnaires(
    x_admin_secret: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    items = await (await _svc(session)).list_questionnaires()
    return {"items": items}


@router.get("/questionnaires/{qid}")
async def get_questionnaire(
    qid: int,
    x_admin_secret: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    obj = await (await _svc(session)).get_questionnaire(qid)
    if obj is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return obj


@router.post("/questionnaires")
async def create_questionnaire(
    body: dict,
    x_admin_secret: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    try:
        new_id = await (await _svc(session)).create_questionnaire(body)
    except KeyConflictError:
        raise HTTPException(status_code=409, detail="QUESTIONNAIRE_KEY_CONFLICT")
    return {"ok": True, "id": new_id}


@router.put("/questionnaires/{qid}")
async def update_questionnaire(
    qid: int,
    body: dict,
    x_admin_secret: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    try:
        ok = await (await _svc(session)).update_questionnaire(qid, body)
    except KeyConflictError:
        raise HTTPException(status_code=409, detail="QUESTIONNAIRE_KEY_CONFLICT")
    if not ok:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return {"ok": True}


@router.delete("/questionnaires/{qid}")
async def delete_questionnaire(
    qid: int,
    x_admin_secret: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    if not await (await _svc(session)).delete_questionnaire(qid):
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return {"ok": True}


# ── question-groups ─────────────────────────────────────────────────────────


@router.post("/question-groups")
async def create_question_group(
    body: dict,
    x_admin_secret: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    try:
        new_id = await (await _svc(session)).create_group(body)
    except ParentNotFoundError:
        raise HTTPException(status_code=404, detail="PARENT_NOT_FOUND")
    return {"ok": True, "id": new_id}


@router.put("/question-groups/{gid}")
async def update_question_group(
    gid: int,
    body: dict,
    x_admin_secret: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    if not await (await _svc(session)).update_group(gid, body):
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return {"ok": True}


@router.delete("/question-groups/{gid}")
async def delete_question_group(
    gid: int,
    x_admin_secret: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    if not await (await _svc(session)).delete_group(gid):
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return {"ok": True}


# ── questions ───────────────────────────────────────────────────────────────


@router.post("/questions")
async def create_question(
    body: dict,
    x_admin_secret: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    try:
        new_id = await (await _svc(session)).create_question(body)
    except ParentNotFoundError:
        raise HTTPException(status_code=404, detail="PARENT_NOT_FOUND")
    return {"ok": True, "id": new_id}


@router.put("/questions/{qid}")
async def update_question(
    qid: int,
    body: dict,
    x_admin_secret: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    if not await (await _svc(session)).update_question(qid, body):
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return {"ok": True}


@router.delete("/questions/{qid}")
async def delete_question(
    qid: int,
    x_admin_secret: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    if not await (await _svc(session)).delete_question(qid):
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return {"ok": True}


# ── options ─────────────────────────────────────────────────────────────────


@router.post("/options")
async def create_option(
    body: dict,
    x_admin_secret: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    try:
        new_id = await (await _svc(session)).create_option(body)
    except ParentNotFoundError:
        raise HTTPException(status_code=404, detail="PARENT_NOT_FOUND")
    return {"ok": True, "id": new_id}


@router.put("/options/{oid}")
async def update_option(
    oid: int,
    body: dict,
    x_admin_secret: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    if not await (await _svc(session)).update_option(oid, body):
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return {"ok": True}


@router.delete("/options/{oid}")
async def delete_option(
    oid: int,
    x_admin_secret: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    if not await (await _svc(session)).delete_option(oid):
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return {"ok": True}


# ── import ──────────────────────────────────────────────────────────────────


@router.post("/questionnaire/import")
async def import_structure(
    body: dict,
    x_admin_secret: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Replace the whole questionnaire structure from a tree.

    Body is a ``{"questionnaires":[...]}`` array tree.
    """
    _check_admin_secret(settings, x_admin_secret)
    svc = QuestionnaireService(QuestionnaireDAO(session))
    count = await svc.import_structure(body)
    return {"ok": True, "imported_questionnaires": count}
