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
from src.api.graphql.resolvers.result import _get_result_service
from src.api.graphql.types import (
    CachedQuestionAnswerItem,
    CachedQuestionItem,
    CharacterOrMusicRanking,
    CompletionRate,
    CompletionRateItem,
    CPItem,
    CPRanking,
    CPRankingEntry,
    DateTimeUtc,
    QueryQuestionnaireResponse,
    RankingEntry,
    RankingGlobal,
    ResultGlobalStats,
    Trends,
    VotingTrendItem,
)
from src.apps.result.dao import EntityNotFoundError, ResultDAO, ResultNotComputedError
from src.apps.result.schemas import (
    CompletionRatesQuery,
    GlobalStatsQuery,
    QuestionnaireQuery,
    RankingQuery,
)
from src.apps.result.service import ResultService
from src.apps.result.whitelist import Whitelist, load_whitelist
from src.common.config import Settings
from src.common.exceptions import NotFoundError, ValidationError

logger = logging.getLogger(__name__)

_SERVICE = "result"  # extensions.service，对齐 brief 要求的 map_app_errors(service="result")

# _get_result_service 复用 resolvers/result.py 的现成实现(同一份 get_redis/
# get_settings 接线)，不在本模块重复定义——两份拷贝迟早会漂移。


# ── 公共助手(本任务建立，后续任务复用) ─────────────────────────────


