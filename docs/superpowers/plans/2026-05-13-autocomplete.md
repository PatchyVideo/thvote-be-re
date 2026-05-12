# Autocomplete Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `search_characters` and `search_music` in `AutocompleteDAO` using `candidate_character` / `candidate_music` tables, and fix the per-category limit distribution in `AutocompleteService`.

**Architecture:** `AutocompleteDAO` queries the `candidate_character` / `candidate_music` tables with `ILIKE` on both `name` and `name_jp`, filtered to the current `vote_year`. The router injects `settings.vote_year` into the DAO constructor. The service distributes the `limit` equally across categories (`ceil(limit/2)` each) before merging.

**Tech Stack:** FastAPI, SQLAlchemy async (asyncpg/aiosqlite), Pydantic v2, pytest-asyncio

---

## File Map

| File | Action |
|---|---|
| `src/apps/autocomplete/dao.py` | Modify — add `vote_year` constructor param; implement `search_characters` and `search_music` |
| `src/apps/autocomplete/service.py` | Modify — fix `ceil(limit/2)` per-category limit |
| `src/apps/autocomplete/router.py` | Modify — inject `settings.vote_year` into DAO |
| `tests/unit/test_autocomplete_service.py` | Create — unit tests for service limit logic |
| `tests/integration/test_autocomplete.py` | Create — integration tests with SQLite + real DAO |

---

## Task 1: Service Limit Fix + Unit Tests (TDD)

**Files:**
- Create: `tests/unit/test_autocomplete_service.py`
- Modify: `src/apps/autocomplete/service.py`

- [ ] **Step 1: Write failing unit tests**

Create `tests/unit/test_autocomplete_service.py`:

```python
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
    # chars(2) + music(2) = 4, CP doesn't displace either
    assert len(result.suggestions) == 4
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/unit/test_autocomplete_service.py -x -q
```

