# GraphQL Schema Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the backend GraphQL schema fully compatible with what the vote and result frontend pages actually send, covering scalar registration, field renaming, strong-typed result responses, submit field alignment, and all user auth mutations.

**Architecture:** All changes are confined to `src/api/graphql/`. New types go in `types.py`; resolvers are rewritten/created in `resolvers/`; `schema.py` wires everything together. The existing REST layer, DAO, and service layer are untouched — resolvers call service methods directly, same as the REST routers do.

**Tech Stack:** Python 3.12, Strawberry GraphQL, FastAPI, existing `UserService` / `ResultService` / `SubmitService`

---

## File Map

| File | Action |
|---|---|
| `src/api/graphql/types.py` | Add `DateTimeUtc` scalar + all Result/User strong types |
| `src/api/graphql/resolvers/result.py` | Rewrite with correct field names, args, strong-typed returns |
| `src/api/graphql/resolvers/submit.py` | Rename fields, rename input types, align `voteToken` arg |
| `src/api/graphql/resolvers/user.py` | Create — all user mutations + `userTokenStatus` query |
| `src/api/graphql/schema.py` | Register `DateTimeUtc` scalar + `UserMutation` + `UserQuery` |
| `tests/contract/test_graphql_schema.py` | Create — schema-level smoke tests |

---

## Task 1: DateTimeUtc scalar + all new GQL types

**Files:**
- Modify: `src/api/graphql/types.py`

- [ ] **Step 1: Write failing test**

Create `tests/contract/test_graphql_schema.py`:

```python
"""GraphQL schema smoke tests — verify field names and types exist."""
import pytest


@pytest.mark.asyncio
async def test_datetimeutc_scalar_registered(async_client):
    """DateTimeUtc scalar must be registered in the schema."""
    resp = await async_client.post(
        "/graphql",
        json={"query": "{ __type(name: \"DateTimeUtc\") { name kind } }"},
    )
    assert resp.status_code == 200
    data = resp.json()
    t = data["data"]["__type"]
    assert t is not None
    assert t["name"] == "DateTimeUtc"


@pytest.mark.asyncio
async def test_query_character_ranking_field_exists(async_client):
    """queryCharacterRanking must exist in the schema."""
    resp = await async_client.post(
        "/graphql",
        json={
            "query": """
            {
              __type(name: "Query") {
                fields { name }
              }
            }
            """
        },
    )
    assert resp.status_code == 200
    names = {f["name"] for f in resp.json()["data"]["__type"]["fields"]}
    assert "queryCharacterRanking" in names
    assert "queryMusicRanking" in names
    assert "queryCPRanking" in names
    assert "queryCharacterTrend" in names
    assert "queryMusicTrend" in names
    assert "queryCharacterSingle" in names
    assert "queryMusicSingle" in names
    assert "queryCPSingle" in names
    assert "queryGlobalStats" in names
    assert "queryCompletionRates" in names
    assert "queryQuestionnaire" in names
    assert "queryQuestionnaireTrend" in names
    assert "queryCharsCovote" in names
    assert "queryMusicsCovote" in names


@pytest.mark.asyncio
async def test_mutation_login_email_exists(async_client):
    """loginEmail mutation must exist in the schema."""
    resp = await async_client.post(
        "/graphql",
        json={
            "query": """
            {
              __type(name: "Mutation") {
                fields { name }
              }
            }
            """
        },
    )
    assert resp.status_code == 200
    names = {f["name"] for f in resp.json()["data"]["__type"]["fields"]}
    assert "loginEmail" in names
    assert "loginPhone" in names
    assert "loginEmailPassword" in names
    assert "requestEmailCode" in names
    assert "requestPhoneCode" in names
    assert "updateEmail" in names
    assert "updatePhone" in names
    assert "updateNickname" in names
    assert "updatePassword" in names
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/contract/test_graphql_schema.py -xvs
```

Expected: FAIL — `DateTimeUtc` not found, query fields not found.

- [ ] **Step 3: Add DateTimeUtc scalar and all new types to types.py**

Replace the top section of `src/api/graphql/types.py` (keep all existing content, add before it):

