# Result Query Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the complete result query module — candidate reference tables, vote_data schema enrichment (rich objects with first/reason), pre-computation pipeline (ComputeService → Redis), Redis-backed ResultDAO, and three admin endpoints.

**Architecture:** ComputeService reads all vote data from PostgreSQL (character/music/cp/questionnaire + candidate tables), runs pure compute functions, then bulk-writes JSON blobs to Redis. ResultDAO reads from Redis only and raises ResultNotComputedError (→ 503) if the key is absent. Admin endpoints trigger computation, bulk-import candidate metadata, and archive final rankings for historical comparison.

**Tech Stack:** FastAPI, SQLAlchemy async (asyncpg/aiosqlite), aioredis, Pydantic v2, pytest-asyncio, fakeredis

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `src/common/config.py` | Modify | Add GENDER_QUESTION_ID, GENDER_MALE/FEMALE_VALUE, ADMIN_SECRET |
| `src/db_model/candidate.py` | Create | CandidateCharacter, CandidateMusic, FinalRanking ORM models |
| `src/db_model/__init__.py` | Modify | Export new models |
| `alembic/versions/0003_candidate_and_final_ranking.py` | Create | Migration for three new tables |
| `src/apps/vote_data/schemas.py` | Modify | Add CharacterVoteItem/MusicVoteItem/CpVoteItem; change list[str] → list[VoteItem] |
| `src/apps/vote_data/service.py` | Modify | Store model_dump() dicts instead of raw strings |
| `src/apps/result/schemas.py` | Modify | Add vote_year + category to query types; update CovoteQuery |
| `src/apps/result/compute.py` | Create | Pure compute functions (no I/O, fully unit-testable) |
| `src/apps/result/compute_dao.py` | Create | ComputeDAO — reads raw data from PG for computation |
| `src/apps/result/compute_service.py` | Create | ComputeService — orchestrates compute_dao + compute + Redis writes |
| `src/apps/result/dao.py` | Rewrite | ResultDAO — reads from Redis, raises on cache miss |
| `src/apps/result/router.py` | Modify | Fix dependency injection (redis not session); add 503 handler |
| `src/apps/result/service.py` | Modify | Fix double-call bug in get_single_entity |
| `src/apps/admin/__init__.py` | Create | Package marker |
| `src/apps/admin/schemas.py` | Create | ImportCandidatesRequest, ComputeResultsResponse |
| `src/apps/admin/service.py` | Create | AdminService (wraps ComputeService + ComputeDAO) |
| `src/apps/admin/router.py` | Create | /admin/compute-results, /admin/import-candidates, /admin/finalize-ranking |
| `src/api/rest/v1/__init__.py` | Modify | Include admin_router |
| `tests/unit/test_compute.py` | Create | Unit tests for pure compute functions |
| `tests/integration/test_result_compute.py` | Create | Integration: SQLite + fakeredis end-to-end |
| `tests/contract/test_result_endpoints.py` | Create | Contract: 503 before compute, 200 after |

---

## Task 1: Config Additions

**Files:**
- Modify: `src/common/config.py`

- [ ] **Step 1: Add four new fields to Settings class**

In `src/common/config.py`, find the `# 投票配置` block (around line 175) and add after `vote_end_iso`:

```python
    # 投票配置
    vote_year: int = Field(2026, env="VOTE_YEAR")
    vote_start_iso: str = Field("2026-01-01T00:00:00Z", env="VOTE_START_ISO")
    vote_end_iso: str = Field("2026-12-31T23:59:59Z", env="VOTE_END_ISO")

    # 结果计算配置
    gender_question_id: str = Field("q11011", env="GENDER_QUESTION_ID")
    gender_male_value: str = Field("male", env="GENDER_MALE_VALUE")
    gender_female_value: str = Field("female", env="GENDER_FEMALE_VALUE")
    admin_secret: str | None = Field(None, env="ADMIN_SECRET")
```

- [ ] **Step 2: Verify settings load without error**

```bash
cd /d/personal/thvote && python -c "from src.common.config import get_settings; s = get_settings(); print(s.gender_question_id, s.vote_year)"
```

Expected output: `q11011 2026`

- [ ] **Step 3: Commit**

```bash
git add src/common/config.py
git commit -m "feat(config): add gender question, admin secret settings for result compute"
```

---

## Task 2: DB Models

**Files:**
- Create: `src/db_model/candidate.py`
- Modify: `src/db_model/__init__.py`

- [ ] **Step 1: Create `src/db_model/candidate.py`**

```python
from sqlalchemy import Column, Integer, String, UniqueConstraint

from .base import Base


class CandidateCharacter(Base):
    __tablename__ = "candidate_character"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vote_year = Column(Integer, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    name_jp = Column(String(255), nullable=False, server_default="")
    origin = Column(String, nullable=False, server_default="")
    type = Column(String(64), nullable=False, server_default="")
    first_appearance = Column(String(16), nullable=True)

    __table_args__ = (
        UniqueConstraint("vote_year", "name", name="uq_candidate_char_year_name"),
    )


class CandidateMusic(Base):
    __tablename__ = "candidate_music"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vote_year = Column(Integer, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    name_jp = Column(String(255), nullable=False, server_default="")
    type = Column(String(64), nullable=False, server_default="")
    first_appearance = Column(String(16), nullable=True)
    album = Column(String(255), nullable=True)

    __table_args__ = (
        UniqueConstraint("vote_year", "name", name="uq_candidate_music_year_name"),
    )


class FinalRanking(Base):
    __tablename__ = "final_ranking"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vote_year = Column(Integer, nullable=False, index=True)
    category = Column(String(16), nullable=False)
    rank = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    vote_count = Column(Integer, nullable=False)
    first_vote_count = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "vote_year", "category", "rank", name="uq_final_ranking_year_cat_rank"
        ),
    )
```

- [ ] **Step 2: Export from `src/db_model/__init__.py`**

Add these imports and exports:

```python
from .candidate import CandidateCharacter, CandidateMusic, FinalRanking
```

And add to `__all__`:
```python
    "CandidateCharacter",
    "CandidateMusic",
    "FinalRanking",
```

- [ ] **Step 3: Verify import**

```bash
python -c "from src.db_model import CandidateCharacter, CandidateMusic, FinalRanking; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add src/db_model/candidate.py src/db_model/__init__.py
git commit -m "feat(db_model): add CandidateCharacter, CandidateMusic, FinalRanking models"
```

---

## Task 3: Alembic Migration 0003

**Files:**
- Create: `alembic/versions/0003_candidate_and_final_ranking.py`

- [ ] **Step 1: Create migration file**

```python
"""add candidate_character, candidate_music, final_ranking tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidate_character",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vote_year", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_jp", sa.String(255), nullable=False, server_default=""),
        sa.Column("origin", sa.Text(), nullable=False, server_default=""),
        sa.Column("type", sa.String(64), nullable=False, server_default=""),
        sa.Column("first_appearance", sa.String(16), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vote_year", "name", name="uq_candidate_char_year_name"),
    )
    op.create_index("ix_candidate_character_vote_year", "candidate_character", ["vote_year"])

    op.create_table(
        "candidate_music",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vote_year", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_jp", sa.String(255), nullable=False, server_default=""),
        sa.Column("type", sa.String(64), nullable=False, server_default=""),
        sa.Column("first_appearance", sa.String(16), nullable=True),
        sa.Column("album", sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vote_year", "name", name="uq_candidate_music_year_name"),
    )
    op.create_index("ix_candidate_music_vote_year", "candidate_music", ["vote_year"])

    op.create_table(
        "final_ranking",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vote_year", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("vote_count", sa.Integer(), nullable=False),
        sa.Column("first_vote_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "vote_year", "category", "rank", name="uq_final_ranking_year_cat_rank"
        ),
    )
    op.create_index("ix_final_ranking_vote_year", "final_ranking", ["vote_year"])


def downgrade() -> None:
    op.drop_table("final_ranking")
    op.drop_table("candidate_music")
    op.drop_table("candidate_character")
```

- [ ] **Step 2: Verify migration history is consistent**

```bash
alembic history
```

Expected: shows `0001 → 0002 → 0003`

- [ ] **Step 3: Apply migration to local DB (if running)**

```bash
alembic upgrade head
```

