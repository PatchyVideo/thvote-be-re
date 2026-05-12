"""Unit tests for AutocompleteService limit distribution."""

import math
from unittest.mock import AsyncMock

import pytest

from src.apps.autocomplete.schemas import AutocompleteRequest
from src.apps.autocomplete.service import AutocompleteService


def _make_suggestions(n: int, type_: str) -> list[dict]:
    return [{"name": f"{type_}{i}", "origin": "orig", "name_jp": "", "type": type_} for i in range(n)]


@pytest.fixture
def mock_dao():
    dao = AsyncMock()
    dao.search_characters = AsyncMock(return_value=_make_suggestions(10, "char"))
    dao.search_music = AsyncMock(return_value=_make_suggestions(10, "music"))
    dao.search_cps = AsyncMock(return_value=[])
    return dao


@pytest.mark.asyncio
async def test_limit_distributed_equally(mock_dao):
    """Each category gets ceil(limit/2) items queried from DAO."""
    service = AutocompleteService(mock_dao)
    await service.search(AutocompleteRequest(query="x", limit=10))
    mock_dao.search_characters.assert_called_once_with("x", math.ceil(10 / 2))
    mock_dao.search_music.assert_called_once_with("x", math.ceil(10 / 2))


@pytest.mark.asyncio
async def test_total_capped_at_limit(mock_dao):
    """Total suggestions never exceed request.limit."""
    service = AutocompleteService(mock_dao)
    result = await service.search(AutocompleteRequest(query="x", limit=6))
    assert len(result.suggestions) <= 6


@pytest.mark.asyncio
async def test_odd_limit_distributed(mock_dao):
    """ceil(7/2) = 4 per category."""
    service = AutocompleteService(mock_dao)
    await service.search(AutocompleteRequest(query="x", limit=7))
    mock_dao.search_characters.assert_called_once_with("x", 4)
    mock_dao.search_music.assert_called_once_with("x", 4)


@pytest.mark.asyncio
async def test_cp_not_counted_in_limit(mock_dao):
    """CP returns [] and doesn't consume limit quota."""
    service = AutocompleteService(mock_dao)
    mock_dao.search_cps = AsyncMock(return_value=[])
    result = await service.search(AutocompleteRequest(query="x", limit=4))
    assert len(result.suggestions) == 4