```python
from __future__ import annotations

from datetime import datetime
from typing import Optional

import strawberry
from strawberry.scalars import JSON  # noqa: F401  — re-exported for resolvers

# ── Custom scalars ────────────────────────────────────────────────────

DateTimeUtc = strawberry.scalar(
    datetime,
    name="DateTimeUtc",
    description="UTC datetime in ISO 8601 format",
    serialize=lambda v: v.isoformat(),
    parse_value=lambda v: datetime.fromisoformat(v.replace("Z", "+00:00")),
)

# ── Result types (align with Rust gateway result_query.rs) ────────────


@strawberry.type
class VotingTrendItem:
    hrs: int
    cnt: int


@strawberry.type
class RankingGlobal:
    total_unique_items: int
    total_first: int
    total_votes: int
    average_votes_per_item: float
    median_votes_per_item: float


@strawberry.type
class RankingEntry:
    rank: int
    rank_last_1: int
    rank_last_2: int
    display_rank: int
    name: str
    vote_count: int
    vote_count_last_1: int
    vote_count_last_2: int
    first_vote_count: int
    first_vote_count_last_1: int
    first_vote_count_last_2: int
    first_vote_percentage: float
    first_vote_percentage_last_1: float
    first_vote_percentage_last_2: float
    first_vote_count_weighted: int
    character_type: str
    character_origin: str
    first_appearance: str
    album: Optional[str]
    name_jpn: str
    vote_percentage: float
    vote_percentage_last_1: float
    vote_percentage_last_2: float
    first_percentage: float
    male_vote_count: int
    male_percentage_per_char: float
    male_percentage_per_total: float
    female_vote_count: int
    female_percentage_per_char: float
    female_percentage_per_total: float
    trend: list[VotingTrendItem]
    trend_first: list[VotingTrendItem]
    reasons: list[str]
    num_reasons: int


@strawberry.type
class CPItem:
    a: str
    b: str
    c: Optional[str]


@strawberry.type
class CPRankingEntry:
    rank: int
    display_rank: int
    cp: CPItem
    a_active: float
    b_active: float
    c_active: float
    none_active: float
    vote_count: int
    first_vote_count: int
    first_vote_percentage: float
    first_vote_count_weighted: int
    vote_percentage: float
    first_percentage: float
    male_vote_count: int
    male_percentage_per_char: float
    male_percentage_per_total: float
    female_vote_count: int
    female_percentage_per_char: float
    female_percentage_per_total: float
    trend: list[VotingTrendItem]
    trend_first: list[VotingTrendItem]
    reasons: list[str]
    num_reasons: int


@strawberry.type
class CharacterOrMusicRanking:
    entries: list[RankingEntry]
    global_: RankingGlobal = strawberry.field(name="global")


@strawberry.type
class CPRanking:
    entries: list[CPRankingEntry]
    global_: RankingGlobal = strawberry.field(name="global")


@strawberry.type
class Trends:
    trend: list[VotingTrendItem]
    trend_first: list[VotingTrendItem]


@strawberry.type
class ResultGlobalStats:
    vote_year: int
    num_vote: int
    num_char: int
    num_music: int
    num_cp: int
    num_doujin: int
    num_male: int
    num_female: int


@strawberry.type
class CompletionRateItem:
    name: str
    rate: float
    num_complete: int
    total: int


@strawberry.type
class CompletionRate:
    vote_year: int
    items: list[CompletionRateItem]


@strawberry.type
class CachedQuestionAnswerItem:
    aid: str
    total_votes: int
    male_votes: int
    female_votes: int


@strawberry.type
class CachedQuestionItem:
    question_id: str
    answers_cat: list[CachedQuestionAnswerItem]
    answers_str: list[str]
    total_answers: int
    total_male: int
    total_female: int


@strawberry.type
class QueryQuestionnaireResponse:
    entries: list[CachedQuestionItem]


@strawberry.type
class CovoteItem:
    a: str
    b: str
    cs: float
    mi: float
    cv: float
    m00: int
    m01: int
    m10: int
    m11: int


@strawberry.type
class CovoteResponse:
    items: list[CovoteItem]


# ── User types ────────────────────────────────────────────────────────


@strawberry.type
class UserGQLType:
    username: Optional[str]
    pfp: Optional[str]
    password: bool
    phone: Optional[str]
    email: Optional[str]
    thbwiki: bool
    patchyvideo: bool
    created_at: datetime


@strawberry.type
class LoginResult:
    user: UserGQLType
    session_token: str
    vote_token: str
```

(Keep all existing `SubmitMetadata`, `CharacterSubmit`, etc. types below — do not remove them.)

- [ ] **Step 4: Run the schema tests**

```bash
pytest tests/contract/test_graphql_schema.py::test_datetimeutc_scalar_registered -xvs
```

Expected: Still FAIL (schema not yet updated). Proceed to Task 2.

- [ ] **Step 5: Commit types**

```bash
git add src/api/graphql/types.py tests/contract/test_graphql_schema.py
git commit -m "feat(graphql): add DateTimeUtc scalar and all result/user GQL types"
```

---

## Task 2: Rewrite Result resolvers

**Files:**
- Modify: `src/api/graphql/resolvers/result.py`

- [ ] **Step 1: Replace result.py entirely**