Expected: runs without error, prints `Running upgrade 0002 -> 0003`

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/0003_candidate_and_final_ranking.py
git commit -m "feat(alembic): migration 0003 — candidate_character, candidate_music, final_ranking"
```

---

## Task 4: vote_data Schema Enrichment

**Files:**
- Modify: `src/apps/vote_data/schemas.py`
- Modify: `src/apps/vote_data/service.py`

- [ ] **Step 1: Add VoteItem types and update Request schemas in `src/apps/vote_data/schemas.py`**

Replace the existing file content with:

```python
"""Vote data schemas for request/response validation."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CharacterVoteItem(BaseModel):
    id: str
    first: bool = False
    reason: str | None = None


class MusicVoteItem(BaseModel):
    id: str
    first: bool = False
    reason: str | None = None


class CpVoteItem(BaseModel):
    id_a: str
    id_b: str
    id_c: str | None = None
    active: str | None = None
    first: bool = False
    reason: str | None = None


class CharacterVoteRequest(BaseModel):
    character_list: list[CharacterVoteItem] = Field(..., min_length=1)


class MusicVoteRequest(BaseModel):
    music_list: list[MusicVoteItem] = Field(..., min_length=1)


class CpVoteRequest(BaseModel):
    cp_list: list[CpVoteItem] = Field(..., min_length=1)


class QuestionnaireVoteRequest(BaseModel):
    questionnaire_list: list[dict[str, Any]] = Field(..., min_length=1)


class CharacterVoteResponse(BaseModel):
    id: str
    submit_datetime: datetime
    character_list: list[dict[str, Any]]

    class Config:
        from_attributes = True


class MusicVoteResponse(BaseModel):
    id: str
    submit_datetime: datetime
    music_list: list[dict[str, Any]]

    class Config:
        from_attributes = True


class CpVoteResponse(BaseModel):
    id: str
    submit_datetime: datetime
    cp_list: list[dict[str, Any]]

    class Config:
        from_attributes = True


class QuestionnaireVoteResponse(BaseModel):
    id: str
    submit_datetime: datetime
    questionnaire_list: list[dict[str, Any]]

    class Config:
        from_attributes = True


class VoteDataSummaryResponse(BaseModel):
    user_id: str
    has_character: bool
    has_music: bool
    has_cp: bool
    has_questionnaire: bool
```

- [ ] **Step 2: Update `src/apps/vote_data/service.py` to store dicts**

In `VoteDataService.submit_character_vote`, change:
```python
# OLD
character = Character(
    id=user_id,
    submit_datetime=datetime.utcnow(),
    character_list=request.character_list,
)
```
to:
```python
# NEW
character = Character(
    id=user_id,
    submit_datetime=datetime.utcnow(),
    character_list=[item.model_dump() for item in request.character_list],
)
```

Also update `update_character` call:
```python
await self.vote_data_dao.update_character(
    user_id, [item.model_dump() for item in request.character_list]
)
```

And the response:
```python
return CharacterVoteResponse(
    id=user_id,
    submit_datetime=datetime.utcnow(),
    character_list=[item.model_dump() for item in request.character_list],
)
```

Apply the same changes to `submit_music_vote` (use `request.music_list`) and `submit_cp_vote` (use `request.cp_list`).

- [ ] **Step 3: Run existing tests to confirm no regression**

```bash
pytest tests/ -x -q
```

Expected: all existing tests pass (the vote_data tests will adjust since character_list is now list[dict])

- [ ] **Step 4: Commit**

```bash
git add src/apps/vote_data/schemas.py src/apps/vote_data/service.py
git commit -m "feat(vote_data): enrich character/music/cp_list to store first+reason objects"
```

---

## Task 5: Compute Pure Functions + Unit Tests (TDD)

**Files:**
- Create: `tests/unit/test_compute.py`
- Create: `src/apps/result/compute.py`

- [ ] **Step 1: Write failing tests in `tests/unit/test_compute.py`**

```python
"""Unit tests for pure compute functions."""

from datetime import datetime, timezone

import pytest

from src.apps.result.compute import (
    CandidateMeta,
    compute_completion_rates,
    compute_covote,
    compute_gender_map,
    compute_global_stats,
    compute_paper_results,
    compute_cp_ranking,
    compute_ranking,
)

VOTE_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
TOTAL_HOURS = 24 * 7  # 7-day voting window


def _dt(hour_offset: int) -> datetime:
    from datetime import timedelta
    return VOTE_START + timedelta(hours=hour_offset)


# ── compute_gender_map ────────────────────────────────────────────────

def test_compute_gender_map_basic():
    q_votes = [
        ("u1", [{"id": "q11011", "answer": ["male"], "answer_str": None}]),
        ("u2", [{"id": "q11011", "answer": ["female"], "answer_str": None}]),
        ("u3", [{"id": "q11011", "answer": None, "answer_str": None}]),
        ("u4", [{"id": "other_q", "answer": ["male"], "answer_str": None}]),
    ]
    result = compute_gender_map(q_votes, "q11011", "male", "female")
    assert result["u1"] == "male"
    assert result["u2"] == "female"
    assert result["u3"] == "unknown"
    assert result["u4"] == "unknown"


def test_compute_gender_map_answer_str_fallback():
    q_votes = [
        ("u1", [{"id": "q11011", "answer": None, "answer_str": "male"}]),
    ]
    result = compute_gender_map(q_votes, "q11011", "male", "female")
    assert result["u1"] == "male"


# ── compute_ranking ───────────────────────────────────────────────────

CANDIDATES = {
    "Alice": CandidateMeta(name="Alice", name_jp="アリス", origin="EoSD", type="旧作", first_appearance="2002"),
    "Bob":   CandidateMeta(name="Bob",   name_jp="ボブ",   origin="PCB",  type="旧作", first_appearance="2003"),
}

CHAR_VOTES = [
    ("u1", _dt(1), [{"id": "Alice", "first": True,  "reason": "love her"},
                    {"id": "Bob",   "first": False, "reason": None}]),
    ("u2", _dt(2), [{"id": "Alice", "first": False, "reason": "cute"}]),
    ("u3", _dt(3), [{"id": "Bob",   "first": True,  "reason": None}]),
]
GENDER_MAP = {"u1": "male", "u2": "female", "u3": "male"}


def test_compute_ranking_vote_counts():
    ranking, global_stats = compute_ranking(
        CHAR_VOTES, CANDIDATES, GENDER_MAP, {}, VOTE_START, TOTAL_HOURS
    )
    by_name = {e["name"]: e for e in ranking}
    assert by_name["Alice"]["rank"][0]["vote_count"] == 2
    assert by_name["Bob"]["rank"][0]["vote_count"] == 2
    assert by_name["Alice"]["rank"][0]["favorite_vote_count"] == 1
    assert by_name["Bob"]["rank"][0]["favorite_vote_count"] == 1


def test_compute_ranking_reasons():
    ranking, _ = compute_ranking(
        CHAR_VOTES, CANDIDATES, GENDER_MAP, {}, VOTE_START, TOTAL_HOURS
    )
    by_name = {e["name"]: e for e in ranking}
    assert "love her" in by_name["Alice"]["reasons"]
    assert "cute" in by_name["Alice"]["reasons"]
    assert by_name["Bob"]["reasons"] == []


def test_compute_ranking_gender_breakdown():
    ranking, _ = compute_ranking(
        CHAR_VOTES, CANDIDATES, GENDER_MAP, {}, VOTE_START, TOTAL_HOURS
    )
    by_name = {e["name"]: e for e in ranking}
    assert by_name["Alice"]["male_vote_count"]["vote_count"] == 1   # u1
    assert by_name["Alice"]["female_vote_count"]["vote_count"] == 1  # u2


def test_compute_ranking_display_rank_ties():
    # Alice and Bob tied on weighted score → both display_rank=1, next would be 3
    ranking, _ = compute_ranking(
        CHAR_VOTES, CANDIDATES, GENDER_MAP, {}, VOTE_START, TOTAL_HOURS
    )
    display_ranks = sorted(e["display_rank"] for e in ranking)
    assert display_ranks == [1, 1]


def test_compute_ranking_metadata_filled():
    ranking, _ = compute_ranking(
        CHAR_VOTES, CANDIDATES, GENDER_MAP, {}, VOTE_START, TOTAL_HOURS
    )
    alice = next(e for e in ranking if e["name"] == "Alice")
    assert alice["type"] == "旧作"
    assert alice["origin"] == "EoSD"
    assert alice["name_jp"] == "アリス"


def test_compute_ranking_unknown_candidate_fallback():
    votes = [("u1", _dt(1), [{"id": "Unknown", "first": False, "reason": None}])]
    ranking, _ = compute_ranking(votes, {}, {}, {}, VOTE_START, TOTAL_HOURS)
    assert ranking[0]["type"] == "未知"
    assert ranking[0]["origin"] == "未知"


def test_compute_ranking_historical():
    historical = {
        "Alice": {"rank_1": 3, "votes_1": 80, "first_1": 20, "rank_2": 5, "votes_2": 60, "first_2": 15}
    }
    ranking, _ = compute_ranking(
        CHAR_VOTES, CANDIDATES, GENDER_MAP, historical, VOTE_START, TOTAL_HOURS
    )
    alice = next(e for e in ranking if e["name"] == "Alice")
    assert len(alice["rank"]) == 3  # current + 2 historical snapshots
    assert alice["rank"][1]["rank"] == 3  # last year


# ── compute_global_stats ──────────────────────────────────────────────

def test_compute_global_stats():
    music_votes = [("u1", _dt(1), [{"id": "Song A", "first": True, "reason": None}])]
    cp_votes = []
    # questionnaire_votes are 2-tuples (user_id, list[dict]) — no datetime
    q_votes = [("u1", [{"id": "q11011", "answer": ["male"], "answer_str": None}])]
    gender_map = {"u1": "male"}
    stats = compute_global_stats(CHAR_VOTES, music_votes, cp_votes, q_votes, gender_map)
    assert stats["num_vote"] == 3   # 3 distinct users voted chars
    assert stats["num_char"] == 3
    assert stats["num_music"] == 1
    assert stats["num_male"] == 2   # u1, u3


# ── compute_completion_rates ──────────────────────────────────────────

def test_compute_completion_rates():
    all_voters = {"u1", "u2", "u3"}
    music_votes = [("u1", _dt(1), [])]
    cp_votes = []
    q_votes = []
    rates = compute_completion_rates(
        CHAR_VOTES, music_votes, cp_votes, q_votes, all_voters
    )
    assert rates["character"] == pytest.approx(1.0)   # 3/3
    assert rates["music"] == pytest.approx(1/3)        # 1/3
    assert rates["cp"] == pytest.approx(0.0)


# ── compute_covote ────────────────────────────────────────────────────

def test_compute_covote():
    votes = [
        ("u1", _dt(1), [{"id": "Alice", "first": False, "reason": None},
                         {"id": "Bob",   "first": False, "reason": None}]),
        ("u2", _dt(2), [{"id": "Alice", "first": False, "reason": None}]),
        ("u3", _dt(3), [{"id": "Bob",   "first": False, "reason": None}]),
    ]
    items = compute_covote(votes, top_k=10)
    pair = next((i for i in items if set([i["a"], i["b"]]) == {"Alice", "Bob"}), None)
    assert pair is not None
    assert pair["m11"] == 1  # u1 voted both
    assert pair["m10"] == 1  # u2 voted only Alice
    assert pair["m01"] == 1  # u3 voted only Bob


# ── compute_cp_ranking ────────────────────────────────────────────────

def test_compute_cp_ranking():
    cp_votes = [
        ("u1", _dt(1), [{"id_a": "A", "id_b": "B", "id_c": None, "active": "A", "first": True, "reason": None}]),
        ("u2", _dt(2), [{"id_a": "A", "id_b": "B", "id_c": None, "active": "B", "first": False, "reason": None}]),
    ]
    ranking, global_stats = compute_cp_ranking(cp_votes, {}, {}, VOTE_START, TOTAL_HOURS)
    assert len(ranking) == 1
    assert ranking[0]["id_a"] == "A"
    assert ranking[0]["id_b"] == "B"
    assert ranking[0]["rank"][0]["vote_count"] == 2
    assert ranking[0]["rank"][0]["favorite_vote_count"] == 1
```

- [ ] **Step 2: Run to confirm all tests fail**

```bash
pytest tests/unit/test_compute.py -x -q 2>&1 | head -20
```

Expected: `ImportError` or `ModuleNotFoundError` for `src.apps.result.compute`

- [ ] **Step 3: Create `src/apps/result/compute.py` with all pure functions**

```python
"""Pure compute functions for result aggregation.

