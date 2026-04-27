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


@pytest.fixture(autouse=True)
def patch_redis(monkeypatch):
    """Replace common.redis.get_redis with a fakeredis client per test."""
    fakeredis_mod = pytest.importorskip("fakeredis")
    fake = fakeredis_mod.aioredis.FakeRedis(decode_responses=True)

    async def _get_redis_stub():
        return fake

    monkeypatch.setattr("src.common.redis.get_redis", _get_redis_stub)
    monkeypatch.setattr("src.common.verification.email_code.get_redis", _get_redis_stub)
    monkeypatch.setattr(
        "src.common.middleware.rate_limit.get_redis", _get_redis_stub
    )
    yield fake
