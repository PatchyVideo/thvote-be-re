"""高级搜索服务:缓存查找/单飞锁/子集整包重算(设计稿 §三/§六/§七)。

缓存 key 镜像预计算布局,多一段 infix:
    result:{year}:adv:{快照版本}:{指纹}:chars:ranking  (TTL 24h)
快照版本由 compute_all 写入(定时重算后翻转,旧缓存自然失效)。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis

from src.apps.result.advanced_search.dsl import Node, fingerprint, parse_query
from src.apps.result.advanced_search.subset import (
    build_facts,
    evaluate_subset,
    resolve_names,
)
from src.apps.result.compute import (
    build_segment_map,
    compute_completion_rates,
    compute_cp_ranking,
    compute_global_stats,
    compute_paper_results,
    compute_ranking,
)
from src.apps.result.compute_dao import ComputeDAO
from src.apps.result.whitelist import load_whitelist_db
from src.common.config import Settings
from src.common.database import get_session_maker
from src.common.exceptions import ValidationError
from src.common.middleware.client_ip import client_ip_var

logger = logging.getLogger(__name__)

ADV_TTL_SECONDS = 24 * 3600
_LOCK_TTL_MS = 30_000
# 等锁上限:等待跟随锁存活(锁没了就提前接手),此值只兜"marker 与锁双双
# 异常缺失"的极端情况;量级须覆盖真实重算耗时(测试机 4 万行问卷 ~8s,
# 真实届数据更大),B-060 由固定 5s(25×200ms)改为 60s。
_WAIT_MAX_SECONDS = 60.0
_WAIT_INTERVAL_SECONDS = 0.2

# miss 重算限频(B-060 双层):GraphQL 入口本身无限流,且 `q<code>=<opt>`
# 原子的 code 不经白名单校验(B-054 前刻意保留),指纹空间无界——轮换指纹可
# 绕过按指纹隔离的单飞锁。每次真实重算 = 4 张全表 SELECT + 纯 CPU 聚合
# (测试机 4 万行问卷实测 ~8s,阻塞事件循环)。
# - per-IP 层(10/min):单个来源刷不同指纹的硬上限,正常用户切页远用不满;
# - 全局层(30/min):多源分布式刷量的兜底,同时是事件循环占用的总闸。
# 只有**真正执行重算**的调用者扣预算:缓存命中、等锁后从缓存拿到结果的
# 路径都不扣(扣费点见 ensure_filtered_results 内两处 _check_miss_budget)。
ADV_MISS_LIMIT_PER_MINUTE = 30
ADV_MISS_LIMIT_PER_IP_PER_MINUTE = 10
_MISS_BUDGET_WINDOW_SECONDS = 60


def miss_budget_key(vote_year: int) -> str:
    return f"adv_miss_budget:{vote_year}"


def miss_budget_ip_key(vote_year: int, client_ip: str) -> str:
    return f"adv_miss_budget:{vote_year}:ip:{client_ip}"


async def _incr_window(redis: aioredis.Redis, key: str) -> int:
    """固定窗口计数:INCR,首个计数设置过期(不滚动续期)。"""
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, _MISS_BUDGET_WINDOW_SECONDS)
    return int(count)


async def _check_miss_budget(
    redis: aioredis.Redis, vote_year: int, client_ip: str | None
) -> None:
    """miss 重算限频(per-IP + 全局双层),超限抛可辨识错误。

    只在**即将真正执行重算**时调用(持锁双检未命中后 / 等锁退出接手后);
    缓存命中与等锁后拿到缓存的路径都不经过这里。client_ip 为 None(非 HTTP
    上下文:测试直调、脚本)时跳过 per-IP 层,只走全局层。
    """
    if client_ip:
        ip_count = await _incr_window(redis, miss_budget_ip_key(vote_year, client_ip))
        if ip_count > ADV_MISS_LIMIT_PER_IP_PER_MINUTE:
            raise ValidationError(
                "ADVANCED_SEARCH_BUSY",
                human_readable_message="高级搜索请求过于频繁,请稍后再试",
            )
    count = await _incr_window(redis, miss_budget_key(vote_year))
    if count > ADV_MISS_LIMIT_PER_MINUTE:
        raise ValidationError(
            "ADVANCED_SEARCH_BUSY",
            human_readable_message="高级搜索请求过于频繁,请稍后再试",
        )

# Compare-and-delete:只删自己持有的锁(value 匹配自己的 token 才删),防止锁在
# 计算超时自然过期后被别的持锁者(第二个抢到同一 lock_key 的调用者)误删。
_UNLOCK_SCRIPT = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then "
    "return redis.call('del', KEYS[1]) else return 0 end"
)


def snapshot_version_key(vote_year: int) -> str:
    return f"result:{vote_year}:snapshot_version"


async def ensure_filtered_results(
    redis: aioredis.Redis, settings: Settings, vote_year: int, query_str: str
) -> str:
    """确保该约束的筛选结果在缓存;返回 ResultDAO 的 key infix。

    解析/限制/未知名字错误直接向上抛(可辨识 ValidationError,契约层经
    map_app_errors 出口)。单飞锁防击穿:等锁者跟随锁存活轮询,锁消失或
    等待超上限才接手自己算(重复计算幂等,只是浪费)。**只有真正执行重算
    的调用者扣 miss 预算**(per-IP ``ADV_MISS_LIMIT_PER_IP_PER_MINUTE`` +
    全局 ``ADV_MISS_LIMIT_PER_MINUTE`` 双层,超限抛 ``ADVANCED_SEARCH_BUSY``);
    缓存命中与等锁后从缓存拿到结果的路径不扣。client IP 取自
    ``client_ip_var``(HTTP 请求经 ClientIPMiddleware 注入,非 HTTP 上下文
    为 None → 只走全局层)。
    """
    ast = parse_query(query_str)
    fp = fingerprint(ast)
    version = await redis.get(snapshot_version_key(vote_year)) or "0"
    if isinstance(version, bytes):
        version = version.decode()
    infix = f"adv:{version}:{fp}"
    marker = f"result:{vote_year}:{infix}:global_stats"
    if await redis.exists(marker):
        return infix

    lock_key = f"adv_lock:{vote_year}:{fp}"
    token = uuid.uuid4().hex
    got_lock = await redis.set(lock_key, token, nx=True, px=_LOCK_TTL_MS)
    try:
        if got_lock:
            # 双检:上面的 exists(marker) 探测与 SET NX 之间可能有别的协程
            # 已经算完并写入 marker——拿到锁不代表还需要真去算一次。
            if await redis.exists(marker):
                return infix
        else:
            # 等锁:跟随锁存活轮询,而非固定短预算(B-060)。真实重算耗时
            # 随数据量增长(测试机 4 万行问卷 ~8s),固定 5s 会让所有等锁者
            # 在最贵的场景集体转入重复计算;上限 _WAIT_MAX_SECONDS 只防
            # marker/锁双双异常缺失时的无限等待。
            waited = 0.0
            while waited < _WAIT_MAX_SECONDS:
                await asyncio.sleep(_WAIT_INTERVAL_SECONDS)
                waited += _WAIT_INTERVAL_SECONDS
                if await redis.exists(marker):
                    return infix
                if not await redis.exists(lock_key):
                    # 持锁者结束却没写 marker(计算失败/被限频/进程死亡)
                    # → 不再空等,自己接手
                    break
            else:
                logger.warning(
                    "advanced search: lock wait exhausted %.0fs, computing "
                    "anyway (year=%d fp=%s)", _WAIT_MAX_SECONDS, vote_year, fp,
                )
        # 走到这里 = 本调用者真的要执行重算 → 此刻才扣 miss 预算
        # (per-IP + 全局双层;等锁后从缓存拿到结果的路径在上面已 return)。
        await _check_miss_budget(redis, vote_year, client_ip_var.get())
        await _compute_filtered(redis, settings, vote_year, ast, infix)
        return infix
    finally:
        if got_lock:
            await redis.eval(_UNLOCK_SCRIPT, 1, lock_key, token)


async def _compute_filtered(
    redis: aioredis.Redis,
    settings: Settings,
    vote_year: int,
    ast: Node,
    infix: str,
) -> None:
    """载票 → 圈子集 → 过滤后复用 compute 纯函数整包重算 → 写缓存。

    与 ComputeService.compute_all 的差异只有:输入按子集过滤、不算
    covote(需求无消费方)、写 key 带 infix 和 TTL。窗口参数与
    compute_all 同源(settings),子集 trend 分桶口径一致。
    """
    s = settings
    vote_start = datetime.fromisoformat(s.vote_start_iso.replace("Z", "+00:00"))
    vote_end = datetime.fromisoformat(s.vote_end_iso.replace("Z", "+00:00"))
    if vote_start.tzinfo is None:
        vote_start = vote_start.replace(tzinfo=timezone.utc)
    if vote_end.tzinfo is None:
        vote_end = vote_end.replace(tzinfo=timezone.utc)
    total_hours = max(1, int((vote_end - vote_start).total_seconds() / 3600))

    session_maker = get_session_maker()
    async with session_maker() as session:
        # 名字解析先于载票:未知名字应该零成本失败(不背四张全表 load_*_votes
        # 的代价)——ADVANCED_SEARCH_UNKNOWN_NAME 是这里唯一的抛出点。
        char_wl = await load_whitelist_db(session, "character", vote_year)
        music_wl = await load_whitelist_db(session, "music", vote_year)
        resolved = resolve_names(ast, char_wl, music_wl)

        dao = ComputeDAO(session)
        char_votes = await dao.load_char_votes()
        music_votes = await dao.load_music_votes()
        cp_votes = await dao.load_cp_votes()
        q_votes = await dao.load_questionnaire_votes(vote_year)
        # 全提交历史:子集 trend 也走真实净增量(与 compute_all 同口径)。
        char_history = await dao.load_char_history()
        music_history = await dao.load_music_history()
        cp_history = await dao.load_cp_history()
        q_history = await dao.load_questionnaire_history(vote_year)

    facts = build_facts(char_votes, music_votes, cp_votes, q_votes, char_wl, music_wl)
    subset = evaluate_subset(ast, facts, resolved)
    logger.info(
        "advanced search compute: year=%d fp=%s subset=%d/%d",
        vote_year, infix.rsplit(":", 1)[-1], len(subset), len(facts.all_vote_ids),
    )

    # segment_map 用全量问卷构建(查表只发生在子集内,设计稿 §六);
    # 其余输入全部过滤到子集。
    label_by_option = {
        s.gender_male_option_code: "male",
        s.gender_female_option_code: "female",
    }
    segment_map = build_segment_map(q_votes, s.gender_question_code, label_by_option)
    char_votes = [v for v in char_votes if v[0] in subset]
    music_votes = [v for v in music_votes if v[0] in subset]
    cp_votes = [v for v in cp_votes if v[0] in subset]
    q_votes = [v for v in q_votes if v[0] in subset]
    char_history = [h for h in char_history if h[0] in subset]
    music_history = [h for h in music_history if h[0] in subset]
    cp_history = [h for h in cp_history if h[0] in subset]
    q_history = [h for h in q_history if h[0] in subset]

    char_ranking, char_global = compute_ranking(
        char_votes, char_wl, segment_map, {}, vote_start, total_hours,
        history=char_history)
    music_ranking, music_global = compute_ranking(
        music_votes, music_wl, segment_map, {}, vote_start, total_hours,
        history=music_history)
    cp_ranking, cp_global = compute_cp_ranking(
        cp_votes, char_wl, segment_map, {}, vote_start, total_hours,
        history=cp_history)
    all_voters = (
        {v[0] for v in char_votes} | {v[0] for v in music_votes}
        | {v[0] for v in cp_votes} | {v[0] for v in q_votes}
    )
    global_stats = compute_global_stats(
        char_votes, music_votes, cp_votes, q_votes, segment_map)
    completion_rates = compute_completion_rates(
        char_votes, music_votes, cp_votes, q_votes, all_voters)
    paper_results = compute_paper_results(
        q_votes, segment_map, vote_start=vote_start, total_hours=total_hours,
        history=q_history)

    def key(*parts: str) -> str:
        return f"result:{vote_year}:{infix}:" + ":".join(parts)

    pipe = redis.pipeline()
    pipe.set(key("chars", "ranking"), json.dumps(char_ranking), ex=ADV_TTL_SECONDS)
    pipe.set(key("chars", "global"), json.dumps(char_global), ex=ADV_TTL_SECONDS)
    pipe.set(key("musics", "ranking"), json.dumps(music_ranking), ex=ADV_TTL_SECONDS)
    pipe.set(key("musics", "global"), json.dumps(music_global), ex=ADV_TTL_SECONDS)
    pipe.set(key("cps", "ranking"), json.dumps(cp_ranking), ex=ADV_TTL_SECONDS)
    pipe.set(key("cps", "global"), json.dumps(cp_global), ex=ADV_TTL_SECONDS)
    pipe.set(
        key("completion_rates"), json.dumps(completion_rates), ex=ADV_TTL_SECONDS)
    for qid, data in paper_results.items():
        pipe.set(key("paper", qid), json.dumps(data), ex=ADV_TTL_SECONDS)
    # global_stats 最后写:它是 ensure 的存在性探针(marker),
    # 必须等其余 section 全部就位后才可见。
    pipe.set(key("global_stats"), json.dumps(global_stats), ex=ADV_TTL_SECONDS)
    await pipe.execute()