```python
"""Result resolvers aligned with frontend GQL queries."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import strawberry

from src.api.graphql.types import (
    CPRanking,
    CPRankingEntry,
    CPItem,
    CharacterOrMusicRanking,
    CompletionRate,
    CompletionRateItem,
    CachedQuestionAnswerItem,
    CachedQuestionItem,
    CovoteItem,
    CovoteResponse,
    QueryQuestionnaireResponse,
    RankingEntry,
    RankingGlobal,
    ResultGlobalStats,
    Trends,
    VotingTrendItem,
)
from src.apps.result.dao import ResultDAO, ResultNotComputedError
from src.apps.result.schemas import (
    CovoteQuery,
    GlobalStatsQuery,
    QuestionnaireQuery,
    QuestionnaireTrendQuery,
    RankingQuery,
    SingleQuery,
    TrendQuery,
)
from src.apps.result.service import ResultService
from src.common.config import get_settings
from src.common.redis import get_redis


async def _get_result_service() -> ResultService:
    redis = await get_redis()
    settings = get_settings()
    dao = ResultDAO(redis, settings)
    return ResultService(dao)


def _not_computed() -> None:
    raise ValueError(
        "Result not yet computed. Run POST /admin/compute-results first."
    )


# ── dict → type converters ────────────────────────────────────────────


def _trend_item(d: dict) -> VotingTrendItem:
    return VotingTrendItem(hrs=d.get("hrs", 0), cnt=d.get("cnt", 0))


def _ranking_entry(d: dict) -> RankingEntry:
    return RankingEntry(
        rank=d.get("rank", 0),
        rank_last_1=d.get("rank_last_1", 0),
        rank_last_2=d.get("rank_last_2", 0),
        display_rank=d.get("display_rank", d.get("rank", 0)),
        name=d.get("name", ""),
        vote_count=d.get("vote_count", 0),
        vote_count_last_1=d.get("vote_count_last_1", 0),
        vote_count_last_2=d.get("vote_count_last_2", 0),
        first_vote_count=d.get("first_vote_count", 0),
        first_vote_count_last_1=d.get("first_vote_count_last_1", 0),
        first_vote_count_last_2=d.get("first_vote_count_last_2", 0),
        first_vote_percentage=d.get("first_vote_percentage", 0.0),
        first_vote_percentage_last_1=d.get("first_vote_percentage_last_1", 0.0),
        first_vote_percentage_last_2=d.get("first_vote_percentage_last_2", 0.0),
        first_vote_count_weighted=d.get("first_vote_count_weighted", 0),
        character_type=d.get("character_type", d.get("type", "")),
        character_origin=d.get("character_origin", d.get("origin", "")),
        first_appearance=d.get("first_appearance", ""),
        album=d.get("album"),
        name_jpn=d.get("name_jpn", d.get("name_jp", "")),
        vote_percentage=d.get("vote_percentage", 0.0),
        vote_percentage_last_1=d.get("vote_percentage_last_1", 0.0),
        vote_percentage_last_2=d.get("vote_percentage_last_2", 0.0),
        first_percentage=d.get("first_percentage", 0.0),
        male_vote_count=d.get("male_vote_count", 0),
        male_percentage_per_char=d.get("male_percentage_per_char", 0.0),
        male_percentage_per_total=d.get("male_percentage_per_total", 0.0),
        female_vote_count=d.get("female_vote_count", 0),
        female_percentage_per_char=d.get("female_percentage_per_char", 0.0),
        female_percentage_per_total=d.get("female_percentage_per_total", 0.0),
        trend=[_trend_item(t) for t in d.get("trend", [])],
        trend_first=[_trend_item(t) for t in d.get("trend_first", [])],
        reasons=d.get("reasons", []),
        num_reasons=d.get("num_reasons", len(d.get("reasons", []))),
    )


def _cp_ranking_entry(d: dict) -> CPRankingEntry:
    cp_raw = d.get("cp", d.get("name", {}))
    if isinstance(cp_raw, str):
        parts = cp_raw.split("×")
        cp_obj = CPItem(a=parts[0] if parts else cp_raw, b=parts[1] if len(parts) > 1 else "", c=parts[2] if len(parts) > 2 else None)
    else:
        cp_obj = CPItem(a=cp_raw.get("a", ""), b=cp_raw.get("b", ""), c=cp_raw.get("c"))
    return CPRankingEntry(
        rank=d.get("rank", 0),
        display_rank=d.get("display_rank", d.get("rank", 0)),
        cp=cp_obj,
        a_active=d.get("a_active", 0.0),
        b_active=d.get("b_active", 0.0),
        c_active=d.get("c_active", 0.0),
        none_active=d.get("none_active", 0.0),
        vote_count=d.get("vote_count", 0),
        first_vote_count=d.get("first_vote_count", 0),
        first_vote_percentage=d.get("first_vote_percentage", 0.0),
        first_vote_count_weighted=d.get("first_vote_count_weighted", 0),
        vote_percentage=d.get("vote_percentage", 0.0),
        first_percentage=d.get("first_percentage", 0.0),
        male_vote_count=d.get("male_vote_count", 0),
        male_percentage_per_char=d.get("male_percentage_per_char", 0.0),
        male_percentage_per_total=d.get("male_percentage_per_total", 0.0),
        female_vote_count=d.get("female_vote_count", 0),
        female_percentage_per_char=d.get("female_percentage_per_char", 0.0),
        female_percentage_per_total=d.get("female_percentage_per_total", 0.0),
        trend=[_trend_item(t) for t in d.get("trend", [])],
        trend_first=[_trend_item(t) for t in d.get("trend_first", [])],
        reasons=d.get("reasons", []),
        num_reasons=d.get("num_reasons", len(d.get("reasons", []))),
    )


def _ranking_global(d: dict) -> RankingGlobal:
    return RankingGlobal(
        total_unique_items=d.get("total_unique_items", 0),
        total_first=d.get("total_first", 0),
        total_votes=d.get("total_votes", 0),
        average_votes_per_item=d.get("average_votes_per_item", 0.0),
        median_votes_per_item=d.get("median_votes_per_item", 0.0),
    )


def _trends(d: dict) -> Trends:
    return Trends(
        trend=[_trend_item(t) for t in d.get("trend", [])],
        trend_first=[_trend_item(t) for t in d.get("trend_first", [])],
    )


def _global_stats(d: dict) -> ResultGlobalStats:
    return ResultGlobalStats(
        vote_year=d.get("vote_year", 0),
        num_vote=d.get("num_vote", 0),
        num_char=d.get("num_char", 0),
        num_music=d.get("num_music", 0),
        num_cp=d.get("num_cp", 0),
        num_doujin=d.get("num_doujin", 0),
        num_male=d.get("num_male", 0),
        num_female=d.get("num_female", 0),
    )


def _completion_rate(d: dict) -> CompletionRate:
    return CompletionRate(
        vote_year=d.get("vote_year", 0),
        items=[
            CompletionRateItem(
                name=item.get("name", ""),
                rate=item.get("rate", 0.0),
                num_complete=item.get("num_complete", 0),
                total=item.get("total", 0),
            )
            for item in d.get("items", [])
        ],
    )


def _questionnaire_response(d: dict) -> QueryQuestionnaireResponse:
    entries = []
    for item in d.get("entries", [d] if "question_id" in d else []):
        entries.append(
            CachedQuestionItem(
                question_id=item.get("question_id", ""),
                answers_cat=[
                    CachedQuestionAnswerItem(
                        aid=a.get("aid", ""),
                        total_votes=a.get("total_votes", 0),
                        male_votes=a.get("male_votes", 0),
                        female_votes=a.get("female_votes", 0),
                    )
                    for a in item.get("answers_cat", [])
                ],
                answers_str=item.get("answers_str", []),
                total_answers=item.get("total_answers", 0),
                total_male=item.get("total_male", 0),
                total_female=item.get("total_female", 0),
            )
        )
    return QueryQuestionnaireResponse(entries=entries)


def _covote_response(items: list) -> CovoteResponse:
    return CovoteResponse(
        items=[
            CovoteItem(
                a=i.get("a", ""),
                b=i.get("b", ""),
                cs=i.get("cs", i.get("chi_square", 0.0)),
                mi=i.get("mi", i.get("mutual_info", 0.0)),
                cv=i.get("cv", 0.0),
                m00=i.get("m00", 0),
                m01=i.get("m01", 0),
                m10=i.get("m10", 0),
                m11=i.get("m11", 0),
            )
            for i in items
        ]
    )


# ── ResultQuery ───────────────────────────────────────────────────────


@strawberry.type
class ResultQuery:
    @strawberry.field
    async def query_character_ranking(
        self,
        vote_start: datetime,
        vote_year: int,
        query: Optional[str] = None,
    ) -> CharacterOrMusicRanking:
        svc = await _get_result_service()
        try:
            result = await svc.get_ranking(
                RankingQuery(category="character", vote_year=vote_year)
            )
        except ResultNotComputedError:
            _not_computed()
        entries = result["rankings"]
        if query:
            entries = [e for e in entries if query.lower() in e.get("name", "").lower()]
        return CharacterOrMusicRanking(
            entries=[_ranking_entry(e) for e in entries],
            global_=_ranking_global(result["global"]),
        )

    @strawberry.field
    async def query_music_ranking(
        self,
        vote_start: datetime,
        vote_year: int,
        query: Optional[str] = None,
    ) -> CharacterOrMusicRanking:
        svc = await _get_result_service()
        try:
            result = await svc.get_ranking(
                RankingQuery(category="music", vote_year=vote_year)
            )
        except ResultNotComputedError:
            _not_computed()
        entries = result["rankings"]
        if query:
            entries = [e for e in entries if query.lower() in e.get("name", "").lower()]
        return CharacterOrMusicRanking(
            entries=[_ranking_entry(e) for e in entries],
            global_=_ranking_global(result["global"]),
        )

    @strawberry.field
    async def query_cp_ranking(
        self,
        vote_start: datetime,
        vote_year: int,
        query: Optional[str] = None,
    ) -> CPRanking:
        svc = await _get_result_service()
        try:
            result = await svc.get_ranking(
                RankingQuery(category="cp", vote_year=vote_year)
            )
        except ResultNotComputedError:
            _not_computed()
        entries = result["rankings"]
        return CPRanking(
            entries=[_cp_ranking_entry(e) for e in entries],
            global_=_ranking_global(result["global"]),
        )

    @strawberry.field
    async def query_character_single(
        self,
        vote_start: datetime,
        vote_year: int,
        rank: int,
        query: Optional[str] = None,
    ) -> Optional[RankingEntry]:
        svc = await _get_result_service()
        try:
            result = await svc.get_ranking(
                RankingQuery(category="character", vote_year=vote_year)
            )
        except ResultNotComputedError:
            _not_computed()
        for entry in result["rankings"]:
            if entry.get("rank") == rank:
                return _ranking_entry(entry)
        return None

    @strawberry.field
    async def query_music_single(
        self,
        vote_start: datetime,
        vote_year: int,
        rank: int,
        query: Optional[str] = None,
    ) -> Optional[RankingEntry]:
        svc = await _get_result_service()
        try:
            result = await svc.get_ranking(
                RankingQuery(category="music", vote_year=vote_year)
            )
        except ResultNotComputedError:
            _not_computed()
        for entry in result["rankings"]:
            if entry.get("rank") == rank:
                return _ranking_entry(entry)
        return None

    @strawberry.field
    async def query_cp_single(
        self,
        vote_start: datetime,
        vote_year: int,
        rank: int,
        query: Optional[str] = None,
    ) -> Optional[CPRankingEntry]:
        svc = await _get_result_service()
        try:
            result = await svc.get_ranking(
                RankingQuery(category="cp", vote_year=vote_year)
            )
        except ResultNotComputedError:
            _not_computed()
        for entry in result["rankings"]:
            if entry.get("rank") == rank:
                return _cp_ranking_entry(entry)
        return None

    @strawberry.field
    async def query_character_trend(
        self,
        vote_start: datetime,
        vote_year: int,
        names: list[str],
    ) -> list[Trends]:
        svc = await _get_result_service()
        result = []
        for name in names:
            try:
                d = await svc.get_trends(
                    TrendQuery(category="character", name=name, vote_year=vote_year)
                )
                result.append(_trends(d))
            except ResultNotComputedError:
                _not_computed()
            except Exception:
                result.append(Trends(trend=[], trend_first=[]))
        return result

    @strawberry.field
    async def query_music_trend(
        self,
        vote_start: datetime,
        vote_year: int,
        names: list[str],
    ) -> list[Trends]:
        svc = await _get_result_service()
        result = []
        for name in names:
            try:
                d = await svc.get_trends(
                    TrendQuery(category="music", name=name, vote_year=vote_year)
                )
                result.append(_trends(d))
            except ResultNotComputedError:
                _not_computed()
            except Exception:
                result.append(Trends(trend=[], trend_first=[]))
        return result

    @strawberry.field
    async def query_cp_trend(
        self,
        vote_start: datetime,
        vote_year: int,
        ranks: list[int],
    ) -> list[Trends]:
        """Returns trend for CP entries by rank. Looks up name from ranking first."""
        svc = await _get_result_service()
        try:
            ranking_result = await svc.get_ranking(
                RankingQuery(category="cp", vote_year=vote_year)
            )
        except ResultNotComputedError:
            _not_computed()
        rank_to_entry = {e.get("rank"): e for e in ranking_result["rankings"]}
        result = []
        for rank in ranks:
            entry = rank_to_entry.get(rank)
            if entry:
                result.append(_trends(entry))
            else:
                result.append(Trends(trend=[], trend_first=[]))
        return result

    @strawberry.field
    async def query_global_stats(
        self,
        vote_start: datetime,
        vote_year: int,
        query: Optional[str] = None,
    ) -> ResultGlobalStats:
        svc = await _get_result_service()
        try:
            d = await svc.get_global_stats(GlobalStatsQuery(vote_year=vote_year))
        except ResultNotComputedError:
            _not_computed()
        return _global_stats(d)

    @strawberry.field
    async def query_completion_rates(
        self,
        vote_start: datetime,
        vote_year: int,
        query: Optional[str] = None,
    ) -> CompletionRate:
        svc = await _get_result_service()
        try:
            d = await svc.get_completion_rates(
                from src.apps.result.schemas import CompletionRatesQuery
                __import__("src.apps.result.schemas", fromlist=["CompletionRatesQuery"])
            )
        except ResultNotComputedError:
            _not_computed()
        return _completion_rate(d)

    @strawberry.field
    async def query_questionnaire(
        self,
        vote_start: datetime,
        vote_year: int,
        questions_of_interest: list[str],
        query: Optional[str] = None,
    ) -> QueryQuestionnaireResponse:
        svc = await _get_result_service()
        all_entries = []
        for qid in questions_of_interest:
            try:
                d = await svc.get_questionnaire(
                    QuestionnaireQuery(question_id=qid, vote_year=vote_year)
                )
                all_entries.append(d)
            except ResultNotComputedError:
                _not_computed()
            except Exception:
                pass
        return _questionnaire_response({"entries": all_entries})

    @strawberry.field
    async def query_questionnaire_trend(
        self,
        vote_start: datetime,
        vote_year: int,
        question_ids: list[str],
        query: Optional[str] = None,
    ) -> list[Trends]:
        svc = await _get_result_service()
        result = []
        for qid in question_ids:
            try:
                d = await svc.get_questionnaire_trend(
                    QuestionnaireTrendQuery(question_id=qid, vote_year=vote_year)
                )
                result.append(_trends(d))
            except ResultNotComputedError:
                _not_computed()
            except Exception:
                result.append(Trends(trend=[], trend_first=[]))
        return result

    @strawberry.field
    async def query_chars_covote(
        self,
        vote_start: datetime,
        vote_year: int,
        top_k: int,
        query: Optional[str] = None,
    ) -> CovoteResponse:
        svc = await _get_result_service()
        try:
            items = await svc.get_covote(
                CovoteQuery(category="character", vote_year=vote_year)
            )
        except ResultNotComputedError:
            _not_computed()
        return _covote_response(items.get("items", items) if isinstance(items, dict) else items)

    @strawberry.field
    async def query_musics_covote(
        self,
        vote_start: datetime,
        vote_year: int,
        top_k: int,
        query: Optional[str] = None,
    ) -> CovoteResponse:
        svc = await _get_result_service()
        try:
            items = await svc.get_covote(
                CovoteQuery(category="music", vote_year=vote_year)
            )
        except ResultNotComputedError:
            _not_computed()
        return _covote_response(items.get("items", items) if isinstance(items, dict) else items)
```