All functions here are side-effect-free: they take data as arguments and
return computed results. No database or Redis access.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import combinations
from typing import Any


@dataclass
class CandidateMeta:
    name: str
    name_jp: str
    origin: str
    type: str
    first_appearance: str | None
    album: str | None = None


# ── Gender ────────────────────────────────────────────────────────────

def compute_gender_map(
    questionnaire_votes: list[tuple[str, list[dict]]],
    gender_question_id: str,
    gender_male_value: str,
    gender_female_value: str,
) -> dict[str, str]:
    """Map user_id → 'male' | 'female' | 'unknown' from questionnaire data."""
    result: dict[str, str] = {}
    for user_id, q_list in questionnaire_votes:
        gender = "unknown"
        for item in q_list:
            if item.get("id") == gender_question_id:
                ans = item.get("answer")
                val = (ans[0] if isinstance(ans, list) and ans else None) or item.get("answer_str") or ""
                if val == gender_male_value:
                    gender = "male"
                elif val == gender_female_value:
                    gender = "female"
                break
        result[user_id] = gender
    return result


# ── Character / Music Ranking ─────────────────────────────────────────

def compute_ranking(
    votes: list[tuple[str, datetime, list[dict]]],
    candidates: dict[str, CandidateMeta],
    gender_map: dict[str, str],
    historical: dict[str, dict],
    vote_start: datetime,
    total_hours: int,
) -> tuple[list[dict], dict]:
    """Compute character or music ranking.

    votes: list of (user_id, submit_datetime, items)
           each item: {"id": str, "first": bool, "reason": str|None}
    historical: name → {"rank_1", "votes_1", "first_1", "rank_2", "votes_2", "first_2"}
    Returns (ranking_list, global_stats_dict)
    """
    vote_count: dict[str, int] = defaultdict(int)
    first_count: dict[str, int] = defaultdict(int)
    reasons: dict[str, list[str]] = defaultdict(list)
    male_count: dict[str, int] = defaultdict(int)
    female_count: dict[str, int] = defaultdict(int)
    trend: dict[str, list[int]] = defaultdict(lambda: [0] * max(total_hours, 1))
    trend_first: dict[str, list[int]] = defaultdict(lambda: [0] * max(total_hours, 1))
    total_voters = len(votes)

    for user_id, submit_dt, items in votes:
        gender = gender_map.get(user_id, "unknown")
        # ensure submit_dt is timezone-aware for subtraction
        if submit_dt.tzinfo is None:
            submit_dt = submit_dt.replace(tzinfo=timezone.utc)
        hour_bucket = max(0, min(
            int((submit_dt - vote_start).total_seconds() / 3600),
            total_hours - 1,
        ))
        for item in items:
            name = item.get("id", "")
            if not name:
                continue
            is_first = bool(item.get("first", False))
            reason = item.get("reason")
            vote_count[name] += 1
            if is_first:
                first_count[name] += 1
            if reason:
                reasons[name].append(reason)
            if gender == "male":
                male_count[name] += 1
            elif gender == "female":
                female_count[name] += 1
            trend[name][hour_bucket] += 1
            if is_first:
                trend_first[name][hour_bucket] += 1

    all_names = set(vote_count.keys())
    total_votes = sum(vote_count.values())

    def weighted(name: str) -> int:
        return first_count[name] * 3 + vote_count[name]

    sorted_names = sorted(all_names, key=lambda n: (-weighted(n), -vote_count[n]))

    ranking = []
    prev_weighted = None
    prev_display_rank = 0
    skipped = 0
    for i, name in enumerate(sorted_names):
        w = weighted(name)
        if w != prev_weighted:
            prev_display_rank = i + 1 + skipped
            skipped = 0
        else:
            skipped += 1

        vc = vote_count[name]
        fc = first_count[name]
        vp = vc / total_voters if total_voters else 0.0
        fp = fc / vc if vc else 0.0

        rank_snapshots = [
            {
                "rank": i + 1,
                "vote_count": vc,
                "favorite_vote_count": fc,
                "favorite_percentage": int(fp * 100),
                "vote_percentage": round(vp * 100, 2),
            }
        ]
        hist = historical.get(name, {})
        if hist.get("rank_1"):
            h1_vc = hist["votes_1"]
            h1_fc = hist["first_1"]
            rank_snapshots.append({
                "rank": hist["rank_1"],
                "vote_count": h1_vc,
                "favorite_vote_count": h1_fc,
                "favorite_percentage": int(h1_fc / h1_vc * 100) if h1_vc else 0,
                "vote_percentage": 0.0,
            })
        if hist.get("rank_2"):
            h2_vc = hist["votes_2"]
            h2_fc = hist["first_2"]
            rank_snapshots.append({
                "rank": hist["rank_2"],
                "vote_count": h2_vc,
                "favorite_vote_count": h2_fc,
                "favorite_percentage": int(h2_fc / h2_vc * 100) if h2_vc else 0,
                "vote_percentage": 0.0,
            })

        mc = male_count[name]
        fc_gender = female_count[name]
        meta = candidates.get(name, CandidateMeta(name, "", "未知", "未知", None))

        ranking.append({
            "rank": rank_snapshots,
            "display_rank": prev_display_rank,
            "name": name,
            "favorite_vote_count_weighted": weighted(name),
            "type": meta.type or "未知",
            "origin": meta.origin or "未知",
            "first_appearance": meta.first_appearance or "",
            "album": meta.album or "",
            "name_jp": meta.name_jp or "",
            "favorite_percentage": round(fp * 100, 2),
            "male_vote_count": {
                "vote_count": mc,
                "percentage_per_char": round(mc / vc, 4) if vc else 0.0,
                "percentage_per_total": round(mc / total_voters, 4) if total_voters else 0.0,
            },
            "female_vote_count": {
                "vote_count": fc_gender,
                "percentage_per_char": round(fc_gender / vc, 4) if vc else 0.0,
                "percentage_per_total": round(fc_gender / total_voters, 4) if total_voters else 0.0,
            },
            "reasons": reasons[name],
            "reasons_count": len(reasons[name]),
            "trend": [{"hrs": h, "cnt": c} for h, c in enumerate(trend[name]) if c > 0],
            "trend_first": [{"hrs": h, "cnt": c} for h, c in enumerate(trend_first[name]) if c > 0],
        })
        prev_weighted = w

    global_stats = {
        "total_unique_items": len(all_names),
        "total_first": sum(first_count.values()),
        "total_votes": total_votes,
        "average_votes_per_item": total_votes / len(all_names) if all_names else 0.0,
        "median_votes_per_item": _median(list(vote_count.values())),
    }
    return ranking, global_stats


