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

logger = logging.getLogger(__name__)

ADV_TTL_SECONDS = 24 * 3600
_LOCK_TTL_MS = 30_000
_WAIT_PROBES = 25
_WAIT_INTERVAL_SECONDS = 0.2

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
    map_app_errors 出口)。单飞锁防击穿:等锁超时兜底自己算——重复计算
    只浪费几百毫秒,不出错。
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
    if got_lock:
        # 双检:上面的 exists(marker) 探测与这里的 SET NX 之间可能有别的协程
        # 已经算完并写入 marker——拿到锁不代表还需要真去算一次。
        if await redis.exists(marker):
            await redis.eval(_UNLOCK_SCRIPT, 1, lock_key, token)
            return infix
    else:
        for _ in range(_WAIT_PROBES):
            await asyncio.sleep(_WAIT_INTERVAL_SECONDS)
            if await redis.exists(marker):
                return infix
        logger.warning(
            "advanced search: lock wait timed out, computing anyway "
            "(year=%d fp=%s)", vote_year, fp,
        )
    try:
        await _compute_filtered(redis, settings, vote_year, ast, infix)
    finally:
        if got_lock:
            await redis.eval(_UNLOCK_SCRIPT, 1, lock_key, token)
    return infix


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

    char_ranking, char_global = compute_ranking(
        char_votes, char_wl, segment_map, {}, vote_start, total_hours)
    music_ranking, music_global = compute_ranking(
        music_votes, music_wl, segment_map, {}, vote_start, total_hours)
    cp_ranking, cp_global = compute_cp_ranking(
        cp_votes, char_wl, segment_map, {}, vote_start, total_hours)
    all_voters = (
        {v[0] for v in char_votes} | {v[0] for v in music_votes}
        | {v[0] for v in cp_votes} | {v[0] for v in q_votes}
    )
    global_stats = compute_global_stats(
        char_votes, music_votes, cp_votes, q_votes, segment_map)
    completion_rates = compute_completion_rates(
        char_votes, music_votes, cp_votes, q_votes, all_voters)
    paper_results = compute_paper_results(q_votes, segment_map)

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