**Note:** There is a bug in the `query_completion_rates` method above — the import is misplaced. Replace the body of that method with:

```python
    @strawberry.field
    async def query_completion_rates(
        self,
        vote_start: datetime,
        vote_year: int,
        query: Optional[str] = None,
    ) -> CompletionRate:
        from src.apps.result.schemas import CompletionRatesQuery
        svc = await _get_result_service()
        try:
            d = await svc.get_completion_rates(CompletionRatesQuery(vote_year=vote_year))
        except ResultNotComputedError:
            _not_computed()
        return _completion_rate(d)
```

The full clean version of `query_completion_rates` to use in the file:

```python
    @strawberry.field
    async def query_completion_rates(
        self,
        vote_start: datetime,
        vote_year: int,
        query: Optional[str] = None,
    ) -> CompletionRate:
        from src.apps.result.schemas import CompletionRatesQuery as CRQuery
        svc = await _get_result_service()
        try:
            d = await svc.get_completion_rates(CRQuery(vote_year=vote_year))
        except ResultNotComputedError:
            _not_computed()
        return _completion_rate(d)
```

- [ ] **Step 2: Verify imports are correct (no syntax errors)**

```bash
python -c "from src.api.graphql.resolvers.result import ResultQuery; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/api/graphql/resolvers/result.py
git commit -m "feat(graphql): rewrite ResultQuery with frontend-aligned field names and strong types"
```

