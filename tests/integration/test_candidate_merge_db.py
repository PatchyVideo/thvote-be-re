"""Integration tests for candidate merge/unmerge (B-040)."""
import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_merge_and_unmerge(session):
    from src.apps.result.compute_dao import ComputeDAO

    await session.execute(text(
        "INSERT INTO candidate_character (vote_year, name) VALUES (2026, '灵梦')"
    ))
    await session.execute(text(
        "INSERT INTO candidate_character (vote_year, name) VALUES (2026, '博丽灵梦')"
    ))
    await session.commit()
    canonical = (await session.execute(
        text("SELECT id FROM candidate_character WHERE name='灵梦'")
    )).scalar_one()
    variant = (await session.execute(
        text("SELECT id FROM candidate_character WHERE name='博丽灵梦'")
    )).scalar_one()

    dao = ComputeDAO(session)
    assert await dao.set_merged_into(variant, "character", canonical) == "ok"
    merges = await dao.list_merges("character", 2026)
    assert any(m["id"] == variant and m["merged_into"] == canonical for m in merges)

    assert await dao.set_merged_into(variant, "character", None) == "ok"
    assert await dao.list_merges("character", 2026) == []


@pytest.mark.asyncio
async def test_merge_target_not_found(session):
    from src.apps.result.compute_dao import ComputeDAO

    await session.execute(text(
        "INSERT INTO candidate_character (vote_year, name) VALUES (2026, 'X')"
    ))
    await session.commit()
    cid = (await session.execute(
        text("SELECT id FROM candidate_character WHERE name='X'")
    )).scalar_one()
    dao = ComputeDAO(session)
    assert await dao.set_merged_into(cid, "character", 999999) == "target_not_found"
    assert await dao.set_merged_into(cid, "character", cid) == "self"
    assert await dao.set_merged_into(999999, "character", cid) == "not_found"