Expected: `ImportError` or test failures (service doesn't have the new logic yet)

- [ ] **Step 3: Fix `src/apps/autocomplete/service.py`**

Replace the file with:

```python
"""Autocomplete service layer."""

import math

from src.apps.autocomplete.dao import AutocompleteDAO
from src.apps.autocomplete.schemas import (
    AutocompleteRequest,
    AutocompleteResponse,
    AutocompleteSuggestion,
)


class AutocompleteService:
    def __init__(self, autocomplete_dao: AutocompleteDAO):
        self.autocomplete_dao = autocomplete_dao

    async def search(self, request: AutocompleteRequest) -> AutocompleteResponse:
        per_cat = math.ceil(request.limit / 2)
        results: list[AutocompleteSuggestion] = []

        for item in await self.autocomplete_dao.search_characters(request.query, per_cat):
            results.append(AutocompleteSuggestion(
                name=item.get("name", ""),
                type="character",
                origin=item.get("origin"),
            ))

        for item in await self.autocomplete_dao.search_music(request.query, per_cat):
            results.append(AutocompleteSuggestion(
                name=item.get("name", ""),
                type="music",
                origin=item.get("origin"),
            ))

        return AutocompleteResponse(suggestions=results[: request.limit])
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/unit/test_autocomplete_service.py -v
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_autocomplete_service.py src/apps/autocomplete/service.py
git commit -m "feat(autocomplete): fix per-category limit distribution with unit tests"
```

---

## Task 2: DAO Implementation + Integration Tests (TDD)

**Files:**
- Create: `tests/integration/test_autocomplete.py`
- Modify: `src/apps/autocomplete/dao.py`

- [ ] **Step 1: Write failing integration tests**

Create `tests/integration/test_autocomplete.py`:

```python
"""Integration tests for AutocompleteDAO using SQLite."""

import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.apps.autocomplete.dao import AutocompleteDAO
from src.db_model.base import Base
from src.db_model.candidate import CandidateCharacter, CandidateMusic

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("JWT_SECRET_KEY", "test-key")
os.environ.setdefault("VOTE_START_ISO", "2026-01-01T00:00:00Z")
os.environ.setdefault("VOTE_END_ISO", "2026-12-31T23:59:59Z")

VOTE_YEAR = 2026


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        # Seed candidate data
        s.add(CandidateCharacter(vote_year=VOTE_YEAR, name="博丽灵梦", name_jp="博麗霊夢",
                                  origin="东方红魔乡", type="旧作", first_appearance="1996"))
        s.add(CandidateCharacter(vote_year=VOTE_YEAR, name="雾雨魔理沙", name_jp="霧雨魔理沙",
                                  origin="东方红魔乡", type="旧作", first_appearance="1996"))
        s.add(CandidateCharacter(vote_year=VOTE_YEAR, name="十六夜咲夜", name_jp="十六夜咲夜",
                                  origin="东方红魔乡", type="旧作", first_appearance="2002"))
        s.add(CandidateMusic(vote_year=VOTE_YEAR, name="Bad Apple!!", name_jp="Bad Apple!!",
                              type="旧作", album="Akyu's Untouched Score vol.5"))
        s.add(CandidateMusic(vote_year=VOTE_YEAR, name="U.N.オーエンは彼女なのか？",
                              name_jp="U.N.オーエンは彼女なのか？", type="旧作", album=None))
        await s.commit()
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_search_characters_by_name(session):
    dao = AutocompleteDAO(session, VOTE_YEAR)
    results = await dao.search_characters("灵梦", 10)
    assert len(results) == 1
    assert results[0]["name"] == "博丽灵梦"
    assert results[0]["origin"] == "东方红魔乡"


@pytest.mark.asyncio
async def test_search_characters_by_name_jp(session):
    dao = AutocompleteDAO(session, VOTE_YEAR)
    results = await dao.search_characters("霊夢", 10)
    assert len(results) == 1
    assert results[0]["name"] == "博丽灵梦"


@pytest.mark.asyncio
async def test_search_characters_no_match(session):
    dao = AutocompleteDAO(session, VOTE_YEAR)
    results = await dao.search_characters("不存在的名字xyz", 10)
    assert results == []


@pytest.mark.asyncio
async def test_search_characters_limit(session):
    dao = AutocompleteDAO(session, VOTE_YEAR)
    results = await dao.search_characters("夜", 2)  # matches 咲夜 and potentially 灵梦(夜?)
    assert len(results) <= 2


@pytest.mark.asyncio
async def test_search_music_by_name(session):
    dao = AutocompleteDAO(session, VOTE_YEAR)
    results = await dao.search_music("Bad", 10)
    assert len(results) == 1
    assert results[0]["name"] == "Bad Apple!!"
    assert results[0]["origin"] == "Akyu's Untouched Score vol.5"


@pytest.mark.asyncio
async def test_search_music_no_album_returns_none_origin(session):
    dao = AutocompleteDAO(session, VOTE_YEAR)
    results = await dao.search_music("U.N", 10)
    assert len(results) == 1
    assert results[0]["origin"] is None


@pytest.mark.asyncio
async def test_search_cps_returns_empty(session):
    dao = AutocompleteDAO(session, VOTE_YEAR)
    results = await dao.search_cps("anything", 10)
    assert results == []


@pytest.mark.asyncio
async def test_wrong_year_returns_nothing(session):
    dao = AutocompleteDAO(session, vote_year=9999)
    results = await dao.search_characters("灵梦", 10)
    assert results == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/integration/test_autocomplete.py -x -q
```

Expected: failures because DAO still returns `[]` and doesn't accept `vote_year`

- [ ] **Step 3: Implement `src/apps/autocomplete/dao.py`**

Replace the file with:

```python
"""Autocomplete data access objects."""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db_model.candidate import CandidateCharacter, CandidateMusic


class AutocompleteDAO:
    def __init__(self, session: AsyncSession, vote_year: int):
        self.session = session
        self.vote_year = vote_year

    async def search_characters(self, query: str, limit: int = 10) -> list[dict]:
        stmt = (
            select(CandidateCharacter)
            .where(
                CandidateCharacter.vote_year == self.vote_year,
                or_(
                    CandidateCharacter.name.ilike(f"%{query}%"),
                    CandidateCharacter.name_jp.ilike(f"%{query}%"),
                ),
            )
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [
            {"name": r.name, "origin": r.origin, "name_jp": r.name_jp, "type": r.type}
            for r in rows
        ]

    async def search_music(self, query: str, limit: int = 10) -> list[dict]:
        stmt = (
            select(CandidateMusic)
            .where(
                CandidateMusic.vote_year == self.vote_year,
                or_(
                    CandidateMusic.name.ilike(f"%{query}%"),
                    CandidateMusic.name_jp.ilike(f"%{query}%"),
                ),
            )
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [
            {"name": r.name, "origin": r.album or None, "name_jp": r.name_jp, "type": r.type}
            for r in rows
        ]

    async def search_cps(self, query: str, limit: int = 10) -> list[dict]:
        return []
```

- [ ] **Step 4: Run integration tests**

```bash
pytest tests/integration/test_autocomplete.py -v
```

Expected: 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/apps/autocomplete/dao.py tests/integration/test_autocomplete.py
git commit -m "feat(autocomplete): implement search_characters and search_music with ILIKE queries"
```

---

## Task 3: Router Dependency Injection Update

**Files:**
- Modify: `src/apps/autocomplete/router.py`

- [ ] **Step 1: Update the router dependency**

Replace `src/apps/autocomplete/router.py` with:

```python
"""Autocomplete API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.autocomplete.dao import AutocompleteDAO
from src.apps.autocomplete.schemas import AutocompleteRequest, AutocompleteResponse
from src.apps.autocomplete.service import AutocompleteService
from src.common.config import Settings, get_settings
from src.common.database import get_db_session

router = APIRouter(prefix="/autocomplete", tags=["autocomplete"])


async def get_autocomplete_service(
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AutocompleteService:
    dao = AutocompleteDAO(session, settings.vote_year)
    return AutocompleteService(dao)


@router.post("/search", response_model=AutocompleteResponse)
async def search_autocomplete(
    request: AutocompleteRequest,
    service: AutocompleteService = Depends(get_autocomplete_service),
) -> AutocompleteResponse:
    """Search for autocomplete suggestions."""
    return await service.search(request)
```

- [ ] **Step 2: Run full test suite**

```bash
pytest tests/ -q
```

Expected: 70+ pass, 1 pre-existing failure (`test_pnvs_client`)

- [ ] **Step 3: Commit**

```bash
git add src/apps/autocomplete/router.py
git commit -m "feat(autocomplete): inject vote_year from settings into AutocompleteDAO"
```

---

## Post-Implementation Checklist

- [ ] `pytest tests/ -q` — 70+ pass, 1 pre-existing failure only
- [ ] Update `REFACTOR_TODO.md`: autocomplete 状态改为 ✅