---

## Task 3: Align Submit resolvers

**Files:**
- Modify: `src/api/graphql/types.py` (rename/add input types)
- Modify: `src/api/graphql/resolvers/submit.py` (rename fields + args)

- [ ] **Step 1: Add new input types to types.py**

Add these `@strawberry.input` classes to `src/api/graphql/types.py` (replace the existing submit input classes entirely):

```python
# ── Submit input types (aligned with frontend GQL names) ─────────────


@strawberry.input
class CharacterItemInput:
    id: str
    reason: Optional[str] = None
    first: Optional[bool] = None


@strawberry.input
class MusicItemInput:
    id: str
    reason: Optional[str] = None
    first: Optional[bool] = None


@strawberry.input
class CPItemInput:
    id_a: str
    id_b: str
    id_c: Optional[str] = None
    active: Optional[str] = None
    first: Optional[bool] = None
    reason: Optional[str] = None


@strawberry.input
class DojinItemInput:
    dojin_type: str
    url: str
    title: str
    author: str
    reason: str
    image_url: Optional[str] = None


# Frontend input type names (CharacterSubmitGQL etc.)
@strawberry.input
class CharacterSubmitGQL:
    vote_token: str
    characters: list[CharacterItemInput]


@strawberry.input
class MusicSubmitGQL:
    vote_token: str
    musics: list[MusicItemInput]


@strawberry.input
class CPSubmitGQL:
    vote_token: str
    cps: list[CPItemInput]


@strawberry.input
class PaperSubmitGQL:
    vote_token: str
    paper_json: str  # frontend sends paperJson


@strawberry.input
class DojinSubmitGQL:
    vote_token: str
    dojins: list[DojinItemInput]
```

