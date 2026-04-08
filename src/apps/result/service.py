"""Result service layer."""

from src.apps.result.dao import ResultDAO
from src.apps.result.schemas import (CompletionRatesQuery, CovoteQuery,
                                     GlobalStats, GlobalStatsQuery,
                                     QuestionnaireQuery,
                                     QuestionnaireTrendQuery,
                                     RankingCharacterMusic, RankingQuery,
                                     ReasonQuery, Reasons, SingleQuery,
                                     TrendQuery, Trends, VotableBase)


class ResultService:
    """Service for result query operations."""

    def __init__(self, result_dao: ResultDAO):
        self.result_dao = result_dao

    async def get_ranking(self, query: RankingQuery) -> RankingCharacterMusic:
        """Get ranking for characters or music."""
        rankings = await self.result_dao.get_ranking(query)
        return RankingCharacterMusic(rankings=rankings)

    async def get_trends(self, query: TrendQuery) -> Trends:
        """Get voting trends."""
        return await self.result_dao.get_trends(query)

    async def get_global_stats(self, query: GlobalStatsQuery) -> GlobalStats:
        """Get global voting statistics."""
        stats = await self.result_dao.get_global_stats(query)
        return GlobalStats(**stats)

    async def get_single_entity(self, query: SingleQuery) -> dict | None:
        """Get a single votable entity."""
        return (
            (await self.result_dao.get_single_entity(query)).model_dump()
            if await self.result_dao.get_single_entity(query)
            else None
        )

    async def get_reasons(self, query: ReasonQuery) -> Reasons:
        """Get voting reasons for an entity."""
        return await self.result_dao.get_reasons(query)

    async def get_covote(self, query: CovoteQuery) -> dict:
        """Get co-vote statistics between two entities."""
        return await self.result_dao.get_covote(query)

    async def get_completion_rates(
        self, query: CompletionRatesQuery
    ) -> dict[str, float]:
        """Get voting completion rates."""
        return await self.result_dao.get_completion_rates(query)

    async def get_questionnaire(self, query: QuestionnaireQuery) -> dict:
        """Get questionnaire data for a vote ID."""
        return await self.result_dao.get_questionnaire(query)

    async def get_questionnaire_trend(self, query: QuestionnaireTrendQuery) -> dict:
        """Get questionnaire trend data."""
        return await self.result_dao.get_questionnaire_trend(query)
