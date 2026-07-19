"""GraphQL 排名查询契约桥 — 前端(旧 Rust gateway)排名查询迁移到 compute 管线。

前端(vote-result)历史 gql 文档按名字严格校验，直接查
``queryCharacterRanking`` / ``queryMusicRanking`` / ``queryCPRanking`` 会得到
"Cannot query field ... on type 'Query'"。本模块只做 dict → strawberry 类型
转换 + 契约层三个行为(voteYear 回落 / query DSL 拒绝 / 上届字段置零)，核心
计算逻辑仍在 compute.py / compute_service.py(Task 3/4)。输出类型全部来自
``src.api.graphql.types``(Rust gateway result_query.rs 对齐版，Task 5 之前
未被任何 resolver 引用)。

契约与决策见 .superpowers/sdd/task-5-brief.md。
"""

from __future__ import annotations

import logging
from typing import Optional

import strawberry

from src.api.graphql.errors import map_app_errors
from src.api.graphql.types import (
    CharacterOrMusicRanking,
    CPItem,
    CPRanking,
    CPRankingEntry,
    DateTimeUtc,
    RankingEntry,
    RankingGlobal,
    VotingTrendItem,
)
from src.apps.result.dao import ResultDAO, ResultNotComputedError
from src.apps.result.schemas import RankingQuery
from src.apps.result.service import ResultService
from src.apps.result.whitelist import Whitelist, load_whitelist
from src.common.config import Settings, get_settings
from src.common.exceptions import ValidationError
from src.common.redis import get_redis

logger = logging.getLogger(__name__)

_SERVICE = "result"  # extensions.service，对齐 brief 要求的 map_app_errors(service="result")


async def _get_result_service() -> ResultService:
    redis = await get_redis()
    settings = get_settings()
    return ResultService(ResultDAO(redis, settings))


# ── 公共助手(本任务建立，后续任务复用) ─────────────────────────────


async def _resolve_vote_year(
    dao: ResultDAO, requested: Optional[int], settings: Settings
) -> int:
    """该年有数据就用，否则回落 settings.vote_year 并记一条日志。

    前端硬编码 ``voteYear: 11``（旧契约遗留），但数据实际落在
    ``settings.vote_year`` 下。用 ``get_global_stats`` 探测该年是否已跑过
    compute（每年计算一次、与 category 无关，天然是"该年是否有数据"的探针），
    没有数据才回落——不能仅因为前端传了旧的 legacy 年份就整体 503。
    """
    year = requested if requested is not None else settings.vote_year
    try:
        await dao.get_global_stats(year)
        return year
    except ResultNotComputedError:
        if year != settings.vote_year:
            logger.info(
                "result_compat: vote_year=%s has no computed data, "
                "falling back to settings.vote_year=%s",
                year,
                settings.vote_year,
            )
        return settings.vote_year


def _reject_query_dsl(query: Optional[str]) -> None:
    """非空(且非 "NONE")→ 抛「高级搜索暂未实现」；经 map_app_errors 成为可辨识错误。

    前端的高级搜索 DSL(如 ``chars:["x"]``)本轮未实现；静默忽略并返回未过滤
    的全量排名，会让用户误以为看到的是筛选后的结果——这是要明确避免的失败
    模式，所以非空 query 一律报错，而不是退化为"当作没传"。
    """
    if query and query != "NONE":
        raise ValidationError(
            "ADVANCED_SEARCH_NOT_IMPLEMENTED",
            details=501,
            human_readable_message="高级搜索暂未实现",
        )


def _trend_items(raw: list[dict]) -> list[VotingTrendItem]:
    return [VotingTrendItem(hrs=t["hrs"], cnt=t["cnt"]) for t in raw]


def _ranking_global_from_dict(g: dict) -> RankingGlobal:
    return RankingGlobal(
        total_unique_items=g["total_unique_items"],
        total_first=g["total_first"],
        total_votes=g["total_votes"],
        average_votes_per_item=g["average_votes_per_item"],
        median_votes_per_item=g["median_votes_per_item"],
    )


def _ranking_entry_from_dict(e: dict) -> RankingEntry:
    """compute_ranking() 产出的单条 dict → RankingEntry（34 个字段全部必填）。

    rank_last_*/vote_count_last_*/first_vote_count_last_*（0）与
    first_vote_percentage_last_*/vote_percentage_last_*（0.0）是上届对比字段，
    本轮 compute 尚未提供历史数据源，按 brief 要求固定置零/置空——不是遗漏。
    """
    male = e["male_vote_count"]
    female = e["female_vote_count"]
    return RankingEntry(
        rank=e["rank"][0]["rank"],
        rank_last_1=0,
        rank_last_2=0,
        display_rank=e["display_rank"],
        name=e["name"],
        vote_count=e["rank"][0]["vote_count"],
        vote_count_last_1=0,
        vote_count_last_2=0,
        first_vote_count=e["rank"][0]["favorite_vote_count"],
        first_vote_count_last_1=0,
        first_vote_count_last_2=0,
        first_vote_percentage=e["favorite_percentage"],
        first_vote_percentage_last_1=0.0,
        first_vote_percentage_last_2=0.0,
        first_vote_count_weighted=e["favorite_vote_count_weighted"],
        character_type=e["type"],
        character_origin=e["origin"],
        first_appearance=e["first_appearance"],
        album=e["album"] or None,
        name_jpn=e["name_jp"],
        vote_percentage=e["rank"][0]["vote_percentage"],
        vote_percentage_last_1=0.0,
        vote_percentage_last_2=0.0,
        first_percentage=e["favorite_percentage_of_all"],
        male_vote_count=male["vote_count"],
        male_percentage_per_char=male["percentage_per_char"],
        male_percentage_per_total=male["percentage_per_total"],
        female_vote_count=female["vote_count"],
        female_percentage_per_char=female["percentage_per_char"],
        female_percentage_per_total=female["percentage_per_total"],
        trend=_trend_items(e["trend"]),
        trend_first=_trend_items(e["trend_first"]),
        reasons=e["reasons"],
        num_reasons=e["reasons_count"],
    )