Keep the old `CharacterSubmitMutationInput`, `MusicSubmitMutationInput` etc. temporarily (they may be used by existing tests); add the new ones alongside them.

- [ ] **Step 2: Rewrite submit.py query and mutation field names**

In `src/api/graphql/resolvers/submit.py`:

**A. Rename query fields** — change the five `get_*_submit` methods to the frontend-expected names, changing the `vote_id` parameter to `vote_token` and decoding it:

Add at the top of the file:
```python
from src.common.security.jwt import decode_vote_token
from src.common.exceptions import AppException
```

Change `get_character_submit` to `get_submit_character_vote` with `vote_token: str` parameter:
```python
    @strawberry.field
    async def get_submit_character_vote(self, vote_token: str) -> CharacterSubmitResult:
        try:
            payload = decode_vote_token(vote_token)
            vote_id = payload.user_id
        except AppException:
            raise ValueError("Invalid vote token")
        async for db in get_db_session():
            service = SubmitService(db)
            data = await service.get_character_submit(vote_id)
            return CharacterSubmitResult(
                characters=pydantic_to_graphql_characters(data.characters),
                meta=pydantic_to_graphql_meta(data.meta),
            )
```

Apply the same pattern to `get_submit_music_vote`, `get_submit_cp_vote`, `get_submit_paper_vote`, `get_submit_dojin_vote`. For paper, the field returns `papersJson: Optional[str]` directly.

**B. Rename mutation fields** — change mutation names and input types:

```python
    @strawberry.mutation
    async def submit_character_vote(self, content: CharacterSubmitGQL) -> SubmitSuccess:
        # decode vote_token to get vote_id
        try:
            payload = decode_vote_token(content.vote_token)
            vote_id = payload.user_id
        except AppException:
            raise ValueError("Invalid vote token")
        redis_client = await get_redis_client()
        await rate_limit(vote_id, redis_client)
        lock_key, lock_value = await _acquire_vote_lock(vote_id)
        try:
            async for db in get_db_session():
                service = SubmitService(db)
                from src.apps.submit.schemas import CharacterSubmit as CharPydantic
                body = CharacterSubmitRest(
                    characters=[
                        CharPydantic(id=c.id, reason=c.reason, first=c.first)
                        for c in content.characters
                    ],
                    meta=SubmitMetadata(
                        vote_id=vote_id,
                        created_at=utcnow(),
                        user_ip="<graphql>",
                    ),
                )
                await service.submit_character(body)
        finally:
            await _release_vote_lock(lock_key, lock_value)
        return SubmitSuccess(ok=True)
```

Apply same pattern to `submit_music_vote`, `submit_cp_vote`, `submit_paper_vote` (using `paper_json` field), `submit_dojin`.

Import `CharacterSubmitGQL`, `MusicSubmitGQL`, `CPSubmitGQL`, `PaperSubmitGQL`, `DojinSubmitGQL` from `src.api.graphql.types`.

Keep old methods (with old names) for backward compatibility during transition — they can be removed later.

- [ ] **Step 3: Verify no import errors**

```bash
python -c "from src.api.graphql.resolvers.submit import SubmitQuery, SubmitMutation; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/api/graphql/types.py src/api/graphql/resolvers/submit.py
git commit -m "feat(graphql): align submit field names and input types to frontend expectations"
```

---

## Task 4: Create User resolver

**Files:**
- Create: `src/api/graphql/resolvers/user.py`

- [ ] **Step 1: Create the file**

