"""Integration tests for vote_data module (service + DAO + summary)."""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.apps.vote_data.dao import VoteDataDAO
from src.apps.vote_data.schemas import (
    CharacterVoteItem,
    CharacterVoteRequest,
    CpVoteItem,
    CpVoteRequest,
    MusicVoteItem,
    MusicVoteRequest,
    QuestionnaireVoteRequest,
)
from src.apps.vote_data.service import VoteDataService
from src.db_model.base import Base
from src.db_model.user import User

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("JWT_SECRET_KEY", "test-key")
os.environ.setdefault("VOTE_START_ISO", "2020-01-01T00:00:00+00:00")
os.environ.setdefault("VOTE_END_ISO", "2099-12-31T23:59:59+00:00")

_USER_ID = "vote-data-test-user-001"


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        # Insert a user row so FK constraints pass
        s.add(User(
            id=_USER_ID,
            email="vd@test.com",
            email_verified=True,
            removed=False,
            register_ip_address="127.0.0.1",
        ))
        await s.commit()
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
def service(session):
    return VoteDataService(VoteDataDAO(session))


# ── Character ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_submit_character_creates_row(service, session):
    req = CharacterVoteRequest(character_list=[
        CharacterVoteItem(id="博丽灵梦", first=True, reason="最喜欢"),
        CharacterVoteItem(id="雾雨魔理沙"),
    ])
    resp = await service.submit_character_vote(_USER_ID, req)
    assert resp.id == _USER_ID
    assert len(resp.character_list) == 2
    assert resp.character_list[0]["id"] == "博丽灵梦"
    assert resp.character_list[0]["first"] is True
    assert resp.character_list[0]["reason"] == "最喜欢"


@pytest.mark.asyncio
async def test_submit_character_upserts_on_second_call(service, session):
    req1 = CharacterVoteRequest(character_list=[CharacterVoteItem(id="Alice")])
    await service.submit_character_vote(_USER_ID, req1)

    req2 = CharacterVoteRequest(character_list=[CharacterVoteItem(id="Bob", first=True)])
    resp = await service.submit_character_vote(_USER_ID, req2)
    assert len(resp.character_list) == 1
    assert resp.character_list[0]["id"] == "Bob"

    # Only one row in DB
    from sqlalchemy import select, func
    from src.db_model.character import Character
    count = (await session.execute(
        select(func.count()).select_from(Character)
    )).scalar_one()
    assert count == 1


# ── Music ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_submit_music_creates_row(service):
    req = MusicVoteRequest(music_list=[
        MusicVoteItem(id="Bad Apple!!", first=True),
        MusicVoteItem(id="U.N.オーエン"),
    ])
    resp = await service.submit_music_vote(_USER_ID, req)
    assert resp.id == _USER_ID
    assert len(resp.music_list) == 2
    assert resp.music_list[0]["first"] is True


@pytest.mark.asyncio
async def test_submit_music_upserts(service):
    req1 = MusicVoteRequest(music_list=[MusicVoteItem(id="Song A")])
    await service.submit_music_vote(_USER_ID, req1)

    req2 = MusicVoteRequest(music_list=[MusicVoteItem(id="Song B"), MusicVoteItem(id="Song C")])
    resp = await service.submit_music_vote(_USER_ID, req2)
    assert len(resp.music_list) == 2
    assert resp.music_list[0]["id"] == "Song B"


# ── CP ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_submit_cp_creates_row(service):
    req = CpVoteRequest(cp_list=[
        CpVoteItem(id_a="Alice", id_b="Bob", active="Alice", first=True, reason="好CP"),
    ])
    resp = await service.submit_cp_vote(_USER_ID, req)
    assert resp.id == _USER_ID
    item = resp.cp_list[0]
    assert item["id_a"] == "Alice"
    assert item["id_b"] == "Bob"
    assert item["active"] == "Alice"
    assert item["first"] is True


# ── Questionnaire ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_submit_questionnaire_creates_row(service):
    req = QuestionnaireVoteRequest(questionnaire_list=[
        {"id": 1, "answer": [1], "answer_str": None},
        {"id": 2, "answer_str": "男"},
    ])
    resp = await service.submit_questionnaire(_USER_ID, req)
    assert resp.id == _USER_ID
    assert len(resp.questionnaire_list) == 2
    assert resp.questionnaire_list[0]["id"] == 1


@pytest.mark.asyncio
async def test_submit_questionnaire_upserts(service):
    req1 = QuestionnaireVoteRequest(questionnaire_list=[{"id": 1, "answer": [1]}])
    await service.submit_questionnaire(_USER_ID, req1)

    req2 = QuestionnaireVoteRequest(questionnaire_list=[{"id": 1, "answer": [2]}, {"id": 2, "answer": [1]}])
    resp = await service.submit_questionnaire(_USER_ID, req2)
    assert len(resp.questionnaire_list) == 2
    assert resp.questionnaire_list[0]["answer"] == [2]


# ── Summary ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_summary_empty_for_new_user(service):
    summary = await service.get_user_vote_summary(_USER_ID)
    assert summary.has_character is False
    assert summary.has_music is False
    assert summary.has_cp is False
    assert summary.has_questionnaire is False


@pytest.mark.asyncio
async def test_summary_reflects_submitted_categories(service):
    await service.submit_character_vote(_USER_ID, CharacterVoteRequest(
        character_list=[CharacterVoteItem(id="Alice")]
    ))
    await service.submit_music_vote(_USER_ID, MusicVoteRequest(
        music_list=[MusicVoteItem(id="Song A")]
    ))

    summary = await service.get_user_vote_summary(_USER_ID)
    assert summary.has_character is True
    assert summary.has_music is True
    assert summary.has_cp is False
    assert summary.has_questionnaire is False


@pytest.mark.asyncio
async def test_summary_all_four_categories(service):
    await service.submit_character_vote(_USER_ID, CharacterVoteRequest(
        character_list=[CharacterVoteItem(id="Alice")]
    ))
    await service.submit_music_vote(_USER_ID, MusicVoteRequest(
        music_list=[MusicVoteItem(id="Song")]
    ))
    await service.submit_cp_vote(_USER_ID, CpVoteRequest(
        cp_list=[CpVoteItem(id_a="A", id_b="B")]
    ))
    await service.submit_questionnaire(_USER_ID, QuestionnaireVoteRequest(
        questionnaire_list=[{"id": 1, "answer": [1]}]
    ))

    summary = await service.get_user_vote_summary(_USER_ID)
    assert all([
        summary.has_character,
        summary.has_music,
        summary.has_cp,
        summary.has_questionnaire,
    ])


# ── Batch reads (used by ComputeDAO) ──────────────────────────────────

@pytest.mark.asyncio
async def test_get_all_submissions_returns_all_rows(service, session):
    await service.submit_character_vote(_USER_ID, CharacterVoteRequest(
        character_list=[CharacterVoteItem(id="Alice")]
    ))
    from src.apps.vote_data.dao import VoteDataDAO
    dao = VoteDataDAO(session)
    rows = await dao.get_all_character_submissions()
    assert len(rows) == 1
    assert rows[0].id == _USER_ID
    assert rows[0].character_list[0]["id"] == "Alice"
