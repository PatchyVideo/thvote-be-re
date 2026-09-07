"""Postgres-only: the two user_identity unique constraints really fire.

sqlite ``create_all`` also creates them, but the point of this test (B-022)
is the real migration-built schema.  Skipped unless ``DATABASE_URL`` points
at Postgres — CI does, after ``alembic upgrade head``.
"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db_model.user_identity import UserIdentity
from tests.helpers.users import build_user

_URL = os.environ.get("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not _URL.startswith("postgresql"), reason="requires a Postgres DATABASE_URL"
)


@pytest_asyncio.fixture
async def pg_session():
    engine = create_async_engine(_URL, future=True)
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest.mark.asyncio
async def test_same_subject_twice_rejected(pg_session):
    subject = f"dup-{uuid.uuid4()}@example.com"
    pg_session.add(build_user(email=subject))
    pg_session.add(build_user(email=subject))
    with pytest.raises(IntegrityError) as exc_info:
        await pg_session.commit()
    assert "uq_user_identity_provider_subject" in str(exc_info.value)


@pytest.mark.asyncio
async def test_two_identities_same_provider_same_user_rejected(pg_session):
    user = build_user(email=f"one-{uuid.uuid4()}@example.com")
    user.identities.append(
        UserIdentity(provider="email", subject=f"two-{uuid.uuid4()}@example.com", verified=True)
    )
    pg_session.add(user)
    with pytest.raises(IntegrityError) as exc_info:
        await pg_session.commit()
    assert "uq_user_identity_user_provider" in str(exc_info.value)


@pytest.mark.asyncio
async def test_unknown_provider_rejected_by_check(pg_session):
    user = build_user()
    user.identities.append(UserIdentity(provider="bogus", subject="x", verified=True))
    pg_session.add(user)
    with pytest.raises(IntegrityError) as exc_info:
        await pg_session.commit()
    assert "ck_user_identity_provider" in str(exc_info.value)
