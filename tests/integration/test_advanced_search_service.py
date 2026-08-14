"""高级搜索服务集成测:整包重算/缓存命中/版本/未知名/空子集(设计稿 §三/§六/§七)。"""

from __future__ import annotations

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
