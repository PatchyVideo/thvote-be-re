"""Result service layer."""

from src.apps.result.dao import ResultDAO
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
        return await self.result_dao.get_questionnaire_trend(query.question_id, query.vote_year)