def _cp_ranking_entry_from_dict(e: dict, char_whitelist: Whitelist) -> CPRankingEntry:
    """compute_cp_ranking() 产出的单条 dict → CPRankingEntry。

    CP 成员是角色 id（id_a/id_b/id_c），前端 CPItem 要的是人名 → 用角色白名单
    ``name_of()`` 转换（CP 永远不查音乐白名单，两个白名单不可混用）。
    """
    male = e["male_vote_count"]
    female = e["female_vote_count"]
    return CPRankingEntry(
        rank=e["rank"][0]["rank"],
        display_rank=e["display_rank"],
        cp=CPItem(
            a=char_whitelist.name_of(e["id_a"]),
            b=char_whitelist.name_of(e["id_b"]),
            c=char_whitelist.name_of(e["id_c"]) if e["id_c"] else None,
        ),
        a_active=e["active_a"],
        b_active=e["active_b"],
        c_active=e["active_c"],
        none_active=e["active_none"],
        vote_count=e["rank"][0]["vote_count"],
        first_vote_count=e["rank"][0]["favorite_vote_count"],
        first_vote_percentage=e["favorite_percentage"],
        first_vote_count_weighted=e["favorite_vote_count_weighted"],
        vote_percentage=e["rank"][0]["vote_percentage"],
        first_percentage=e["favorite_percentage_of_all"],
        male_vote_count=male["vote_count"],
        male_percentage_per_char=male["percentage_per_char"],
        male_percentage_per_total=male["percentage_per_total"],
        female_vote_count=female["vote_count"],
        female_percentage_per_char=female["percentage_per_char"],
        female_percentage_per_total=female["percentage_per_total"],
        trend=_trend_items(e["trend"]),
        trend_first=_trend_items(e["trend_first"]),
        reasons=e["reasons"],
        num_reasons=e["reasons_count"],
    )


async def _query_character_or_music_ranking(
    category: str, vote_year: Optional[int], query: Optional[str]
) -> CharacterOrMusicRanking:
    _reject_query_dsl(query)
    svc = await _get_result_service()
    settings = get_settings()
    year = await _resolve_vote_year(svc.result_dao, vote_year, settings)
    data = await svc.get_ranking(
        RankingQuery(category=category, vote_year=year, names=[])
    )
    return CharacterOrMusicRanking(
        entries=[_ranking_entry_from_dict(e) for e in data["rankings"]],
        global_=_ranking_global_from_dict(data["global"]),
    )


async def _query_cp_ranking(
    vote_year: Optional[int], query: Optional[str]
) -> CPRanking:
    _reject_query_dsl(query)
    svc = await _get_result_service()
    settings = get_settings()
    year = await _resolve_vote_year(svc.result_dao, vote_year, settings)
    data = await svc.get_ranking(RankingQuery(category="cp", vote_year=year, names=[]))
    char_whitelist = load_whitelist("character")
    return CPRanking(
        entries=[
            _cp_ranking_entry_from_dict(e, char_whitelist) for e in data["rankings"]
        ],
        global_=_ranking_global_from_dict(data["global"]),
    )


@strawberry.type
class ResultCompatQuery:
    """前端(旧 Rust gateway)排名查询契约桥。"""

    @strawberry.field
    async def query_character_ranking(
        self,
        # vote_start 前端必传，但排名计算不依赖它（compute 管线用
        # settings.vote_start_iso 自行确定统计窗口）；此参数仅为 schema 兼容
        # 保留，不参与计算。
        vote_start: Optional[DateTimeUtc] = None,
        vote_year: Optional[int] = None,
        # 高级搜索 DSL：见 _reject_query_dsl。
        query: Optional[str] = None,
    ) -> CharacterOrMusicRanking:
        async with map_app_errors(service=_SERVICE):
            return await _query_character_or_music_ranking(
                "character", vote_year, query
            )
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.field
    async def query_music_ranking(
        self,
        vote_start: Optional[DateTimeUtc] = None,
        vote_year: Optional[int] = None,
        query: Optional[str] = None,
    ) -> CharacterOrMusicRanking:
        async with map_app_errors(service=_SERVICE):
            return await _query_character_or_music_ranking("music", vote_year, query)
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.field(name="queryCPRanking")
    async def query_cp_ranking(
        self,
        vote_start: Optional[DateTimeUtc] = None,
        vote_year: Optional[int] = None,
        query: Optional[str] = None,
    ) -> CPRanking:
        async with map_app_errors(service=_SERVICE):
            return await _query_cp_ranking(vote_year, query)
        raise RuntimeError("unreachable")  # pragma: no cover
