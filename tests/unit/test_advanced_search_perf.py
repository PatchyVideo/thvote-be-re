"""性能冒烟:5 万合成票走 事实索引→求值→子集重排名 全程 < 2s(设计稿 §九-6)。

纯内存路径(不含 DB 载票——载票是既有 compute_all 同款 SELECT,不在此测)。
阈值给足余量:CI 机器慢也不该 flake;若仍偶发,放宽到 4s 并在此注明。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from src.apps.result.advanced_search.dsl import parse_query
from src.apps.result.advanced_search.subset import (
    build_facts,
    evaluate_subset,
    resolve_names,
)
from src.apps.result.compute import compute_ranking
from src.apps.result.whitelist import Whitelist, WhitelistEntry

N_VOTES = 50_000
N_CHARS = 50
_DT = datetime(2026, 1, 2, tzinfo=timezone.utc)


def test_perf_smoke_50k_votes() -> None:
    wl = Whitelist([
        WhitelistEntry(
            candidate_id=100 + j, voteable_id=j, old_id=None, name=f"角色{j}",
            name_jp="", origin="", type="", first_appearance=None,
            album=None, system_id=j,
        )
        for j in range(N_CHARS)
    ])
    votes = [
        (
            f"u{i}", _DT,
            [{"id": str(100 + (i % N_CHARS)), "first": i % 7 == 0, "reason": None},
             {"id": str(100 + ((i + 1) % N_CHARS)), "first": False, "reason": None}],
        )
        for i in range(N_VOTES)
    ]
    ast = parse_query('chars: ["角色1", "角色2"] OR chars_first="角色3"')

    t0 = time.monotonic()
    resolved = resolve_names(ast, wl, Whitelist([]))
    facts = build_facts(votes, [], [], [], wl, Whitelist([]))
    subset = evaluate_subset(ast, facts, resolved)
    filtered = [v for v in votes if v[0] in subset]
    ranking, _global = compute_ranking(filtered, wl, {}, {}, _DT, 24)
    elapsed = time.monotonic() - t0

    assert subset  # 约束确实圈到了票
    assert ranking
    assert elapsed < 2.0, f"advanced search pipeline took {elapsed:.2f}s"
