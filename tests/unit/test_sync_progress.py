"""Tests for sync progress and checkpoint Redis utilities."""
import pytest
import fakeredis.aioredis


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.mark.asyncio
async def test_set_and_get_progress(redis):
    from src.apps.admin.sync.progress import set_progress, get_progress

    await set_progress(redis, "run-1", processed=100, total=500, errors=2)
    data = await get_progress(redis, "run-1")

    assert data["processed"] == "100"
    assert data["total"] == "500"
    assert data["errors"] == "2"


@pytest.mark.asyncio
async def test_cancel_signal(redis):
    from src.apps.admin.sync.progress import set_cancel_signal, check_cancel

    assert not await check_cancel(redis, "run-1")
    await set_cancel_signal(redis, "run-1")
    assert await check_cancel(redis, "run-1")


@pytest.mark.asyncio
async def test_current_run(redis):
    from src.apps.admin.sync.progress import set_current_run, get_current_run

    assert await get_current_run(redis) is None
    await set_current_run(redis, "run-abc")
    assert await get_current_run(redis) == "run-abc"


@pytest.mark.asyncio
async def test_save_and_load_checkpoint(redis):
    from src.apps.admin.sync.checkpoint import save_checkpoint, load_checkpoint

    assert await load_checkpoint(redis, "run-1", "voters") is None
    await save_checkpoint(redis, "run-1", "voters", "507f1f77bcf86cd799439011")
    val = await load_checkpoint(redis, "run-1", "voters")
    assert val == "507f1f77bcf86cd799439011"
