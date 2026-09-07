"""高级搜索服务集成测:整包重算/缓存命中/版本/未知名/空子集(设计稿 §三/§六/§七)。"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest
import pytest_asyncio

try:
    import fakeredis.aioredis as fakeredis_aioredis
    FakeRedis = fakeredis_aioredis.FakeRedis
except ImportError:
    import fakeredis
    FakeRedis = fakeredis.aioredis.FakeRedis

from tests.integration.conftest import seed_voteables_from_snapshot

import src.apps.result.advanced_search.service as adv_service_module
from src.apps.result.advanced_search.service import (
    ensure_filtered_results,
    snapshot_version_key,
)
from src.apps.result.compute_dao import ComputeDAO
from src.apps.result.compute_service import ComputeService
from src.apps.result.whitelist import load_whitelist_db
from src.common.config import Settings
from src.common.exceptions import ValidationError
from src.db_model.raw_submit import RawCharacterSubmit


@pytest_asyncio.fixture
def fake_redis():
    return FakeRedis(decode_responses=True)


@pytest_asyncio.fixture
def settings():
    s = Settings()
    s.__dict__["vote_year"] = 2026
    s.__dict__["vote_start_iso"] = "2026-01-01T00:00:00Z"
    s.__dict__["vote_end_iso"] = "2026-12-31T23:59:59Z"
    s.__dict__["gender_question_code"] = "11011"
    s.__dict__["gender_male_option_code"] = "1101101"
    s.__dict__["gender_female_option_code"] = "1101102"
    return s


@pytest_asyncio.fixture
async def seeded(session, session_maker, fake_redis, settings, monkeypatch):
    """种子:白名单 + 3 条角色票(u1/u2 投 id1,u3 投 id2)→ compute_all。
    并把 advanced_search.service 的 get_session_maker 指到测试库。
    返回 (name1, name2):id1/id2 的展示名,供 DSL 用。"""
    await seed_voteables_from_snapshot(session, "character", 2026)
    await seed_voteables_from_snapshot(session, "music", 2026)
    wl = await load_whitelist_db(session, "character", 2026)
    id1, id2 = sorted(wl.ids)[:2]
    for vid, cid, first in [("u1", id1, True), ("u2", id1, False), ("u3", id2, True)]:
        session.add(RawCharacterSubmit(
            vote_id=vid, attempt=1,
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc), user_ip="",
            payload=[{"id": cid, "first": first, "reason": None}],
        ))
    await session.commit()
    compute_service = ComputeService(ComputeDAO(session), fake_redis, settings)
    result = await compute_service.compute_all(2026)
    assert result["ok"] is True
    monkeypatch.setattr(adv_service_module, "get_session_maker", lambda: session_maker)
    return wl.name_of(id1), wl.name_of(id2)


@pytest.mark.asyncio
async def test_compute_all_writes_snapshot_version(seeded, fake_redis):
    assert await fake_redis.get(snapshot_version_key(2026)) is not None


@pytest.mark.asyncio
async def test_filtered_ranking_uses_subset_denominator(seeded, fake_redis, settings):
    name1, _ = seeded
    infix = await ensure_filtered_results(
        fake_redis, settings, 2026, f'chars: ["{name1}"]'
    )
    ranking = json.loads(await fake_redis.get(f"result:2026:{infix}:chars:ranking"))
    # 子集 = {u1, u2}(都投了 id1);榜上只有 name1,票数 2,占比分母是子集的 2
    assert [e["name"] for e in ranking] == [name1]
    assert ranking[0]["rank"][0]["vote_count"] == 2
    assert ranking[0]["rank"][0]["vote_percentage"] == 1.0
    stats = json.loads(await fake_redis.get(f"result:2026:{infix}:global_stats"))
    assert stats["num_vote"] == 2


@pytest.mark.asyncio
async def test_cache_hit_skips_recompute(seeded, fake_redis, settings, monkeypatch):
    name1, _ = seeded
    calls = {"n": 0}
    real = adv_service_module._compute_filtered

    async def counting(*args, **kwargs):
        calls["n"] += 1
        return await real(*args, **kwargs)

    monkeypatch.setattr(adv_service_module, "_compute_filtered", counting)
    q = f'chars: ["{name1}"]'
    infix1 = await ensure_filtered_results(fake_redis, settings, 2026, q)
    infix2 = await ensure_filtered_results(fake_redis, settings, 2026, q)
    assert infix1 == infix2
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_version_flip_invalidates_cache(
    seeded, fake_redis, settings, monkeypatch
):
    """版本翻转(定时重算后)让旧筛选缓存自然失效,同一 query 必须重新计算
    (设计稿 §九.5)。"""
    name1, _ = seeded
    q = f'chars: ["{name1}"]'
    infix1 = await ensure_filtered_results(fake_redis, settings, 2026, q)

    await fake_redis.set(snapshot_version_key(2026), "999999")

    calls = {"n": 0}
    real = adv_service_module._compute_filtered

    async def counting(*args, **kwargs):
        calls["n"] += 1
        return await real(*args, **kwargs)

    monkeypatch.setattr(adv_service_module, "_compute_filtered", counting)
    infix2 = await ensure_filtered_results(fake_redis, settings, 2026, q)

    assert infix2 != infix1
    assert "adv:999999:" in infix2
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_unknown_name_raises(seeded, fake_redis, settings):
    with pytest.raises(ValidationError) as exc_info:
        await ensure_filtered_results(
            fake_redis, settings, 2026, 'chars: ["绝对不存在的角色名XYZ"]'
        )
    assert exc_info.value.message == "ADVANCED_SEARCH_UNKNOWN_NAME"


@pytest.mark.asyncio
async def test_empty_subset_is_valid_result(seeded, fake_redis, settings):
    name1, name2 = seeded
    infix = await ensure_filtered_results(
        fake_redis, settings, 2026,
        f'chars_first="{name1}" AND chars_first="{name2}"',
    )
    ranking = json.loads(await fake_redis.get(f"result:2026:{infix}:chars:ranking"))
    stats = json.loads(await fake_redis.get(f"result:2026:{infix}:global_stats"))
    assert ranking == []
    assert stats["num_vote"] == 0


@pytest.mark.asyncio
async def test_miss_budget_limits_distinct_queries(
    seeded, fake_redis, settings, monkeypatch
):
    """全局 miss 限频:阈值 monkeypatch 成 2,连发 3 个不同(各自都是 miss 的)
    查询,第 3 个必须抛 ADVANCED_SEARCH_BUSY(必须项,审查者方案 a)。"""
    name1, name2 = seeded
    monkeypatch.setattr(adv_service_module, "ADV_MISS_LIMIT_PER_MINUTE", 2)
    q1 = f'chars: ["{name1}"]'
    q2 = f'chars: ["{name2}"]'
    q3 = f'chars_first="{name1}"'
    await ensure_filtered_results(fake_redis, settings, 2026, q1)
    await ensure_filtered_results(fake_redis, settings, 2026, q2)
    with pytest.raises(ValidationError) as exc_info:
        await ensure_filtered_results(fake_redis, settings, 2026, q3)
    assert exc_info.value.message == "ADVANCED_SEARCH_BUSY"


@pytest.mark.asyncio
async def test_miss_budget_cache_hit_does_not_consume_budget(
    seeded, fake_redis, settings, monkeypatch
):
    """预算打满后,重复同一(已缓存)query 命中缓存路径,不消耗预算、仍成功。"""
    name1, name2 = seeded
    monkeypatch.setattr(adv_service_module, "ADV_MISS_LIMIT_PER_MINUTE", 2)
    q1 = f'chars: ["{name1}"]'
    q2 = f'chars: ["{name2}"]'
    infix1 = await ensure_filtered_results(fake_redis, settings, 2026, q1)
    await ensure_filtered_results(fake_redis, settings, 2026, q2)
    # 预算已耗尽(2/2);重复 q1 命中缓存,不应该抛 ADVANCED_SEARCH_BUSY。
    infix_again = await ensure_filtered_results(fake_redis, settings, 2026, q1)
    assert infix_again == infix1


@pytest.mark.asyncio
async def test_concurrent_same_query_single_flight(
    seeded, fake_redis, settings, monkeypatch
):
    """并发路径:两个协程同时对同一新查询调 ensure_filtered_results,
    单飞锁下 _compute_filtered 至多被调 2 次(锁竞争允许 1 或 2),
    两者返回同一 infix,缓存最终存在。"""
    name1, _ = seeded
    calls = {"n": 0}
    real = adv_service_module._compute_filtered

    async def counting(*args, **kwargs):
        calls["n"] += 1
        return await real(*args, **kwargs)

    monkeypatch.setattr(adv_service_module, "_compute_filtered", counting)
    q = f'chars: ["{name1}"]'
    infix1, infix2 = await asyncio.gather(
        ensure_filtered_results(fake_redis, settings, 2026, q),
        ensure_filtered_results(fake_redis, settings, 2026, q),
    )
    assert infix1 == infix2
    assert 1 <= calls["n"] <= 2
    assert await fake_redis.exists(f"result:2026:{infix1}:global_stats")


# ── B-060:扣费后置 / 等锁跟随锁存活 / per-IP 预算 ─────────────────────


def _foreign_lock_key(infix: str) -> str:
    return f"adv_lock:2026:{infix.rsplit(':', 1)[-1]}"


def _install_counters(monkeypatch) -> dict:
    """给 _check_miss_budget/_compute_filtered 包计数器(仍调用真实现)。"""
    calls = {"budget": 0, "compute": 0}
    real_budget = adv_service_module._check_miss_budget
    real_compute = adv_service_module._compute_filtered

    async def counting_budget(*args, **kwargs):
        calls["budget"] += 1
        return await real_budget(*args, **kwargs)

    async def counting_compute(*args, **kwargs):
        calls["compute"] += 1
        return await real_compute(*args, **kwargs)

    monkeypatch.setattr(adv_service_module, "_check_miss_budget", counting_budget)
    monkeypatch.setattr(adv_service_module, "_compute_filtered", counting_compute)
    return calls


@pytest.mark.asyncio
async def test_waiter_served_by_cache_consumes_no_budget(
    seeded, fake_redis, settings, monkeypatch
):
    """等锁者最终从缓存拿到结果 → 不扣任何预算、不重算(B-060 扣费后置)。"""
    name1, _ = seeded
    q = f'chars: ["{name1}"]'
    infix = await ensure_filtered_results(fake_redis, settings, 2026, q)
    marker_key = f"result:2026:{infix}:global_stats"
    marker_val = await fake_redis.get(marker_key)
    await fake_redis.delete(marker_key)  # 重演"别人正在算、缓存尚未就绪"
    await fake_redis.set(_foreign_lock_key(infix), "foreign-token", px=30_000)

    calls = _install_counters(monkeypatch)

    async def write_marker_later() -> None:
        await asyncio.sleep(0.05)  # 在等锁者第一次轮询(0.2s)前写入
        await fake_redis.set(marker_key, marker_val)

    result_infix, _ = await asyncio.gather(
        ensure_filtered_results(fake_redis, settings, 2026, q),
        write_marker_later(),
    )
    assert result_infix == infix
    assert calls == {"budget": 0, "compute": 0}


@pytest.mark.asyncio
async def test_waiter_computes_after_lock_vanishes(
    seeded, fake_redis, settings, monkeypatch
):
    """持锁者消失且没写 marker → 等锁者提前退出等待,自己扣费计算
    (不必等满等待上限;B-060 等锁跟随锁存活)。"""
    name1, name2 = seeded
    q = f'chars: ["{name2}"]'  # 未缓存过的查询
    from src.apps.result.advanced_search.dsl import fingerprint, parse_query

    fp = fingerprint(parse_query(q))
    lock_key = f"adv_lock:2026:{fp}"
    await fake_redis.set(lock_key, "foreign-token", px=30_000)

    calls = _install_counters(monkeypatch)

    async def release_lock_later() -> None:
        await asyncio.sleep(0.05)
        await fake_redis.delete(lock_key)  # 持锁者"死亡",没留下 marker

    import time

    t0 = time.monotonic()
    infix, _ = await asyncio.gather(
        ensure_filtered_results(fake_redis, settings, 2026, q),
        release_lock_later(),
    )
    elapsed = time.monotonic() - t0
    assert calls == {"budget": 1, "compute": 1}
    assert await fake_redis.exists(f"result:2026:{infix}:global_stats")
    # 提前退出:远小于旧实现"等满 5s 再兜底"的耗时(锁 0.05s 就没了,
    # 首次轮询 0.2s 即应发现并转入计算;给计算本身留 ~2s 余量)
    assert elapsed < 3.0, f"waiter did not exit early: {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_per_ip_budget_isolated(seeded, fake_redis, settings, monkeypatch):
    """per-IP 预算彼此隔离:A 打满不影响 B;未设 IP 时只受全局预算约束。"""
    from src.common.middleware.client_ip import client_ip_var

    monkeypatch.setattr(adv_service_module, "ADV_MISS_LIMIT_PER_IP_PER_MINUTE", 1)
    name1, name2 = seeded

    token = client_ip_var.set("198.51.100.1")
    try:
        await ensure_filtered_results(
            fake_redis, settings, 2026, f'chars: ["{name1}"]'
        )  # A 的第 1 次 miss:成功
        with pytest.raises(ValidationError) as exc_info:
            await ensure_filtered_results(
                fake_redis, settings, 2026, f'chars: ["{name2}"]'
            )  # A 的第 2 次 miss:per-IP 超限
        assert exc_info.value.message == "ADVANCED_SEARCH_BUSY"
    finally:
        client_ip_var.reset(token)

    token = client_ip_var.set("198.51.100.2")
    try:
        await ensure_filtered_results(
            fake_redis, settings, 2026, f'chars_first="{name1}"'
        )  # B 不受 A 影响:成功
    finally:
        client_ip_var.reset(token)
