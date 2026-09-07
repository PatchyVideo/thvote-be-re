"""真实净增量 trend(B-050-后补2 Step 2)。

基于 append-only 提交历史(ComputeDAO.load_*_history)对每个选民的快照
序列做集合 diff:首快照全体实体 +1;后续快照新增 +1、消失 -1,落在该
快照时刻的小时桶。与 compute_ranking 的近似口径("最新提交时刻分桶")
不同,这里能真实反映改票造成的负增量——前端 Trends 契约本就按"每桶
净增量(可为负)"消费,由前端自行累计。

不变量:任一 key 全桶净增量之和 == 最终快照里该 key 的计数——前提是
调用方传入的 item_keys 过滤口径(白名单等)与榜单计数完全一致,且
history 的选民排除口径与榜单同源(_history_per_vote 保证)。
"""

from collections import defaultdict
from collections.abc import Callable, Hashable, Iterable
from datetime import datetime, timezone

_EMPTY: dict[str, list[dict]] = {"trend": [], "trend_first": []}


def net_delta_trends(
    history: list[tuple[str, datetime, int, list[dict]]],
    item_keys: Callable[[dict], Iterable[Hashable]],
    first_flag: Callable[[dict], bool],
    vote_start: datetime,
    total_hours: int,
) -> dict[Hashable, dict[str, list[dict]]]:
    """从全提交历史算每个 key 的净增量 trend / trend_first。

    history: (vote_id, created_at, attempt, items) 的全历史行,顺序任意
    (内部按选民分组后以 (created_at, attempt) 升序重放)。
    item_keys: item → 0..n 个 canonical key(str 或 tuple);返回空表示该
    item 被丢弃(如白名单未命中)——必须与榜单计数的丢弃口径一致。
    first_flag: item 是否带本命标记;trend_first 对本命 key 集合同样做 diff
    (本命转移 = 旧 key -1、新 key +1)。
    返回 {key: {"trend": [{"hrs","cnt"}...], "trend_first": [...]}},稀疏、
    只含 cnt != 0 的桶,hrs 升序。
    """
    hours_cap = max(total_hours, 1)
    trend: dict[Hashable, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    trend_first: dict[Hashable, dict[int, int]] = defaultdict(
        lambda: defaultdict(int)
    )

    by_vote: dict[str, list[tuple[datetime, int, list[dict]]]] = defaultdict(list)
    for vote_id, created_at, attempt, items in history:
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        by_vote[vote_id].append((created_at, attempt, items))

    for snapshots in by_vote.values():
        snapshots.sort(key=lambda s: (s[0], s[1]))
        prev_keys: set[Hashable] = set()
        prev_first: set[Hashable] = set()
        for created_at, _attempt, items in snapshots:
            bucket = max(0, min(
                int((created_at - vote_start).total_seconds() / 3600),
                hours_cap - 1,
            ))
            cur_keys: set[Hashable] = set()
            cur_first: set[Hashable] = set()
            for item in items:
                keys = list(item_keys(item))
                cur_keys.update(keys)
                if first_flag(item):
                    cur_first.update(keys)
            for k in cur_keys - prev_keys:
                trend[k][bucket] += 1
            for k in prev_keys - cur_keys:
                trend[k][bucket] -= 1
            for k in cur_first - prev_first:
                trend_first[k][bucket] += 1
            for k in prev_first - cur_first:
                trend_first[k][bucket] -= 1
            prev_keys, prev_first = cur_keys, cur_first

    result: dict[Hashable, dict[str, list[dict]]] = {}
    for k in trend.keys() | trend_first.keys():
        result[k] = {
            "trend": [
                {"hrs": h, "cnt": c}
                for h, c in sorted(trend[k].items()) if c != 0
            ],
            "trend_first": [
                {"hrs": h, "cnt": c}
                for h, c in sorted(trend_first[k].items()) if c != 0
            ],
        }
    return result


def trends_for(
    trends: dict[Hashable, dict[str, list[dict]]], key: Hashable
) -> dict[str, list[dict]]:
    """取某 key 的 trend 对,缺失时返回空对(实体从未出现在历史中)。"""
    return trends.get(key, _EMPTY)