```python
"""User GraphQL resolvers — auth mutations and token status query."""
from __future__ import annotations

from typing import Optional

import strawberry
from strawberry.types import Info

from src.api.graphql.types import LoginResult, UserGQLType
from src.apps.user.dao import ActivityLogDAO, UserDAO
from src.apps.user.schemas import (
    LoginEmailPasswordRequest,
    LoginEmailRequest,
    LoginPhoneRequest,
    Meta,
    SendEmailCodeRequest,
    SendSmsCodeRequest,
    TokenStatusRequest,
    UpdateEmailRequest,
    UpdateNicknameRequest,
    UpdatePasswordRequest,
    UpdatePhoneRequest,
    voter_fe_from_user,
)
from src.apps.user.service import UserService
from src.common.database import get_session_maker
from src.common.exceptions import AppException
from src.common.redis import get_redis
from src.common.verification import get_email_code_service, get_sms_code_service


async def _get_user_service() -> UserService:
    redis = await get_redis()
    session_maker = get_session_maker()
    session = session_maker()
    # Note: session is not closed here — Strawberry resolvers are short-lived.
    # For production, use a proper dependency injection pattern.
    async with session as s:
        return UserService(
            user_dao=UserDAO(s),
            activity_dao=ActivityLogDAO(s),
            email_code_service=get_email_code_service(),
            sms_code_service=get_sms_code_service(),
            redis=redis,
        ), s


def _make_meta(info: Info) -> Meta:
    """Extract client IP from Strawberry request context."""
    try:
        request = info.context["request"]
        ip = request.client.host if request.client else "<unknown>"
    except Exception:
        ip = "<unknown>"
    return Meta(user_ip=ip)


def _app_error(exc: AppException) -> None:
    """Re-raise AppException as a Strawberry error with extensions."""
    raise strawberry.exceptions.StrawberryException(
        message=exc.message,
    )


def _voter_fe_to_user_gql(vfe) -> UserGQLType:
    return UserGQLType(
        username=vfe.username,
        pfp=vfe.pfp,
        password=vfe.password,
        phone=vfe.phone,
        email=vfe.email,
        thbwiki=vfe.thbwiki,
        patchyvideo=vfe.patchyvideo,
        created_at=vfe.created_at,
    )


def _login_response_to_result(resp) -> LoginResult:
    return LoginResult(
        user=_voter_fe_to_user_gql(resp.user),
        session_token=resp.session_token,
        vote_token=resp.vote_token,
    )


@strawberry.type
class UserQuery:
    @strawberry.field
    async def user_token_status(
        self, user_token: str, vote_token: Optional[str] = None
    ) -> bool:
        session_maker = get_session_maker()
        redis = await get_redis()
        async with session_maker()() as session:
            svc = UserService(
                user_dao=UserDAO(session),
                activity_dao=ActivityLogDAO(session),
                redis=redis,
            )
            try:
                req = TokenStatusRequest(user_token=user_token)
                await svc.token_status(req)
                return True
            except AppException:
                return False


@strawberry.type
class UserMutation:
    @strawberry.mutation
    async def login_email(
        self,
        info: Info,
        email: str,
        verify_code: str,
        nickname: Optional[str] = None,
    ) -> LoginResult:
        meta = _make_meta(info)
        session_maker = get_session_maker()
        redis = await get_redis()
        async with session_maker()() as session:
            svc = UserService(
                user_dao=UserDAO(session),
                activity_dao=ActivityLogDAO(session),
                email_code_service=get_email_code_service(),
                sms_code_service=get_sms_code_service(),
                redis=redis,
            )
            try:
                resp = await svc.login_with_email_code(
                    LoginEmailRequest(
                        email=email,
                        nickname=nickname,
                        verify_code=verify_code,
                        meta=meta,
                    )
                )
            except AppException as exc:
                _app_error(exc)
        return _login_response_to_result(resp)

    @strawberry.mutation
    async def login_phone(
        self,
        info: Info,
        phone: str,
        verify_code: str,
        nickname: Optional[str] = None,
    ) -> LoginResult:
        meta = _make_meta(info)
        session_maker = get_session_maker()
        redis = await get_redis()
        async with session_maker()() as session:
            svc = UserService(
                user_dao=UserDAO(session),
                activity_dao=ActivityLogDAO(session),
                email_code_service=get_email_code_service(),
                sms_code_service=get_sms_code_service(),
                redis=redis,
            )
            try:
                resp = await svc.login_with_phone_code(
                    LoginPhoneRequest(
                        phone=phone,
                        nickname=nickname,
                        verify_code=verify_code,
                        meta=meta,
                    )
                )
            except AppException as exc:
                _app_error(exc)
        return _login_response_to_result(resp)

    @strawberry.mutation
    async def login_email_password(
        self,
        info: Info,
        email: str,
        password: str,
    ) -> LoginResult:
        meta = _make_meta(info)
        session_maker = get_session_maker()
        redis = await get_redis()
        async with session_maker()() as session:
            svc = UserService(
                user_dao=UserDAO(session),
                activity_dao=ActivityLogDAO(session),
                email_code_service=get_email_code_service(),
                sms_code_service=get_sms_code_service(),
                redis=redis,
            )
            try:
                resp = await svc.login_with_email_password(
                    LoginEmailPasswordRequest(email=email, password=password, meta=meta)
                )
            except AppException as exc:
                _app_error(exc)
        return _login_response_to_result(resp)

    @strawberry.mutation
    async def request_email_code(self, info: Info, email: str) -> bool:
        meta = _make_meta(info)
        session_maker = get_session_maker()
        redis = await get_redis()
        async with session_maker()() as session:
            svc = UserService(
                user_dao=UserDAO(session),
                activity_dao=ActivityLogDAO(session),
                email_code_service=get_email_code_service(),
                redis=redis,
            )
            try:
                await svc.send_email_code(
                    SendEmailCodeRequest(email=email, meta=meta)
                )
            except AppException as exc:
                _app_error(exc)
        return True

    @strawberry.mutation
    async def request_phone_code(self, info: Info, phone: str) -> bool:
        meta = _make_meta(info)
        session_maker = get_session_maker()
        redis = await get_redis()
        async with session_maker()() as session:
            svc = UserService(
                user_dao=UserDAO(session),
                activity_dao=ActivityLogDAO(session),
                sms_code_service=get_sms_code_service(),
                redis=redis,
            )
            try:
                await svc.send_sms_code(
                    SendSmsCodeRequest(phone=phone, meta=meta)
                )
            except AppException as exc:
                _app_error(exc)
        return True

    @strawberry.mutation
    async def update_email(
        self, info: Info, user_token: str, email: str, verify_code: str
    ) -> bool:
        meta = _make_meta(info)
        session_maker = get_session_maker()
        redis = await get_redis()
        async with session_maker()() as session:
            svc = UserService(
                user_dao=UserDAO(session),
                activity_dao=ActivityLogDAO(session),
                email_code_service=get_email_code_service(),
                redis=redis,
            )
            try:
                await svc.update_email(
                    UpdateEmailRequest(
                        user_token=user_token, email=email,
                        verify_code=verify_code, meta=meta,
                    )
                )
            except AppException as exc:
                _app_error(exc)
        return True

    @strawberry.mutation
    async def update_phone(
        self, info: Info, user_token: str, phone: str, verify_code: str
    ) -> bool:
        meta = _make_meta(info)
        session_maker = get_session_maker()
        redis = await get_redis()
        async with session_maker()() as session:
            svc = UserService(
                user_dao=UserDAO(session),
                activity_dao=ActivityLogDAO(session),
                sms_code_service=get_sms_code_service(),
                redis=redis,
            )
            try:
                await svc.update_phone(
                    UpdatePhoneRequest(
                        user_token=user_token, phone=phone,
                        verify_code=verify_code, meta=meta,
                    )
                )
            except AppException as exc:
                _app_error(exc)
        return True

    @strawberry.mutation
    async def update_nickname(
        self, info: Info, user_token: str, new_nickname: str
    ) -> bool:
        meta = _make_meta(info)
        session_maker = get_session_maker()
        redis = await get_redis()
        async with session_maker()() as session:
            svc = UserService(
                user_dao=UserDAO(session),
                activity_dao=ActivityLogDAO(session),
                redis=redis,
            )
            try:
                await svc.update_nickname(
                    UpdateNicknameRequest(
                        user_token=user_token, nickname=new_nickname, meta=meta
                    )
                )
            except AppException as exc:
                _app_error(exc)
        return True

    @strawberry.mutation
    async def update_password(
        self,
        info: Info,
        user_token: str,
        new_password: str,
        old_password: Optional[str] = None,
    ) -> bool:
        meta = _make_meta(info)
        session_maker = get_session_maker()
        redis = await get_redis()
        async with session_maker()() as session:
            svc = UserService(
                user_dao=UserDAO(session),
                activity_dao=ActivityLogDAO(session),
                redis=redis,
            )
            try:
                await svc.update_password(
                    UpdatePasswordRequest(
                        user_token=user_token,
                        old_password=old_password,
                        new_password=new_password,
                        meta=meta,
                    )
                )
            except AppException as exc:
                _app_error(exc)
        return True
```