def _median(values: list[int]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return (s[mid] + s[~mid]) / 2.0


# ── CP Ranking ────────────────────────────────────────────────────────

def compute_cp_ranking(
    cp_votes: list[tuple[str, datetime, list[dict]]],
    gender_map: dict[str, str],
    historical: dict[str, dict],
    vote_start: datetime,
    total_hours: int,
) -> tuple[list[dict], dict]:
    """Compute CP ranking.

    Each item: {"id_a", "id_b", "id_c", "active", "first", "reason"}
    CP key: "A×B" or "A×B×C"
    """
    vote_count: dict[str, int] = defaultdict(int)
    first_count: dict[str, int] = defaultdict(int)
    reasons: dict[str, list[str]] = defaultdict(list)
    active_count: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    cp_meta: dict[str, dict] = {}
    trend: dict[str, list[int]] = defaultdict(lambda: [0] * max(total_hours, 1))
    trend_first: dict[str, list[int]] = defaultdict(lambda: [0] * max(total_hours, 1))
    total_voters = len(cp_votes)

    for user_id, submit_dt, items in cp_votes:
        if submit_dt.tzinfo is None:
            submit_dt = submit_dt.replace(tzinfo=timezone.utc)
        hour_bucket = max(0, min(
            int((submit_dt - vote_start).total_seconds() / 3600),
            total_hours - 1,
        ))
        for item in items:
            a = item.get("id_a", "")
            b = item.get("id_b", "")
            c = item.get("id_c")
            key = f"{a}×{b}×{c}" if c else f"{a}×{b}"
            active = item.get("active") or "none"
            is_first = bool(item.get("first", False))
            reason = item.get("reason")

            vote_count[key] += 1
            if is_first:
                first_count[key] += 1
            if reason:
                reasons[key].append(reason)
            active_count[key][active] += 1
            trend[key][hour_bucket] += 1
            if is_first:
                trend_first[key][hour_bucket] += 1
            if key not in cp_meta:
                cp_meta[key] = {"id_a": a, "id_b": b, "id_c": c}

    all_keys = set(vote_count.keys())
    total_votes = sum(vote_count.values())

    def weighted(k: str) -> int:
        return first_count[k] * 3 + vote_count[k]

    sorted_keys = sorted(all_keys, key=lambda k: (-weighted(k), -vote_count[k]))

    ranking = []
    prev_w = None
    prev_dr = 0
    skipped = 0
    for i, key in enumerate(sorted_keys):
        w = weighted(key)
        if w != prev_w:
            prev_dr = i + 1 + skipped
            skipped = 0
        else:
            skipped += 1

        vc = vote_count[key]
        fc = first_count[key]
        ac = active_count[key]
        meta = cp_meta[key]

        def _rate(who: str) -> float:
            return round(ac.get(who, 0) / vc, 4) if vc else 0.0

        ranking.append({
            "rank": [{"rank": i + 1, "vote_count": vc, "favorite_vote_count": fc,
                       "favorite_percentage": int(fc / vc * 100) if vc else 0,
                       "vote_percentage": round(vc / total_voters * 100, 2) if total_voters else 0.0}],
            "display_rank": prev_dr,
            "name": key,
            "id_a": meta["id_a"],
            "id_b": meta["id_b"],
            "id_c": meta["id_c"],
            "favorite_vote_count_weighted": w,
            "favorite_percentage": round(fc / vc * 100, 2) if vc else 0.0,
            "active_a": _rate(meta["id_a"]),
            "active_b": _rate(meta["id_b"]),
            "active_c": _rate(meta["id_c"]) if meta["id_c"] else 0.0,
            "active_none": _rate("none"),
            "reasons": reasons[key],
            "reasons_count": len(reasons[key]),
            "trend": [{"hrs": h, "cnt": c} for h, c in enumerate(trend[key]) if c > 0],
            "trend_first": [{"hrs": h, "cnt": c} for h, c in enumerate(trend_first[key]) if c > 0],
        })
        prev_w = w

    global_stats = {
        "total_unique_items": len(all_keys),
        "total_first": sum(first_count.values()),
        "total_votes": total_votes,
        "average_votes_per_item": total_votes / len(all_keys) if all_keys else 0.0,
        "median_votes_per_item": _median(list(vote_count.values())),
    }
    return ranking, global_stats


# ── Global Stats ──────────────────────────────────────────────────────

def compute_global_stats(
    char_votes: list[tuple[str, datetime, list[dict]]],
    music_votes: list[tuple[str, datetime, list[dict]]],
    cp_votes: list[tuple[str, datetime, list[dict]]],
    questionnaire_votes: list[tuple[str, list[dict]]],
    gender_map: dict[str, str],
) -> dict[str, Any]:
    char_users = {uid for uid, _, _ in char_votes}
    music_users = {uid for uid, _, _ in music_votes}
    cp_users = {uid for uid, _, _ in cp_votes}
    q_users = {uid for uid, _ in questionnaire_votes}
    all_users = char_users | music_users | cp_users | q_users
    male = sum(1 for uid in all_users if gender_map.get(uid) == "male")
    female = sum(1 for uid in all_users if gender_map.get(uid) == "female")
    finished = char_users & music_users
    return {
        "num_vote": len(all_users),
        "num_char": len(char_users),
        "num_music": len(music_users),
        "num_cp": len(cp_users),
        "num_doujin": 0,
        "num_male": male,
        "num_female": female,
        "num_finished_voting": len(finished),
        "num_finished_paper": len(q_users),
    }


# ── Completion Rates ──────────────────────────────────────────────────

def compute_completion_rates(
    char_votes: list[tuple[str, datetime, list[dict]]],
    music_votes: list[tuple[str, datetime, list[dict]]],
    cp_votes: list[tuple[str, datetime, list[dict]]],
    questionnaire_votes: list[tuple[str, list[dict]]],
    all_voters: set[str],
) -> dict[str, float]:
    total = len(all_voters)
    if total == 0:
        return {"character": 0.0, "music": 0.0, "cp": 0.0, "questionnaire": 0.0}
    return {
        "character": len({uid for uid, _, _ in char_votes} & all_voters) / total,
        "music": len({uid for uid, _, _ in music_votes} & all_voters) / total,
        "cp": len({uid for uid, _, _ in cp_votes} & all_voters) / total,
        "questionnaire": len({uid for uid, _ in questionnaire_votes} & all_voters) / total,
    }


# ── Paper (Questionnaire) Results ─────────────────────────────────────

def compute_paper_results(
    questionnaire_votes: list[tuple[str, list[dict]]],
    vote_start: datetime,
    total_hours: int,
) -> dict[str, dict]:
    """Compute per-question statistics from questionnaire votes.

    Returns {question_id: {"answers_cat": [...], "answers_str": [...], "total": int}}
    """
    question_cat: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    question_str: dict[str, list[str]] = defaultdict(list)
    question_total: dict[str, int] = defaultdict(int)

    for user_id, q_list in questionnaire_votes:
        for item in q_list:
            qid = str(item.get("id", ""))
            if not qid:
                continue
            question_total[qid] += 1
            ans = item.get("answer")
            ans_str = item.get("answer_str")
            if isinstance(ans, list):
                for a in ans:
                    question_cat[qid][str(a)] += 1
            if ans_str and str(ans_str).strip() and str(ans_str).strip() != "无":
                question_str[qid].append(str(ans_str).strip())

    result: dict[str, dict] = {}
    for qid in question_total:
        result[qid] = {
            "question_id": qid,
            "answers_cat": [{"aid": k, "count": v} for k, v in question_cat[qid].items()],
            "answers_str": question_str[qid],
            "total": question_total[qid],
        }
    return result


# ── Covote ────────────────────────────────────────────────────────────

def compute_covote(
    votes: list[tuple[str, datetime, list[dict]]],
    top_k: int = 100,
) -> list[dict]:
    """Compute pairwise co-vote statistics for the top-k entities."""
    vote_count: dict[str, int] = defaultdict(int)
    user_voted: dict[str, set[str]] = {}

    for user_id, _, items in votes:
        names = {item.get("id", "") for item in items if item.get("id")}
        user_voted[user_id] = names
        for name in names:
            vote_count[name] += 1

    top_names = sorted(vote_count, key=lambda n: -vote_count[n])[:top_k]
    top_set = set(top_names)
    total = len(user_voted)

    result = []
    for a, b in combinations(top_names, 2):
        voters_a = {uid for uid, names in user_voted.items() if a in names and a in top_set}
        voters_b = {uid for uid, names in user_voted.items() if b in names and b in top_set}
        m11 = len(voters_a & voters_b)
        m10 = len(voters_a - voters_b)
        m01 = len(voters_b - voters_a)
        m00 = total - m11 - m10 - m01
        union = m11 + m10 + m01
        cv = m11 / union if union else 0.0
        result.append({"a": a, "b": b, "m00": m00, "m01": m01, "m10": m10, "m11": m11, "cv": round(cv, 4)})

    return sorted(result, key=lambda x: -x["cv"])
```

- [ ] **Step 4: Run unit tests to verify they pass**

```bash
pytest tests/unit/test_compute.py -v
```

Expected: all 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/apps/result/compute.py tests/unit/test_compute.py
git commit -m "feat(result): add pure compute functions with full unit test coverage"
```

---

## Task 6: ComputeDAO

**Files:**
- Create: `src/apps/result/compute_dao.py`

- [ ] **Step 1: Create `src/apps/result/compute_dao.py`**

```python
"""ComputeDAO — reads raw vote + candidate data from PostgreSQL for computation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.result.compute import CandidateMeta
from src.db_model.candidate import CandidateCharacter, CandidateMusic, FinalRanking
from src.db_model.character import Character
from src.db_model.cp import Cp
from src.db_model.music import Music
from src.db_model.questionnaire import Questionnaire


def _normalize_items(raw_list: list) -> list[dict]:
    """Backward-compat: old list[str] → list[dict]."""
    result = []
    for item in (raw_list or []):
        if isinstance(item, str):
            result.append({"id": item, "first": False, "reason": None})
        elif isinstance(item, dict):
            result.append(item)
    return result


class ComputeDAO:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def load_char_votes(self) -> list[tuple[str, datetime, list[dict]]]:
        rows = (await self.session.execute(select(Character))).scalars().all()
        return [(r.id, r.submit_datetime, _normalize_items(r.character_list)) for r in rows]

    async def load_music_votes(self) -> list[tuple[str, datetime, list[dict]]]:
        rows = (await self.session.execute(select(Music))).scalars().all()
        return [(r.id, r.submit_datetime, _normalize_items(r.music_list)) for r in rows]

    async def load_cp_votes(self) -> list[tuple[str, datetime, list[dict]]]:
        rows = (await self.session.execute(select(Cp))).scalars().all()
        return [(r.id, r.submit_datetime, _normalize_items(r.cp_list)) for r in rows]

    async def load_questionnaire_votes(self) -> list[tuple[str, list[dict]]]:
        rows = (await self.session.execute(select(Questionnaire))).scalars().all()
        return [(r.id, r.questionnaire_list or []) for r in rows]

    async def load_char_candidates(self, vote_year: int) -> dict[str, CandidateMeta]:
        rows = (await self.session.execute(
            select(CandidateCharacter).where(CandidateCharacter.vote_year == vote_year)
        )).scalars().all()
        return {r.name: CandidateMeta(
            name=r.name, name_jp=r.name_jp, origin=r.origin,
            type=r.type, first_appearance=r.first_appearance,
        ) for r in rows}

    async def load_music_candidates(self, vote_year: int) -> dict[str, CandidateMeta]:
        rows = (await self.session.execute(
            select(CandidateMusic).where(CandidateMusic.vote_year == vote_year)
        )).scalars().all()
        return {r.name: CandidateMeta(
            name=r.name, name_jp=r.name_jp, origin="",
            type=r.type, first_appearance=r.first_appearance, album=r.album,
        ) for r in rows}

    async def load_historical(self, vote_year: int, category: str) -> dict[str, dict]:
        """Load rank_last_1 and rank_last_2 from final_ranking for historical comparison."""
        hist: dict[str, dict] = {}
        for delta, suffix in [(1, "1"), (2, "2")]:
            rows = (await self.session.execute(
                select(FinalRanking).where(
                    FinalRanking.vote_year == vote_year - delta,
                    FinalRanking.category == category,
                )
            )).scalars().all()
            for r in rows:
                entry = hist.setdefault(r.name, {})
                entry[f"rank_{suffix}"] = r.rank
                entry[f"votes_{suffix}"] = r.vote_count
                entry[f"first_{suffix}"] = r.first_vote_count
        return hist

    async def upsert_candidates(self, vote_year: int, category: str, items: list[dict]) -> int:
        """Bulk upsert candidate rows. Returns number of rows upserted."""
        Model = CandidateCharacter if category == "character" else CandidateMusic
        count = 0
        for item in items:
            existing = (await self.session.execute(
                select(Model).where(Model.vote_year == vote_year, Model.name == item["name"])
            )).scalar_one_or_none()
            if existing:
                for k, v in item.items():
                    if k != "name" and hasattr(existing, k):
                        setattr(existing, k, v)
            else:
                row = Model(vote_year=vote_year, **item)
                self.session.add(row)
            count += 1
        await self.session.commit()
        return count

    async def save_final_ranking(self, vote_year: int, category: str, entries: list[dict]) -> int:
        """Archive final ranking for historical comparison."""
        count = 0
        for entry in entries:
            rank = entry.get("display_rank") or entry.get("rank", [{}])[0].get("rank", 0)
            vc = entry.get("rank", [{}])[0].get("vote_count", 0)
            fc = entry.get("rank", [{}])[0].get("favorite_vote_count", 0)
            existing = (await self.session.execute(
                select(FinalRanking).where(
                    FinalRanking.vote_year == vote_year,
                    FinalRanking.category == category,
                    FinalRanking.rank == rank,
                )
            )).scalar_one_or_none()
            if existing:
                existing.name = entry["name"]
                existing.vote_count = vc
                existing.first_vote_count = fc
            else:
                self.session.add(FinalRanking(
                    vote_year=vote_year, category=category, rank=rank,
                    name=entry["name"], vote_count=vc, first_vote_count=fc,
                ))
            count += 1
        await self.session.commit()
        return count
```

- [ ] **Step 2: Verify import**

```bash
python -c "from src.apps.result.compute_dao import ComputeDAO; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/apps/result/compute_dao.py
git commit -m "feat(result): add ComputeDAO for reading PG vote + candidate data"
```

---

## Task 7: ComputeService

**Files:**
- Create: `src/apps/result/compute_service.py`

- [ ] **Step 1: Create `src/apps/result/compute_service.py`**

```python
"""ComputeService — orchestrates compute pipeline and writes to Redis."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import redis.asyncio as aioredis

from src.apps.result.compute import (
    compute_completion_rates,
    compute_covote,
    compute_cp_ranking,
    compute_gender_map,
    compute_global_stats,
    compute_paper_results,
    compute_ranking,
)
from src.apps.result.compute_dao import ComputeDAO
from src.common.config import Settings

logger = logging.getLogger(__name__)

LOCK_TTL_MS = 300_000  # 5 minutes


class ComputeService:
    def __init__(self, compute_dao: ComputeDAO, redis: aioredis.Redis, settings: Settings):
        self.dao = compute_dao
        self.redis = redis
        self.settings = settings

    def _key(self, vote_year: int, *parts: str) -> str:
        return f"result:{vote_year}:" + ":".join(parts)

    def _lock_key(self, vote_year: int) -> str:
        return f"compute_lock:{vote_year}"

    async def compute_all(self, vote_year: int) -> dict:
        """Run full computation pipeline for the given vote_year. Writes results to Redis."""
        lock_key = self._lock_key(vote_year)
        acquired = await self.redis.set(lock_key, "1", nx=True, px=LOCK_TTL_MS)
        if not acquired:
            raise ComputeInProgressError()

        t0 = time.monotonic()
        try:
            s = self.settings
            vote_start_str = s.vote_start_iso.replace("Z", "+00:00")
            vote_end_str = s.vote_end_iso.replace("Z", "+00:00")
            vote_start = datetime.fromisoformat(vote_start_str)
            vote_end = datetime.fromisoformat(vote_end_str)
            total_hours = max(1, int((vote_end - vote_start).total_seconds() / 3600))

            # Load all data
            char_votes = await self.dao.load_char_votes()
            music_votes = await self.dao.load_music_votes()
            cp_votes = await self.dao.load_cp_votes()
            q_votes = await self.dao.load_questionnaire_votes()

            char_candidates = await self.dao.load_char_candidates(vote_year)
            music_candidates = await self.dao.load_music_candidates(vote_year)

            char_hist = await self.dao.load_historical(vote_year, "character")
            music_hist = await self.dao.load_historical(vote_year, "music")
            cp_hist = await self.dao.load_historical(vote_year, "cp")

            # Compute
            gender_map = compute_gender_map(
                q_votes, s.gender_question_id, s.gender_male_value, s.gender_female_value
            )
            char_ranking, char_global = compute_ranking(
                char_votes, char_candidates, gender_map, char_hist, vote_start, total_hours
            )
            music_ranking, music_global = compute_ranking(
                music_votes, music_candidates, gender_map, music_hist, vote_start, total_hours
            )
            cp_ranking, cp_global = compute_cp_ranking(
                cp_votes, gender_map, cp_hist, vote_start, total_hours
            )

            all_voters = (
                {uid for uid, _, _ in char_votes}
                | {uid for uid, _, _ in music_votes}
                | {uid for uid, _, _ in cp_votes}
                | {uid for uid, _ in q_votes}
            )
            global_stats = compute_global_stats(char_votes, music_votes, cp_votes, q_votes, gender_map)
            completion_rates = compute_completion_rates(
                char_votes, music_votes, cp_votes, q_votes, all_voters
            )
            paper_results = compute_paper_results(q_votes, vote_start, total_hours)
            char_covote = compute_covote(char_votes, top_k=100)
            music_covote = compute_covote(music_votes, top_k=100)

            # Bulk write to Redis
            pipe = self.redis.pipeline()
            pipe.set(self._key(vote_year, "chars", "ranking"), json.dumps(char_ranking))
            pipe.set(self._key(vote_year, "chars", "global"), json.dumps(char_global))
            pipe.set(self._key(vote_year, "musics", "ranking"), json.dumps(music_ranking))
            pipe.set(self._key(vote_year, "musics", "global"), json.dumps(music_global))
            pipe.set(self._key(vote_year, "cps", "ranking"), json.dumps(cp_ranking))
            pipe.set(self._key(vote_year, "cps", "global"), json.dumps(cp_global))
            pipe.set(self._key(vote_year, "global_stats"), json.dumps(global_stats))
            pipe.set(self._key(vote_year, "completion_rates"), json.dumps(completion_rates))
            pipe.set(self._key(vote_year, "covote", "chars"), json.dumps(char_covote))
            pipe.set(self._key(vote_year, "covote", "musics"), json.dumps(music_covote))
            for qid, data in paper_results.items():
                pipe.set(self._key(vote_year, "paper", qid), json.dumps(data))
            await pipe.execute()

            duration = round(time.monotonic() - t0, 2)
            logger.info("Compute complete for vote_year=%d in %.2fs", vote_year, duration)
            return {
                "ok": True,
                "vote_year": vote_year,
                "duration_seconds": duration,
                "counts": {
                    "chars": len(char_ranking),
                    "musics": len(music_ranking),
                    "cps": len(cp_ranking),
                    "questions": len(paper_results),
                },
            }
        finally:
            await self.redis.delete(lock_key)


class ComputeInProgressError(Exception):
    pass
```

- [ ] **Step 2: Verify import**

```bash
python -c "from src.apps.result.compute_service import ComputeService; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/apps/result/compute_service.py
git commit -m "feat(result): add ComputeService orchestrator — reads PG, computes, writes Redis"
```

---

## Task 8: ResultDAO Rewrite

**Files:**
- Modify: `src/apps/result/dao.py`

- [ ] **Step 1: Replace `src/apps/result/dao.py` completely**

```python
"""ResultDAO — reads pre-computed result data from Redis."""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

from src.common.config import Settings


class ResultNotComputedError(Exception):
    """Raised when Redis cache is empty — admin must run /admin/compute-results first."""


class EntityNotFoundError(Exception):
    """Raised when a specific entity is not found in computed results."""


class ResultDAO:
    def __init__(self, redis: aioredis.Redis, settings: Settings):
        self.redis = redis
        self.settings = settings

    def _year(self, vote_year: int | None) -> int:
        return vote_year if vote_year is not None else self.settings.vote_year

    def _key(self, vote_year: int, *parts: str) -> str:
        return f"result:{vote_year}:" + ":".join(parts)

    async def _get_json(self, key: str) -> Any:
        raw = await self.redis.get(key)
        if raw is None:
            raise ResultNotComputedError(f"No computed data at Redis key: {key}")
        return json.loads(raw)

    async def get_ranking(self, category: str, names: list[str], vote_year: int | None = None) -> tuple[list[dict], dict]:
        """Returns (ranking_list, global_stats_dict). Filters by names if provided."""
        year = self._year(vote_year)
        cat = _category_key(category)
        ranking = await self._get_json(self._key(year, cat, "ranking"))
        global_stats = await self._get_json(self._key(year, cat, "global"))
        if names:
            ranking = [e for e in ranking if e.get("name") in names]
        return ranking, global_stats

    async def get_reasons(self, category: str, name: str, vote_year: int | None = None) -> list[str]:
        year = self._year(vote_year)
        cat = _category_key(category)
        ranking = await self._get_json(self._key(year, cat, "ranking"))
        for entry in ranking:
            if entry.get("name") == name:
                return entry.get("reasons", [])
        raise EntityNotFoundError(name)

    async def get_trend(self, category: str, name: str, vote_year: int | None = None) -> dict:
        year = self._year(vote_year)
        cat = _category_key(category)
        ranking = await self._get_json(self._key(year, cat, "ranking"))
        for entry in ranking:
            if entry.get("name") == name:
                return {"trend": entry.get("trend", []), "trend_first": entry.get("trend_first", [])}
        raise EntityNotFoundError(name)

    async def get_global_stats(self, vote_year: int | None = None) -> dict:
        return await self._get_json(self._key(self._year(vote_year), "global_stats"))

    async def get_single_entity(self, category: str, name: str, vote_year: int | None = None) -> dict:
        year = self._year(vote_year)
        cat = _category_key(category)
        ranking = await self._get_json(self._key(year, cat, "ranking"))
        for entry in ranking:
            if entry.get("name") == name:
                return entry
        raise EntityNotFoundError(name)

    async def get_completion_rates(self, vote_year: int | None = None) -> dict:
        return await self._get_json(self._key(self._year(vote_year), "completion_rates"))

    async def get_questionnaire(self, question_id: str, vote_year: int | None = None) -> dict:
        return await self._get_json(self._key(self._year(vote_year), "paper", question_id))

    async def get_covote(self, category: str, vote_year: int | None = None) -> list[dict]:
        cat = "chars" if category == "character" else "musics"
        return await self._get_json(self._key(self._year(vote_year), "covote", cat))


def _category_key(category: str) -> str:
    mapping = {"character": "chars", "music": "musics", "cp": "cps"}
    return mapping.get(category, category)
```

- [ ] **Step 2: Verify import**

```bash
python -c "from src.apps.result.dao import ResultDAO, ResultNotComputedError; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/apps/result/dao.py
git commit -m "feat(result): rewrite ResultDAO as Redis reader; remove all NotImplementedError"
```

---

## Task 9: Result Schemas + Router Update

**Files:**
- Modify: `src/apps/result/schemas.py`
- Modify: `src/apps/result/router.py`
- Modify: `src/apps/result/service.py`

- [ ] **Step 1: Update query types in `src/apps/result/schemas.py`**

Add `vote_year: int | None = None` and `category` fields to all query types. Replace the existing `RankingQuery`, `TrendQuery`, `ReasonQuery`, `SingleQuery`, `CovoteQuery`, `GlobalStatsQuery`, `CompletionRatesQuery`, `QuestionnaireQuery`, `QuestionnaireTrendQuery` with:

```python
from typing import Literal, Optional
from pydantic import BaseModel
from datetime import datetime


class RankingQuery(BaseModel):
    vote_year: int | None = None
    category: Literal["character", "music", "cp"] = "character"
    names: list[str] = []


class TrendQuery(BaseModel):
    vote_year: int | None = None
    category: Literal["character", "music", "cp"] = "character"
    name: str


class ReasonQuery(BaseModel):
    vote_year: int | None = None
    category: Literal["character", "music", "cp"] = "character"
    name: str


class SingleQuery(BaseModel):
    vote_year: int | None = None
    category: Literal["character", "music", "cp"] = "character"
    name: str


class CovoteQuery(BaseModel):
    vote_year: int | None = None
    category: Literal["character", "music"] = "character"


class GlobalStatsQuery(BaseModel):
    vote_year: int | None = None


class CompletionRatesQuery(BaseModel):
    vote_year: int | None = None


class QuestionnaireQuery(BaseModel):
    vote_year: int | None = None
    question_id: str


class QuestionnaireTrendQuery(BaseModel):
    vote_year: int | None = None
    question_id: str
```

Keep the existing response model classes (`RankingEntity`, `RankingCharacterMusic`, `GlobalStats`, `Trends`, `Reasons`, `VoteCountData`, `RankingEntityData`, `TrendItem`) unchanged.

- [ ] **Step 2: Rewrite `src/apps/result/router.py`**

```python
"""Result query API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

import redis.asyncio as aioredis

from src.apps.result.dao import EntityNotFoundError, ResultDAO, ResultNotComputedError
from src.apps.result.schemas import (
    CompletionRatesQuery,
    CovoteQuery,
    GlobalStatsQuery,
    QuestionnaireQuery,
    QuestionnaireTrendQuery,
    RankingQuery,
    ReasonQuery,
    SingleQuery,
    TrendQuery,
)
from src.apps.result.service import ResultService
from src.common.config import Settings, get_settings
from src.common.redis import get_redis

router = APIRouter(prefix="/result", tags=["result"])


async def get_result_service(
    redis: aioredis.Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> ResultService:
    dao = ResultDAO(redis, settings)
    return ResultService(dao)


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, ResultNotComputedError):
        raise HTTPException(status_code=503, detail="RESULT_NOT_COMPUTED")
    if isinstance(exc, EntityNotFoundError):
        raise HTTPException(status_code=404, detail="ENTITY_NOT_FOUND")
    raise exc


@router.post("/ranking/", response_model=dict)
async def get_ranking(
    query: RankingQuery,
    service: ResultService = Depends(get_result_service),
) -> dict:
    try:
        return await service.get_ranking(query)
    except (ResultNotComputedError, EntityNotFoundError) as e:
        _raise_http(e)


@router.post("/trends/", response_model=dict)
async def get_trends(
    query: TrendQuery,
    service: ResultService = Depends(get_result_service),
) -> dict:
    try:
        return await service.get_trends(query)
    except (ResultNotComputedError, EntityNotFoundError) as e:
        _raise_http(e)


@router.post("/global-stats/", response_model=dict)
async def get_global_stats(
    query: GlobalStatsQuery,
    service: ResultService = Depends(get_result_service),
) -> dict:
    try:
        return await service.get_global_stats(query)
    except ResultNotComputedError as e:
        _raise_http(e)


@router.post("/single/", response_model=dict)
async def get_single_entity(
    query: SingleQuery,
    service: ResultService = Depends(get_result_service),
) -> dict:
    try:
        return await service.get_single_entity(query)
    except (ResultNotComputedError, EntityNotFoundError) as e:
        _raise_http(e)


@router.post("/reasons/", response_model=dict)
async def get_reasons(
    query: ReasonQuery,
    service: ResultService = Depends(get_result_service),
) -> dict:
    try:
        return await service.get_reasons(query)
    except (ResultNotComputedError, EntityNotFoundError) as e:
        _raise_http(e)


@router.post("/covote/", response_model=dict)
async def get_covote(
    query: CovoteQuery,
    service: ResultService = Depends(get_result_service),
) -> dict:
    try:
        return await service.get_covote(query)
    except ResultNotComputedError as e:
        _raise_http(e)


@router.post("/completion-rates/", response_model=dict)
async def get_completion_rates(
    query: CompletionRatesQuery,
    service: ResultService = Depends(get_result_service),
) -> dict:
    try:
        return await service.get_completion_rates(query)
    except ResultNotComputedError as e:
        _raise_http(e)


@router.post("/questionnaire/", response_model=dict)
async def get_questionnaire(
    query: QuestionnaireQuery,
    service: ResultService = Depends(get_result_service),
) -> dict:
    try:
        return await service.get_questionnaire(query)
    except ResultNotComputedError as e:
        _raise_http(e)


@router.post("/questionnaire-trend/", response_model=dict)
async def get_questionnaire_trend(
    query: QuestionnaireTrendQuery,
    service: ResultService = Depends(get_result_service),
) -> dict:
    try:
        return await service.get_questionnaire_trend(query)
    except ResultNotComputedError as e:
        _raise_http(e)
```

- [ ] **Step 3: Update `src/apps/result/service.py`**

Replace the file to align method signatures with the new DAO:

```python
"""Result service layer."""

from src.apps.result.dao import ResultDAO
from src.apps.result.schemas import (
    CompletionRatesQuery, CovoteQuery, GlobalStatsQuery,
    QuestionnaireQuery, QuestionnaireTrendQuery,
    RankingQuery, ReasonQuery, SingleQuery, TrendQuery,
)


class ResultService:
    def __init__(self, result_dao: ResultDAO):
        self.result_dao = result_dao

    async def get_ranking(self, query: RankingQuery) -> dict:
        ranking, global_stats = await self.result_dao.get_ranking(
            query.category, query.names, query.vote_year
        )
        return {"rankings": ranking, "global": global_stats}

    async def get_trends(self, query: TrendQuery) -> dict:
        return await self.result_dao.get_trend(query.category, query.name, query.vote_year)

    async def get_global_stats(self, query: GlobalStatsQuery) -> dict:
        return await self.result_dao.get_global_stats(query.vote_year)

    async def get_single_entity(self, query: SingleQuery) -> dict:
        return await self.result_dao.get_single_entity(query.category, query.name, query.vote_year)

    async def get_reasons(self, query: ReasonQuery) -> dict:
        reasons = await self.result_dao.get_reasons(query.category, query.name, query.vote_year)
        return {"reasons": reasons}

    async def get_covote(self, query: CovoteQuery) -> dict:
        items = await self.result_dao.get_covote(query.category, query.vote_year)
        return {"items": items}

    async def get_completion_rates(self, query: CompletionRatesQuery) -> dict:
        return await self.result_dao.get_completion_rates(query.vote_year)

    async def get_questionnaire(self, query: QuestionnaireQuery) -> dict:
        return await self.result_dao.get_questionnaire(query.question_id, query.vote_year)

    async def get_questionnaire_trend(self, query: QuestionnaireTrendQuery) -> dict:
        return await self.result_dao.get_questionnaire(query.question_id, query.vote_year)
```

- [ ] **Step 4: Run full test suite**

```bash
pytest tests/ -x -q
```

Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add src/apps/result/schemas.py src/apps/result/router.py src/apps/result/service.py
git commit -m "feat(result): update schemas/router/service — Redis DI, vote_year param, 503 on cache miss"
```

---

## Task 10: Admin Module

**Files:**
- Create: `src/apps/admin/__init__.py`
- Create: `src/apps/admin/schemas.py`
- Create: `src/apps/admin/service.py`
- Create: `src/apps/admin/router.py`

- [ ] **Step 1: Create `src/apps/admin/__init__.py`**

```python
```
(empty file)

- [ ] **Step 2: Create `src/apps/admin/schemas.py`**

```python
"""Admin endpoint schemas."""

from typing import Literal
from pydantic import BaseModel


class CandidateItem(BaseModel):
    name: str
    name_jp: str = ""
    origin: str = ""
    type: str = ""
    first_appearance: str | None = None
    album: str | None = None


class ImportCandidatesRequest(BaseModel):
    vote_year: int
    category: Literal["character", "music"]
    items: list[CandidateItem]


class ImportCandidatesResponse(BaseModel):
    ok: bool = True
    imported: int


class ComputeResultsResponse(BaseModel):
    ok: bool
    vote_year: int
    duration_seconds: float
    counts: dict


class FinalizeRankingResponse(BaseModel):
    ok: bool = True
    vote_year: int
    saved: int
```

- [ ] **Step 3: Create `src/apps/admin/service.py`**

```python
"""Admin service — wraps ComputeService and ComputeDAO."""

from src.apps.result.compute_dao import ComputeDAO
from src.apps.result.compute_service import ComputeInProgressError, ComputeService
from src.apps.admin.schemas import ImportCandidatesRequest


class AdminService:
    def __init__(self, compute_service: ComputeService, compute_dao: ComputeDAO):
        self.compute_service = compute_service
        self.compute_dao = compute_dao

    async def compute_results(self, vote_year: int) -> dict:
        return await self.compute_service.compute_all(vote_year)

    async def import_candidates(self, request: ImportCandidatesRequest) -> int:
        items = [item.model_dump(exclude_none=False) for item in request.items]
        return await self.compute_dao.upsert_candidates(
            request.vote_year, request.category, items
        )

    async def finalize_ranking(self, vote_year: int) -> int:
        """Read computed Redis ranking and archive to final_ranking PG table."""
        import json
        import redis.asyncio as aioredis
        # ranking data is already in Redis — we read it via compute_service's redis
        redis = self.compute_service.redis
        total = 0
        for category in ("character", "music", "cp"):
            cat_key = {"character": "chars", "music": "musics", "cp": "cps"}[category]
            key = f"result:{vote_year}:{cat_key}:ranking"
            raw = await redis.get(key)
            if raw:
                entries = json.loads(raw)
                saved = await self.compute_dao.save_final_ranking(vote_year, category, entries)
                total += saved
        return total
```

- [ ] **Step 4: Create `src/apps/admin/router.py`**

```python
"""Admin endpoints: compute-results, import-candidates, finalize-ranking."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.admin.schemas import (
    ComputeResultsResponse,
    FinalizeRankingResponse,
    ImportCandidatesRequest,
    ImportCandidatesResponse,
)
from src.apps.admin.service import AdminService
from src.apps.result.compute_dao import ComputeDAO
from src.apps.result.compute_service import ComputeInProgressError, ComputeService
from src.common.config import Settings, get_settings
from src.common.database import get_db_session
from src.common.redis import get_redis

router = APIRouter(prefix="/admin", tags=["admin"])


def _check_admin_secret(settings: Settings, secret: str | None) -> None:
    if settings.admin_secret and secret != settings.admin_secret:
        raise HTTPException(status_code=403, detail="FORBIDDEN")


async def get_admin_service(
    session: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> AdminService:
    compute_dao = ComputeDAO(session)
    compute_svc = ComputeService(compute_dao, redis, settings)
    return AdminService(compute_svc, compute_dao)


@router.post("/compute-results", response_model=ComputeResultsResponse)
async def compute_results(
    vote_year: int | None = None,
    x_admin_secret: str | None = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> ComputeResultsResponse:
    _check_admin_secret(settings, x_admin_secret)
    year = vote_year or settings.vote_year
    try:
        result = await service.compute_results(year)
        return ComputeResultsResponse(**result)
    except ComputeInProgressError:
        raise HTTPException(status_code=409, detail="COMPUTE_IN_PROGRESS")


@router.post("/import-candidates", response_model=ImportCandidatesResponse)
async def import_candidates(
    body: ImportCandidatesRequest,
    x_admin_secret: str | None = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> ImportCandidatesResponse:
    _check_admin_secret(settings, x_admin_secret)
    count = await service.import_candidates(body)
    return ImportCandidatesResponse(imported=count)


@router.post("/finalize-ranking", response_model=FinalizeRankingResponse)
async def finalize_ranking(
    vote_year: int | None = None,
    x_admin_secret: str | None = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> FinalizeRankingResponse:
    _check_admin_secret(settings, x_admin_secret)
    year = vote_year or settings.vote_year
    saved = await service.finalize_ranking(year)
    return FinalizeRankingResponse(vote_year=year, saved=saved)
```

- [ ] **Step 5: Commit**

```bash
git add src/apps/admin/
git commit -m "feat(admin): add compute-results, import-candidates, finalize-ranking endpoints"
```

---

## Task 11: Register Admin Router

**Files:**
- Modify: `src/api/rest/v1/__init__.py`

- [ ] **Step 1: Add admin_router import and include**

In `src/api/rest/v1/__init__.py`, add:

```python
from src.apps.admin.router import router as admin_router
```

And add to the router inclusions:

```python
api_router.include_router(admin_router)
```

- [ ] **Step 2: Run the full test suite**

```bash
pytest tests/ -x -q
```

Expected: all tests pass

- [ ] **Step 3: Commit**

```bash
git add src/api/rest/v1/__init__.py
git commit -m "feat(api): register admin router under /api/v1/admin"
```

---

## Task 12: Integration Tests

**Files:**
- Create: `tests/integration/test_result_compute.py`

- [ ] **Step 1: Create `tests/integration/test_result_compute.py`**

```python
"""Integration tests: full compute pipeline using SQLite + fakeredis."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pytest
import pytest_asyncio

try:
    import fakeredis.aioredis as fakeredis
except ImportError:
    import fakeredis

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.apps.result.compute_dao import ComputeDAO
from src.apps.result.compute_service import ComputeService
from src.apps.result.dao import ResultDAO, ResultNotComputedError
from src.common.config import Settings
from src.db_model.base import Base
from src.db_model.candidate import CandidateCharacter
from src.db_model.character import Character
from src.db_model.music import Music
from src.db_model.questionnaire import Questionnaire

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("JWT_SECRET_KEY", "test-key")
os.environ.setdefault("VOTE_START_ISO", "2026-01-01T00:00:00Z")
os.environ.setdefault("VOTE_END_ISO", "2026-12-31T23:59:59Z")


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncSession:
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s


@pytest_asyncio.fixture
def fake_redis():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest_asyncio.fixture
def settings():
    s = Settings()
    s.__dict__["vote_year"] = 2026
    s.__dict__["vote_start_iso"] = "2026-01-01T00:00:00Z"
    s.__dict__["vote_end_iso"] = "2026-12-31T23:59:59Z"
    s.__dict__["gender_question_id"] = "q11011"
    s.__dict__["gender_male_value"] = "male"
    s.__dict__["gender_female_value"] = "female"
    return s


async def _seed_data(session: AsyncSession) -> None:
    """Insert minimal test data."""
    session.add(CandidateCharacter(
        vote_year=2026, name="Alice", name_jp="アリス",
        origin="EoSD", type="旧作", first_appearance="2002",
    ))
    session.add(Character(
        id="user-1",
        submit_datetime=datetime(2026, 1, 2, tzinfo=timezone.utc),
        character_list=[{"id": "Alice", "first": True, "reason": "love her"}],
    ))
    session.add(Character(
        id="user-2",
        submit_datetime=datetime(2026, 1, 3, tzinfo=timezone.utc),
        character_list=[{"id": "Alice", "first": False, "reason": None}],
    ))
    session.add(Questionnaire(
        id="user-1",
        submit_datetime=datetime(2026, 1, 2, tzinfo=timezone.utc),
        questionnaire_list=[{"id": "q11011", "answer": ["male"], "answer_str": None}],
    ))
    await session.commit()


@pytest.mark.asyncio
async def test_compute_and_read_ranking(session, fake_redis, settings):
    await _seed_data(session)
    dao = ComputeDAO(session)
    svc = ComputeService(dao, fake_redis, settings)
    result = await svc.compute_all(2026)

    assert result["ok"] is True
    assert result["counts"]["chars"] == 1  # Alice only

    result_dao = ResultDAO(fake_redis, settings)
    ranking_data = await result_dao.get_ranking("character", [], 2026)
    ranking, global_stats = ranking_data
    assert len(ranking) == 1
    assert ranking[0]["name"] == "Alice"
    assert ranking[0]["rank"][0]["vote_count"] == 2
    assert ranking[0]["rank"][0]["favorite_vote_count"] == 1


@pytest.mark.asyncio
async def test_result_not_computed_error(fake_redis, settings):
    result_dao = ResultDAO(fake_redis, settings)
    with pytest.raises(ResultNotComputedError):
        await result_dao.get_ranking("character", [], 2026)


@pytest.mark.asyncio
async def test_compute_global_stats(session, fake_redis, settings):
    await _seed_data(session)
    dao = ComputeDAO(session)
    svc = ComputeService(dao, fake_redis, settings)
    await svc.compute_all(2026)

    result_dao = ResultDAO(fake_redis, settings)
    stats = await result_dao.get_global_stats(2026)
    assert stats["num_char"] == 2  # user-1 and user-2
    assert stats["num_male"] == 1  # only user-1 answered questionnaire as male
```

- [ ] **Step 2: Run integration tests**

```bash
pytest tests/integration/test_result_compute.py -v
```

Expected: 3 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_result_compute.py
git commit -m "test(result): add integration tests for compute pipeline + ResultDAO"
```

---

## Task 13: Contract Tests

**Files:**
- Create: `tests/contract/test_result_endpoints.py`

- [ ] **Step 1: Create `tests/contract/test_result_endpoints.py`**

```python
"""Contract tests: result endpoints return 503 before compute, 200 after."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.main import create_app


@pytest_asyncio.fixture
async def client():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


RESULT_ENDPOINTS = [
    ("POST", "/api/v1/result/ranking/",          {"category": "character"}),
    ("POST", "/api/v1/result/trends/",            {"category": "character", "name": "Alice"}),
    ("POST", "/api/v1/result/global-stats/",      {}),
    ("POST", "/api/v1/result/single/",            {"category": "character", "name": "Alice"}),
    ("POST", "/api/v1/result/reasons/",           {"category": "character", "name": "Alice"}),
    ("POST", "/api/v1/result/covote/",            {"category": "character"}),
    ("POST", "/api/v1/result/completion-rates/",  {}),
    ("POST", "/api/v1/result/questionnaire/",     {"question_id": "q11011"}),
    ("POST", "/api/v1/result/questionnaire-trend/", {"question_id": "q11011"}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,body", RESULT_ENDPOINTS)
async def test_result_endpoints_503_before_compute(client, method, path, body):
    resp = await client.request(method, path, json=body)
    assert resp.status_code == 503, f"{path} expected 503, got {resp.status_code}: {resp.text}"
    assert resp.json()["detail"] == "RESULT_NOT_COMPUTED"


@pytest.mark.asyncio
async def test_admin_compute_results_endpoint_reachable(client):
    resp = await client.post("/api/v1/admin/compute-results")
    # Returns 200 with empty data (no votes seeded), not 404
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True


@pytest.mark.asyncio
async def test_admin_import_candidates_endpoint_reachable(client):
    resp = await client.post("/api/v1/admin/import-candidates", json={
        "vote_year": 2026,
        "category": "character",
        "items": [{"name": "Alice", "name_jp": "アリス", "origin": "EoSD", "type": "旧作"}],
    })
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
```

- [ ] **Step 2: Run contract tests**

```bash
pytest tests/contract/test_result_endpoints.py -v
```

Expected: all tests PASS

- [ ] **Step 3: Run full test suite to confirm no regressions**

```bash
pytest tests/ -q
```

Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/contract/test_result_endpoints.py
git commit -m "test(result): add contract tests — 503 before compute, admin endpoints reachable"
```

---

## Post-Implementation Checklist

- [ ] `alembic upgrade head` runs cleanly on a fresh database
- [ ] `POST /api/v1/admin/import-candidates` accepts a candidate list
- [ ] `POST /api/v1/admin/compute-results` writes to Redis and returns duration
- [ ] `POST /api/v1/result/ranking/` returns 200 with rankings after compute
- [ ] `POST /api/v1/result/ranking/` returns 503 if compute not yet run
- [ ] `POST /api/v1/admin/finalize-ranking` writes to `final_ranking` PG table
- [ ] Update `REFACTOR_TODO.md`: mark result module ✅
- [ ] Update `docs/BACKLOG.md` with any new follow-up items discovered
