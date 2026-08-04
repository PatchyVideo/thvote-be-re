"""result_compat.py 适配器层单元测试：历史对比字段的"无数据"哨兵值。

MUST FIX 3（2026-07-19 fix-wave）：``RankingEntry`` 的 rank_last_*/
vote_count_last_*/first_vote_count_last_*/first_vote_percentage_last_*/
vote_percentage_last_* 本轮 compute 尚未提供真实历史数据源，必须固定回退到
旧网关（``result-query/src/query.rs`` 的 ``.unwrap_or(-1)``/
``.unwrap_or(-1.0)``）同款的"无数据"哨兵 ``-1``/``-1.0``，不能是 ``0``/
``0.0``——前端（``characterCompare.vue``）按
``item.voteCountLast1 < 0 ? '-' : ...`` 判断"有没有上届数据"；填 0 会被
误读成"上届确实是 0 票"这种编造出来的数据，而不是"没有上届数据"。
"""

from datetime import datetime, timezone

from src.api.graphql.resolvers.result_compat import _ranking_entry_from_dict
from src.apps.result.compute import compute_ranking
from src.apps.result.whitelist import Whitelist, WhitelistEntry

VS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _wl() -> Whitelist:
    return Whitelist([
        WhitelistEntry("id_a", "角色甲", "", "", "旧作", None, None, 0),
    ])


def test_ranking_entry_historical_fields_are_sentinel_not_zero() -> None:
    # historical={} 是 compute_service.py 当前的固定传参（v1 尚无历史数据源）；
    # 这正是 rank_last_*/vote_count_last_* 等字段全部退化为"无数据"的真实场景。
    votes = [("u1", VS, [{"id": "id_a", "first": True, "reason": None}])]
    ranking, _ = compute_ranking(votes, _wl(), {}, {}, VS, 1)
    entry = _ranking_entry_from_dict(ranking[0])

    assert entry.rank_last_1 == -1
    assert entry.rank_last_2 == -1
    assert entry.vote_count_last_1 == -1
    assert entry.vote_count_last_2 == -1
    assert entry.first_vote_count_last_1 == -1
    assert entry.first_vote_count_last_2 == -1
    assert entry.first_vote_percentage_last_1 == -1.0
    assert entry.first_vote_percentage_last_2 == -1.0
    assert entry.vote_percentage_last_1 == -1.0
    assert entry.vote_percentage_last_2 == -1.0