async def _resolve_vote_year(
    dao: ResultDAO, requested: Optional[int], settings: Settings
) -> int:
    """该年有数据就用，否则回落 settings.vote_year 并记一条日志。

    前端硬编码 ``voteYear: 11``（旧契约遗留），但数据实际落在
    ``settings.vote_year`` 下。用 ``get_global_stats`` 探测该年是否已跑过
    compute（每年计算一次、与 category 无关，天然是"该年是否有数据"的探针），
    没有数据才回落——不能仅因为前端传了旧的 legacy 年份就整体 503。

    探针 key（``result:{year}:global_stats``）与实际排名读取的 key
    （``result:{year}:{cat}:ranking``）是两个不同的 Redis key；两者在
    ``ComputeService.compute_all`` 里由同一个 pipeline 一次性写入，正常情况下
    永远同生共死，此处才能把前者当后者的存在性代理。如果未来出现"pipeline
    写到一半失败"这类部分写入场景，两者可能不一致——届时这个探针不再可靠，
    需要重新评估。
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
            human_readable_message="高级搜索暂未实现",
        )


async def _map_not_computed_error(coro):
    """await coro；``ResultNotComputedError`` → 稳定、可辨识、不泄内部细节的错误。

    ``ResultNotComputedError`` 的 message 是
    ``f"No computed data at Redis key: {key}"``（dao.py），逐年不同、且直接
    暴露内部 Redis key 布局；``map_app_errors`` 会把 ``exc.message`` 原样当
    ``error_kind`` 透传给调用方，这既不稳定（前端没法匹配一个包含年份的字符串）
    也违反 errors.py 自己的契约("响应只暴露稳定的 INTERNAL_ERROR，不向调用方
    透出内部细节")。这里改写成稳定 kind + 用户文案，不透传原始 message。

    这是"该年确实没算过"的真实兜底路径——``_resolve_vote_year`` 回落到
    ``settings.vote_year`` 之后，如果连这一年都没算过（全新部署的真实状态），
    这里同样会触发。被 ``_fetch_ranking``（排名）以及 Task 6 新增的
    global stats / completion rates 取数复用，避免每处重写一遍 try/except。
    """
    try:
        return await coro
    except ResultNotComputedError as exc:
        raise ValidationError(
            "RESULT_NOT_COMPUTED",
            human_readable_message="投票结果尚未生成，请稍后再试",
        ) from exc


async def _fetch_ranking(svc: ResultService, category: str, year: int) -> dict:
    """svc.get_ranking 包一层，见 `_map_not_computed_error` 的转写规则。"""
    return await _map_not_computed_error(
        svc.get_ranking(RankingQuery(category=category, vote_year=year, names=[]))
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

    移除条件：compute.py 里 ``compute_ranking``/``compute_cp_ranking`` 已经有
    "``historical`` 非空时在 ``rank[1]``/``rank[2]`` 里塞历史快照"的活路径
    （目前 compute_service.py 固定传 ``{}``）；一旦上届对比（历史 backlog 项）
    落地、``compute_service`` 开始传非空 ``historical``，这里必须同步改成从
    ``rank[1]``/``rank[2]`` 取值，否则会用硬编码 0 悄悄盖掉真实历史数据。
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
    # settings 直接取 dao 上已持有的那份(同一个 get_settings() 单例)，不重复调用。
    year = await _resolve_vote_year(svc.result_dao, vote_year, svc.result_dao.settings)
    data = await _fetch_ranking(svc, category, year)
    return CharacterOrMusicRanking(
        entries=[_ranking_entry_from_dict(e) for e in data["rankings"]],
        global_=_ranking_global_from_dict(data["global"]),
    )


async def _query_cp_ranking(
    vote_year: Optional[int], query: Optional[str]
) -> CPRanking:
    _reject_query_dsl(query)
    svc = await _get_result_service()
    year = await _resolve_vote_year(svc.result_dao, vote_year, svc.result_dao.settings)
    data = await _fetch_ranking(svc, "cp", year)
    char_whitelist = load_whitelist("character")
    return CPRanking(
        entries=[
            _cp_ranking_entry_from_dict(e, char_whitelist) for e in data["rankings"]
        ],
        global_=_ranking_global_from_dict(data["global"]),
    )


# ── 单条查询(按唯一序号) ──────────────────────────────────────────


def _find_by_ordinal(rankings: list[dict], rank: int) -> dict:
    """按唯一序号 ``e["rank"][0]["rank"]`` 匹配——不用会并列的 ``display_rank``
    （并列名次时多个条目共享同一个 display_rank，无法用它取到确定的单条）。

    找不到 → ``NotFoundError("ENTITY_NOT_FOUND")``，经 map_app_errors 变成
    可辨识的 404 类错误；不是 ``INTERNAL_ERROR``，也不能把 ``None`` 悄悄传给
    RankingEntry/CPRankingEntry 这类字段全部必填、无默认值的 GraphQL 类型。
    """
    for e in rankings:
        if e["rank"][0]["rank"] == rank:
            return e
    raise NotFoundError(
        "ENTITY_NOT_FOUND", human_readable_message="未找到该排名条目"
    )


async def _query_character_or_music_single(
    category: str, rank: int, vote_year: Optional[int], query: Optional[str]
) -> RankingEntry:
    _reject_query_dsl(query)
    svc = await _get_result_service()
    year = await _resolve_vote_year(svc.result_dao, vote_year, svc.result_dao.settings)
    data = await _fetch_ranking(svc, category, year)
    return _ranking_entry_from_dict(_find_by_ordinal(data["rankings"], rank))


async def _query_cp_single(
    rank: int, vote_year: Optional[int], query: Optional[str]
) -> CPRankingEntry:
    _reject_query_dsl(query)
    svc = await _get_result_service()
    year = await _resolve_vote_year(svc.result_dao, vote_year, svc.result_dao.settings)
    data = await _fetch_ranking(svc, "cp", year)
    char_whitelist = load_whitelist("character")
    return _cp_ranking_entry_from_dict(
        _find_by_ordinal(data["rankings"], rank), char_whitelist
    )


# ── 趋势(按 name 列表，逐个取) ───────────────────────────────────────


async def _query_character_or_music_trend(
    category: str, names: list[str], vote_year: Optional[int]
) -> list[Trends]:
    """逐个 name 取 ``ResultDAO.get_trend``；顺序与入参 ``names`` 一致。

    单个 name 不在该年榜单里(``EntityNotFoundError``) → 该位置返回空
    ``Trends``(不报错，不影响其余 name 的结果)；但整个分类都没算过
    (``ResultNotComputedError``，理论上不该发生——见 `_resolve_vote_year`
    的探针注释)时仍要转写成稳定的 ``RESULT_NOT_COMPUTED``，不能被"缺失当空"
    的规则悄悄吞掉，否则前端会把"整体没算过"误读成"这些角色都没人投"。这条
    转写复用 `_map_not_computed_error`（与 `_fetch_ranking`/全局统计/完成率/
    问卷同一处逻辑），只在外层单独捕获 `EntityNotFoundError`（它不会被
    `_map_not_computed_error` 拦下，会正常穿透到这里）。
    """
    svc = await _get_result_service()
    year = await _resolve_vote_year(svc.result_dao, vote_year, svc.result_dao.settings)
    trends: list[Trends] = []
    for name in names:
        try:
            raw = await _map_not_computed_error(
                svc.result_dao.get_trend(category, name, year)
            )
        except EntityNotFoundError:
            trends.append(Trends(trend=[], trend_first=[]))
            continue
        trends.append(
            Trends(
                trend=_trend_items(raw["trend"]),
                trend_first=_trend_items(raw["trend_first"]),
            )
        )
    return trends


# ── 全局统计 / 完成率 ─────────────────────────────────────────────


async def _query_global_stats(
    vote_year: Optional[int], query: Optional[str]
) -> ResultGlobalStats:
    _reject_query_dsl(query)
    svc = await _get_result_service()
    year = await _resolve_vote_year(svc.result_dao, vote_year, svc.result_dao.settings)
    data = await _map_not_computed_error(
        svc.get_global_stats(GlobalStatsQuery(vote_year=year))
    )
    # vote_year 是解析后的年份(_resolve_vote_year 的返回值)，不是前端原始传参——
    # compute_global_stats 本身不产出这个字段，契约层补上。
    return ResultGlobalStats(
        vote_year=year,
        num_vote=data["num_vote"],
        num_char=data["num_char"],
        num_music=data["num_music"],
        num_cp=data["num_cp"],
        num_doujin=data["num_doujin"],
        num_male=data["num_male"],
        num_female=data["num_female"],
    )


async def _query_completion_rates(
    vote_year: Optional[int], query: Optional[str]
) -> CompletionRate:
    _reject_query_dsl(query)
    svc = await _get_result_service()
    year = await _resolve_vote_year(svc.result_dao, vote_year, svc.result_dao.settings)
    data = await _map_not_computed_error(
        svc.get_completion_rates(CompletionRatesQuery(vote_year=year))
    )
    return CompletionRate(
        vote_year=year,
        items=[
            CompletionRateItem(
                name=category,
                rate=d["rate"],
                num_complete=d["num_complete"],
                total=d["total"],
            )
            for category, d in data.items()
        ],
    )


# ── 问卷 ──────────────────────────────────────────────────────────


def _strip_question_prefix(question_id: str) -> str:
    """接受两种写法：带可选前导 ``q``(前端线上格式 ``q11011``)或裸数字码
    ``11011``；库里按裸码存(``paper:{code}``)，两种写法都落到同一个 key。
    """
    return question_id[1:] if question_id.startswith("q") else question_id


async def _query_questionnaire_entries(
    question_ids: list[str], vote_year: Optional[int], query: Optional[str]
) -> QueryQuestionnaireResponse:
    """按 ``question_ids`` 顺序逐个取问卷统计；缺的题跳过，不报错。

    ``ResultDAO.get_questionnaire`` 对"这道题没数据"和"整个 paper/年份从未
    计算过"抛的是**同一个** ``ResultNotComputedError``，无法只凭异常类型区分——
    如果直接在逐题循环里 catch-and-continue，一个全新部署（该年从未跑过
    compute）会让每个 id 都触发这个分支，最终得到一个"看起来成功但其实什么
    都没算过"的 ``{entries: []}``，而不是可辨识的 ``RESULT_NOT_COMPUTED``。
    所以进入逐题循环前，先对 `get_global_stats` 做一次 `_map_not_computed_error`
    探测（与 `queryQuestionnaireTrend` 用的是同一套探测）：这一步过了，
    "该年确实算过"这个前提就成立，per-id 的 ``ResultNotComputedError`` 才能
    被安全地解读为"这道具体题没数据"而不是"整体没算过"，跳过才是正确行为。
    """
    _reject_query_dsl(query)
    svc = await _get_result_service()
    year = await _resolve_vote_year(svc.result_dao, vote_year, svc.result_dao.settings)
    await _map_not_computed_error(
        svc.get_global_stats(GlobalStatsQuery(vote_year=year))
    )
    entries: list[CachedQuestionItem] = []
    for question_id in question_ids:
        code = _strip_question_prefix(question_id)
        try:
            raw = await svc.get_questionnaire(
                QuestionnaireQuery(question_id=code, vote_year=year)
            )
        except ResultNotComputedError:
            continue
        entries.append(
            CachedQuestionItem(
                question_id="q" + code,
                answers_cat=[
                    CachedQuestionAnswerItem(
                        aid=a["aid"],
                        total_votes=a["count"],
                        male_votes=a["male_votes"],
                        female_votes=a["female_votes"],
                    )
                    for a in raw["answers_cat"]
                ],
                answers_str=raw["answers_str"],
                total_answers=raw["total"],
                total_male=raw["total_male"],
                total_female=raw["total_female"],
            )
        )
    return QueryQuestionnaireResponse(entries=entries)


async def _query_questionnaire_trend_entries(
    question_ids: list[str], vote_year: Optional[int], query: Optional[str]
) -> list[Trends]:
    """按 ``question_ids`` 顺序逐个返回**空** ``Trends``——问卷没有真正的时间
    维度（``compute_paper_results`` 完全不产出按小时切片的数据），详见
    ``ResultCompatQuery.query_questionnaire_trend`` 的字段 docstring。

    仍对该年是否算过做一次 ``RESULT_NOT_COMPUTED`` 探测（与其余 8 个查询
    一致），这样"该年确实一次都没算过"和"该年算过、只是这项指标退化成空"
    是两种可辨识的状态，不会被"反正也是空"的降级逻辑悄悄合并掉。
    """
    _reject_query_dsl(query)
    svc = await _get_result_service()
    year = await _resolve_vote_year(svc.result_dao, vote_year, svc.result_dao.settings)
    await _map_not_computed_error(
        svc.get_global_stats(GlobalStatsQuery(vote_year=year))
    )
    return [Trends(trend=[], trend_first=[]) for _ in question_ids]


@strawberry.type
class ResultCompatQuery:
    """前端(旧 Rust gateway)result 契约桥：排名/单条/趋势/统计/问卷。"""

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
        # 不可达：map_app_errors 出错必 re-raise，成功则已在 with 块内 return；
        # 这行只为满足类型检查器"函数需要显式返回值"的要求。
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
        # 不可达：map_app_errors 出错必 re-raise，成功则已在 with 块内 return；
        # 这行只为满足类型检查器"函数需要显式返回值"的要求。
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
        # 不可达：map_app_errors 出错必 re-raise，成功则已在 with 块内 return；
        # 这行只为满足类型检查器"函数需要显式返回值"的要求。
        raise RuntimeError("unreachable")  # pragma: no cover

    # ── 单条查询(按唯一序号 rank，不是会并列的 displayRank) ──────────

    @strawberry.field
    async def query_character_single(
        self,
        rank: int,
        vote_start: Optional[DateTimeUtc] = None,
        vote_year: Optional[int] = None,
        query: Optional[str] = None,
    ) -> RankingEntry:
        async with map_app_errors(service=_SERVICE):
            return await _query_character_or_music_single(
                "character", rank, vote_year, query
            )
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.field
    async def query_music_single(
        self,
        rank: int,
        vote_start: Optional[DateTimeUtc] = None,
        vote_year: Optional[int] = None,
        query: Optional[str] = None,
    ) -> RankingEntry:
        async with map_app_errors(service=_SERVICE):
            return await _query_character_or_music_single(
                "music", rank, vote_year, query
            )
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.field(name="queryCPSingle")
    async def query_cp_single(
        self,
        rank: int,
        vote_start: Optional[DateTimeUtc] = None,
        vote_year: Optional[int] = None,
        query: Optional[str] = None,
    ) -> CPRankingEntry:
        async with map_app_errors(service=_SERVICE):
            return await _query_cp_single(rank, vote_year, query)
        raise RuntimeError("unreachable")  # pragma: no cover

    # ── 趋势(按 name 列表批量取，顺序与入参一致) ──────────────────────

    @strawberry.field
    async def query_character_trend(
        self,
        names: list[str],
        vote_start: Optional[DateTimeUtc] = None,
        vote_year: Optional[int] = None,
    ) -> list[Trends]:
        async with map_app_errors(service=_SERVICE):
            return await _query_character_or_music_trend(
                "character", names, vote_year
            )
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.field
    async def query_music_trend(
        self,
        names: list[str],
        vote_start: Optional[DateTimeUtc] = None,
        vote_year: Optional[int] = None,
    ) -> list[Trends]:
        async with map_app_errors(service=_SERVICE):
            return await _query_character_or_music_trend("music", names, vote_year)
        raise RuntimeError("unreachable")  # pragma: no cover

    # ── 全局统计 / 完成率 ─────────────────────────────────────────────

    @strawberry.field
    async def query_global_stats(
        self,
        vote_start: Optional[DateTimeUtc] = None,
        vote_year: Optional[int] = None,
        query: Optional[str] = None,
    ) -> ResultGlobalStats:
        async with map_app_errors(service=_SERVICE):
            return await _query_global_stats(vote_year, query)
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.field
    async def query_completion_rates(
        self,
        vote_start: Optional[DateTimeUtc] = None,
        vote_year: Optional[int] = None,
        query: Optional[str] = None,
    ) -> CompletionRate:
        async with map_app_errors(service=_SERVICE):
            return await _query_completion_rates(vote_year, query)
        raise RuntimeError("unreachable")  # pragma: no cover

    # ── 问卷 ──────────────────────────────────────────────────────────

    @strawberry.field
    async def query_questionnaire(
        self,
        questions_of_interest: list[str],
        vote_start: Optional[DateTimeUtc] = None,
        vote_year: Optional[int] = None,
        query: Optional[str] = None,
    ) -> QueryQuestionnaireResponse:
        async with map_app_errors(service=_SERVICE):
            return await _query_questionnaire_entries(
                questions_of_interest, vote_year, query
            )
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.field
    async def query_questionnaire_trend(
        self,
        question_ids: list[str],
        vote_start: Optional[DateTimeUtc] = None,
        vote_year: Optional[int] = None,
        query: Optional[str] = None,
    ) -> list[Trends]:
        """按 ``questionIds`` 顺序返回**空** trend 序列——后端没有问卷时间维度。

        ``compute_paper_results`` 完全忽略 ``vote_start``/``total_hours``，
        不产出任何按小时切片的数据（问卷 trend 存储改造/C3 未落地，见设计稿
        §七「已知限制」第 3 条），所以无法返回真实的时间序列。

        真实前端（`QuestionnaireDetail.vue`）与旧 Rust 网关
        （`gateway/src/schema.rs`）都按 ``[Trends!]!`` 消费这个字段
        （`entries[0].trend`/`.trendFirst`）——**返回形状错误**会让 schema
        校验直接失败、整个"调查问卷"页面挂掉；本字段返回**形状正确、内容为空**
        的 ``Trends`` 列表（长度与 ``questionIds`` 一致，顺序保留），让页面
        能渲染出一个空图表而不是整体报错。

        （早期实现曾把这里当 ``queryQuestionnaire`` 的别名、返回
        ``QueryQuestionnaireResponse``——这是对 task-6-brief.md/设计稿字面
        要求的忠实执行，但两份规划文档在这一点上判断有误：它们从"后端现有
        ``get_questionnaire_trend`` 是别名"反推字段契约，而不是从真实前端
        消费方反推；已更正。）

        移除条件：真实问卷趋势需要 append-only 的提交历史存储（BACKLOG 里与
        角色/音乐 trend 共用的同一项存储改造）落地后，才能在这里返回真实的
        按小时序列，届时应删除这条"恒为空"的退化逻辑。
        """
        async with map_app_errors(service=_SERVICE):
            return await _query_questionnaire_trend_entries(
                question_ids, vote_year, query
            )
        raise RuntimeError("unreachable")  # pragma: no cover
