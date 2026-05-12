"""Result resolvers for GraphQL API."""

from typing import Optional

import strawberry

from src.api.graphql.types import JSON
from src.apps.result.dao import ResultDAO, ResultNotComputedError
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
from src.common.config import get_settings
from src.common.redis import get_redis


async def _get_result_service() -> ResultService:
    redis = await get_redis()
    settings = get_settings()
    dao = ResultDAO(redis, settings)
    return ResultService(dao)


def _not_computed_error(exc: ResultNotComputedError) -> None:
    raise ValueError(
        "Result not yet computed. Run POST /api/v1/admin/compute-results first."
    ) from exc


@strawberry.type
class ResultQuery:
    @strawberry.field(description="Ranking for character, music, or CP.")
    async def ranking(
        self,
        category: str = "character",
        vote_year: Optional[int] = None,
        names: Optional[list[str]] = None,
    ) -> JSON:
        svc = await _get_result_service()
        try:
            return await svc.get_ranking(
                RankingQuery(category=category, vote_year=vote_year, names=names or [])
            )
        except ResultNotComputedError as exc:
            _not_computed_error(exc)

    @strawberry.field(description="Voting trends for a named entity.")
    async def trends(
        self,
        name: str,
        category: str = "character",
        vote_year: Optional[int] = None,
    ) -> JSON:
        svc = await _get_result_service()
        try:
            return await svc.get_trends(
                TrendQuery(name=name, category=category, vote_year=vote_year)
            )
        except ResultNotComputedError as exc:
            _not_computed_error(exc)

    @strawberry.field(description="Global voting statistics.")
    async def global_stats(self, vote_year: Optional[int] = None) -> JSON:
        svc = await _get_result_service()
        try:
            return await svc.get_global_stats(GlobalStatsQuery(vote_year=vote_year))
        except ResultNotComputedError as exc:
            _not_computed_error(exc)

    @strawberry.field(description="Single entity ranking entry.")
    async def single_entity(
        self,
        name: str,
        category: str = "character",
        vote_year: Optional[int] = None,
    ) -> JSON:
        svc = await _get_result_service()
        try:
            return await svc.get_single_entity(
                SingleQuery(name=name, category=category, vote_year=vote_year)
            )
        except ResultNotComputedError as exc:
            _not_computed_error(exc)

    @strawberry.field(description="Voting reasons for a named entity.")
    async def reasons(
        self,
        name: str,
        category: str = "character",
        vote_year: Optional[int] = None,
    ) -> JSON:
        svc = await _get_result_service()
        try:
            return await svc.get_reasons(
                ReasonQuery(name=name, category=category, vote_year=vote_year)
            )
        except ResultNotComputedError as exc:
            _not_computed_error(exc)

    @strawberry.field(description="Co-vote statistics for a category.")
    async def covote(
        self,
        category: str = "character",
        vote_year: Optional[int] = None,
    ) -> JSON:
        svc = await _get_result_service()
        try:
            return await svc.get_covote(
                CovoteQuery(category=category, vote_year=vote_year)
            )
        except ResultNotComputedError as exc:
            _not_computed_error(exc)

    @strawberry.field(description="Voting completion rates by category.")
    async def completion_rates(self, vote_year: Optional[int] = None) -> JSON:
        svc = await _get_result_service()
        try:
            return await svc.get_completion_rates(
                CompletionRatesQuery(vote_year=vote_year)
            )
        except ResultNotComputedError as exc:
            _not_computed_error(exc)

    @strawberry.field(description="Questionnaire results for a specific question.")
    async def questionnaire(
        self,
        question_id: str,
        vote_year: Optional[int] = None,
    ) -> JSON:
        svc = await _get_result_service()
        try:
            return await svc.get_questionnaire(
                QuestionnaireQuery(question_id=question_id, vote_year=vote_year)
            )
        except ResultNotComputedError as exc:
            _not_computed_error(exc)

    @strawberry.field(description="Questionnaire trend data for a specific question.")
    async def questionnaire_trend(
        self,
        question_id: str,
        vote_year: Optional[int] = None,
    ) -> JSON:
        svc = await _get_result_service()
        try:
            return await svc.get_questionnaire_trend(
                QuestionnaireTrendQuery(question_id=question_id, vote_year=vote_year)
            )
        except ResultNotComputedError as exc:
            _not_computed_error(exc)
