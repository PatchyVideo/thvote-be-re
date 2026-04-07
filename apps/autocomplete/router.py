"""Autocomplete API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.autocomplete.dao import AutocompleteDAO
from apps.autocomplete.schemas import AutocompleteRequest, AutocompleteResponse
from apps.autocomplete.service import AutocompleteService
from common.database import get_db_session

router = APIRouter(prefix="/autocomplete", tags=["autocomplete"])


async def get_autocomplete_service(
    session: AsyncSession = Depends(get_db_session),
) -> AutocompleteService:
    """Dependency to get AutocompleteService instance."""
    dao = AutocompleteDAO(session)
    return AutocompleteService(dao)


@router.post("/search", response_model=AutocompleteResponse)
async def search_autocomplete(
    request: AutocompleteRequest,
    service: AutocompleteService = Depends(get_autocomplete_service),
) -> AutocompleteResponse:
    """Search for autocomplete suggestions."""
    return await service.search(request)