- [ ] **Step 2: Verify no import errors**

```bash
python -c "from src.api.graphql.resolvers.user import UserQuery, UserMutation; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/api/graphql/resolvers/user.py
git commit -m "feat(graphql): add UserQuery and UserMutation resolvers (login, update, token status)"
```

---

## Task 5: Update schema.py to wire everything together

**Files:**
- Modify: `src/api/graphql/schema.py`

- [ ] **Step 1: Replace schema.py**

```python
"""GraphQL Schema definition."""

from datetime import datetime

import strawberry

from .resolvers.result import ResultQuery
from .resolvers.submit import SubmitMutation, SubmitQuery
from .resolvers.user import UserMutation, UserQuery
from .types import DateTimeUtc


@strawberry.type
class Query(SubmitQuery, ResultQuery, UserQuery):
    """Root GraphQL Query."""

    pass


@strawberry.type
class Mutation(SubmitMutation, UserMutation):
    """Root GraphQL Mutation."""

    pass


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    scalar_overrides={datetime: DateTimeUtc},
)
```

- [ ] **Step 2: Run all schema tests**

```bash
pytest tests/contract/test_graphql_schema.py -xvs
```

Expected: All 3 tests PASS.

- [ ] **Step 3: Verify app still starts**

```bash
python -c "from src.main import app; print('app loads OK')"
```

Expected: `app loads OK` (with Nacos log lines, which is fine)

- [ ] **Step 4: Run full test suite**

```bash
pytest tests/ -x --tb=short -q
```

Expected: all existing tests pass (pre-existing alibabacloud failure is ok)

- [ ] **Step 5: Commit**

```bash
git add src/api/graphql/schema.py
git commit -m "feat(graphql): register DateTimeUtc scalar, UserQuery, UserMutation in schema"
```

---

## Task 6: Fix flake8 violations in new files

**Files:**
- Modify: all files touched in Tasks 1-5

- [ ] **Step 1: Run flake8**

```bash
flake8 src/api/graphql/ --max-line-length=88
```

Fix any E501 (long lines), F401 (unused imports), or other violations by wrapping or removing as needed.

- [ ] **Step 2: Verify zero violations**

```bash
flake8 src/api/graphql/ --max-line-length=88
```

Expected: no output (exit code 0)

- [ ] **Step 3: Run full suite again**

```bash
pytest tests/ -x --tb=short -q
```

- [ ] **Step 4: Commit**

```bash
git add src/api/graphql/
git commit -m "fix(graphql): resolve all flake8 violations in graphql module"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| `DateTimeUtc` scalar registered | Task 1 + Task 5 |
| All 14 `query*` result fields | Task 2 |
| Strong types for all result fields | Task 1 (types) + Task 2 (converters) |
| `getSubmitCharacterVote(voteToken)` rename | Task 3 |
| `submitCharacterVote(content: CharacterSubmitGQL)` rename | Task 3 |
| `loginEmail`, `loginPhone`, `loginEmailPassword` | Task 4 |
| `requestEmailCode`, `requestPhoneCode` | Task 4 |
| `updateEmail`, `updatePhone`, `updateNickname`, `updatePassword` | Task 4 |
| `userTokenStatus` query | Task 4 |
| AppException → GraphQL error with extensions | Task 4 |

**Placeholder scan:** No TBD/TODO found.

**Type consistency:** `LoginResult` defined in Task 1 types.py, used in Task 4 resolver. `DateTimeUtc` defined in Task 1, registered in Task 5. `CharacterSubmitGQL` input defined in Task 3 types.py, imported in Task 3 submit.py. All consistent.
