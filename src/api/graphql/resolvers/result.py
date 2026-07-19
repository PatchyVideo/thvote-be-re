"""Result resolvers for GraphQL API."""

from typing import Optional

import strawberry

from src.api.graphql.errors import map_app_errors
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
from src.common.exceptions import ValidationError
from src.common.redis import get_redis

_SERVICE = "result"  # extensions.service，与 result_compat.py 用同一个 service 名


async def _get_result_service() -> ResultService:
    redis = await get_redis()
    settings = get_settings()
    dao = ResultDAO(redis, settings)
    return ResultService(dao)


def _not_computed_error(exc: ResultNotComputedError) -> None:
    """``ResultNotComputedError`` → 稳定、可辨识、不泄内部细节的错误。

    之前这里直接抛 ``ValueError("... Run POST /api/v1/admin/compute-results
    first.")``；``ResultQuery`` 没有 ``map_app_errors`` 包裹，这条 message
    会原样穿透到匿名调用方，等于把内部 admin 接口路径广播出去。改成与
    ``result_compat.py._map_not_computed_error`` 同款的稳定 kind，经下面的
    ``map_app_errors(service=_SERVICE)`` 包裹后不再透出任何内部细节。
    """
    raise ValidationError(
        "RESULT_NOT_COMPUTED",
        human_readable_message="投票结果尚未生成，请稍后再试",
    ) from exc


@strawberry.type
class ResultQuery:
    """旧版 JSON 标量查询；见 result_compat.py 的类型化替代。

    每个字段都用 ``map_app_errors(service=_SERVICE)`` 包裹——不然
    ``_not_computed_error`` 抛出的 ``ValidationError``（乃至任何未预期异常）
    会带着原始 message/堆栈直接穿透到匿名调用方。
    """

    @strawberry.field(description="Ranking for character, music, or CP.")
    async def ranking(
        self,
        category: str = "character",
        vote_year: Optional[int] = None,
        names: Optional[list[str]] = None,
    ) -> JSON:
        async with map_app_errors(service=_SERVICE):
            svc = await _get_result_service()
            try:
                return await svc.get_ranking(
                    RankingQuery(
                        category=category, vote_year=vote_year, names=names or []
                    )
                )
            except ResultNotComputedError as exc:
                _not_computed_error(exc)
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.field(description="Voting trends for a named entity.")
    async def trends(
        self,
        name: str,
        category: str = "character",
        vote_year: Optional[int] = None,
    ) -> JSON:
        async with map_app_errors(service=_SERVICE):
            svc = await _get_result_service()
            try:
                return await svc.get_trends(
                    TrendQuery(name=name, category=category, vote_year=vote_year)
                )
            except ResultNotComputedError as exc:
                _not_computed_error(exc)
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.field(description="Global voting statistics.")
    async def global_stats(self, vote_year: Optional[int] = None) -> JSON:
        async with map_app_errors(service=_SERVICE):
            svc = await _get_result_service()
            try:
                return await svc.get_global_stats(
                    GlobalStatsQuery(vote_year=vote_year)
                )
            except ResultNotComputedError as exc:
                _not_computed_error(exc)
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.field(description="Single entity ranking entry.")
    async def single_entity(
        self,
        name: str,
        category: str = "character",
        vote_year: Optional[int] = None,
    ) -> JSON:
        async with map_app_errors(service=_SERVICE):
            svc = await _get_result_service()
            try:
                return await svc.get_single_entity(
                    SingleQuery(name=name, category=category, vote_year=vote_year)
                )
            except ResultNotComputedError as exc:
                _not_computed_error(exc)
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.field(description="Voting reasons for a named entity.")
    async def reasons(
        self,
        name: str,
        category: str = "character",
        vote_year: Optional[int] = None,
    ) -> JSON:
        async with map_app_errors(service=_SERVICE):
            svc = await _get_result_service()
            try:
                return await svc.get_reasons(
                    ReasonQuery(name=name, category=category, vote_year=vote_year)
                )
            except ResultNotComputedError as exc:
                _not_computed_error(exc)
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.field(description="Co-vote statistics for a category.")
    async def covote(
        self,
        category: str = "character",
        vote_year: Optional[int] = None,
    ) -> JSON:
        async with map_app_errors(service=_SERVICE):
            svc = await _get_result_service()
            try:
                return await svc.get_covote(
                    CovoteQuery(category=category, vote_year=vote_year)
                )
            except ResultNotComputedError as exc:
                _not_computed_error(exc)
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.field(description="Voting completion rates by category.")
    async def completion_rates(self, vote_year: Optional[int] = None) -> JSON:
        async with map_app_errors(service=_SERVICE):
            svc = await _get_result_service()
            try:
                return await svc.get_completion_rates(
                    CompletionRatesQuery(vote_year=vote_year)
                )
            except ResultNotComputedError as exc:
                _not_computed_error(exc)
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.field(description="Questionnaire results for a specific question.")
    async def questionnaire(
        self,
        question_id: str,
        vote_year: Optional[int] = None,
    ) -> JSON:
        async with map_app_errors(service=_SERVICE):
            svc = await _get_result_service()
            try:
                return await svc.get_questionnaire(
                    QuestionnaireQuery(question_id=question_id, vote_year=vote_year)
                )
            except ResultNotComputedError as exc:
                _not_computed_error(exc)
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.field(description="Questionnaire trend data for a specific question.")
    async def questionnaire_trend(
        self,
        question_id: str,
        vote_year: Optional[int] = None,
    ) -> JSON:
        async with map_app_errors(service=_SERVICE):
            svc = await _get_result_service()
            try:
                return await svc.get_questionnaire_trend(
                    QuestionnaireTrendQuery(
                        question_id=question_id, vote_year=vote_year
                    )
                )
            except ResultNotComputedError as exc:
                _not_computed_error(exc)
        raise RuntimeError("unreachable")  # pragma: no cover
