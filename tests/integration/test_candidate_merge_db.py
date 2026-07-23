"""Integration tests for candidate merge/unmerge (B-040)."""
import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_merge_and_unmerge(session):
    """After voteable refactor: merged_into column removed, merge is a no-op.
    set_merged_into still validates inputs but does not persist the link."""
    from src.apps.result.compute_dao import ComputeDAO

    # Seed work → voteables → candidates (new schema)
    await session.execute(text(
        "INSERT INTO work (id, name, type) VALUES (1, '红魔乡', 'new')"
    ))
    await session.execute(text(
        "INSERT INTO voteable_character (id, name, work_id) VALUES (10, '灵梦', 1)"
    ))
    await session.execute(text(
        "INSERT INTO voteable_character (id, name, work_id) VALUES (11, '博丽灵梦', 1)"
    ))
    await session.execute(text(
        "INSERT INTO candidate_character (vote_year, voteable_id) VALUES (2026, 10)"
    ))
    await session.execute(text(
        "INSERT INTO candidate_character (vote_year, voteable_id) VALUES (2026, 11)"
    ))
    await session.commit()
    canonical = (await session.execute(
        text("SELECT id FROM candidate_character WHERE voteable_id=10")
    )).scalar_one()
    variant = (await session.execute(
        text("SELECT id FROM candidate_character WHERE voteable_id=11")
    )).scalar_one()

    dao = ComputeDAO(session)
    # set_merged_into still validates inputs (not_found, target_not_found, self)
    # but merged_into column was removed — the link is not persisted
    assert await dao.set_merged_into(variant, "character", canonical) == "ok"
    # list_merges returns empty after voteable refactor
    assert await dao.list_merges("character", 2026) == []

    # Unmerge still returns ok (no-op)
    assert await dao.set_merged_into(variant, "character", None) == "ok"
    assert await dao.list_merges("character", 2026) == []


@pytest.mark.asyncio
async def test_merge_target_not_found(session):
    from src.apps.result.compute_dao import ComputeDAO

    # Seed work → voteable → candidate (new schema)
    await session.execute(text(
        "INSERT INTO work (id, name, type) VALUES (1, 'w', 'new')"
    ))
    await session.execute(text(
        "INSERT INTO voteable_character (id, name, work_id) VALUES (10, 'X', 1)"
    ))
    await session.execute(text(
        "INSERT INTO candidate_character (vote_year, voteable_id) VALUES (2026, 10)"
    ))
    await session.commit()
    cid = (await session.execute(
        text("SELECT id FROM candidate_character WHERE voteable_id=10")
    )).scalar_one()
    dao = ComputeDAO(session)
    assert await dao.set_merged_into(cid, "character", 999999) == "target_not_found"
    assert await dao.set_merged_into(cid, "character", cid) == "self"
    assert await dao.set_merged_into(999999, "character", cid) == "not_found"
