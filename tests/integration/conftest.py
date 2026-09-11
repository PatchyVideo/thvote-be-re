"""Integration-test fixtures.

We default to an in-memory sqlite database with the schema created via
``Base.metadata.create_all`` (faster, no external services required).
The CI workflow provisions real Postgres + Redis instances; if the
environment exposes ``DATABASE_URL`` pointing to Postgres, we honor it
and run alembic upgrade head instead.

Aliyun PNVS / DM SMTP clients are always mocked here.
"""
from __future__ import annotations

import os
from typing import AsyncGenerator
# ``import fakeredis.aioredis as X`` 只绑定别名 ``X``，不会绑定裸名
# ``fakeredis`` —— 而下方 patch_redis 的运行时 fallback 要引用裸名。
# 因此这里先裸 import fakeredis，保证两条 import 分支下 patch_redis 的
# 「fakeredis.aioredis.FakeRedis → fakeredis.FakeRedis」fallback 都可用。
try:
    import fakeredis
    import fakeredis.aioredis as fakeredis_aioredis
    FakeRedis = fakeredis_aioredis.FakeRedis
except ImportError:
    import fakeredis
    FakeRedis = fakeredis.FakeRedis
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.apps.user.dao import ActivityLogDAO, UserDAO
from src.apps.user.service import UserService
from src.common.aliyun.pnvs_client import PnvsResult, PnvsSendResult
from src.db_model.base import Base


@pytest_asyncio.fixture
async def engine():
    """Bring up a fresh in-memory sqlite schema for each test."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_maker(engine) -> AsyncGenerator[async_sessionmaker, None]:
    yield async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(session_maker) -> AsyncGenerator[AsyncSession, None]:
    async with session_maker() as s:
        yield s


@pytest.fixture
def fake_pnvs():
    """Mock Aliyun PNVS client; default behaviour: send→ok, check→PASS."""
    mock = AsyncMock()
    mock.send_sms_verify_code.return_value = PnvsSendResult(
        biz_id="BIZ-TEST", request_id="req-test"
    )
    mock.check_sms_verify_code.return_value = PnvsResult(
        passed=True, request_id="req-test"
    )
    return mock


@pytest.fixture
def fake_smtp():
    """Mock Aliyun DM SMTP client; default behaviour: succeed silently."""
    mock = AsyncMock()
    mock.send_verification_email.return_value = None
    return mock


@pytest_asyncio.fixture
async def user_service(session, session_maker, fake_pnvs, fake_smtp):
    """Wire a UserService with fake external services + isolated DAOs."""
    from src.common.verification.email_code import EmailCodeService
    from src.common.verification.sms_code import SmsCodeService

    return UserService(
        user_dao=UserDAO(session),
        activity_dao=ActivityLogDAO(session_maker),
        email_code_service=EmailCodeService(smtp_client=fake_smtp),
        sms_code_service=SmsCodeService(pnvs_client=fake_pnvs),
    )


async def seed_voteables_from_snapshot(session, category: str, vote_year: int):
    """把冻结的白名单快照 JSON 灌进 voteable_*/candidate_*（Task 6）。

    走 Task 4 的统一导入通道（``VoteableImportService``），不是绕过它直接
    INSERT——这样集成测试种子数据的路径和真实回填脚本
    （``scripts/whitelist_to_import.py``）用的是同一段代码，两者不会跑偏
    （dogfooding）。``VoteableImportService.run`` 自己在成功时已 commit
    （见 voteable_import_service.py:139），这里再 commit 一次是无害的幂等
    调用，不是遗漏后的补救。
    """
    import json as _json
    from pathlib import Path

    from scripts.whitelist_to_import import convert
    from src.apps.admin.voteable_import_service import VoteableImportService

    raw = _json.loads(
        (Path("src/apps/result/data") / f"whitelist_{category}.json").read_text()
    )
    svc = VoteableImportService(session)
    result = await svc.run(
        category, vote_year, "json",
        _json.dumps(convert(category, raw)), dry_run=False,
    )
    assert not result.get("conflicts")
    await session.commit()


@pytest.fixture(autouse=True)
def patch_redis(monkeypatch):
    """Replace common.redis.get_redis with a fakeredis client per test."""
    #fakeredis_mod = pytest.importorskip("fakeredis")
    #fake = fakeredis_mod.aioredis.FakeRedis(decode_responses=True)
    try:
        fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    except:
        fake = fakeredis.FakeRedis(decode_responses=True)

    async def _get_redis_stub():
        return fake

    monkeypatch.setattr("src.common.redis.get_redis", _get_redis_stub)
    monkeypatch.setattr("src.common.verification.email_code.get_redis", _get_redis_stub)
    monkeypatch.setattr(
        "src.common.middleware.rate_limit.get_redis", _get_redis_stub
    )
    yield fake
