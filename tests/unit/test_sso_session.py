import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_create_sso_session_returns_sid():
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)

    from src.apps.user.sso_session import create_sso_session
    sid = await create_sso_session(redis, {"qq_openid": "12345"})

    assert len(sid) == 36  # UUID4 format
    redis.set.assert_called_once()
    call_args = redis.set.call_args
    assert call_args[1]["ex"] == 600


@pytest.mark.asyncio
async def test_consume_sso_session_returns_data_and_deletes():
    import json
    data = {"thbwiki_uid": "999", "qq_openid": None}

    redis = AsyncMock()
    redis.getdel = AsyncMock(return_value=json.dumps(data).encode())

    from src.apps.user.sso_session import consume_sso_session
    result = await consume_sso_session(redis, "some-sid")

    assert result == data
    redis.getdel.assert_called_once_with("sso-session:some-sid")


@pytest.mark.asyncio
async def test_consume_sso_session_returns_none_for_missing():
    redis = AsyncMock()
    redis.getdel = AsyncMock(return_value=None)

    from src.apps.user.sso_session import consume_sso_session
    result = await consume_sso_session(redis, "nonexistent")

    assert result is None


@pytest.mark.asyncio
async def test_consume_sso_session_falls_back_when_getdel_unavailable():
    """Redis < 6.2 doesn't have GETDEL; fall back to GET+DEL via pipeline."""
    import json
    data = {"thbwiki_uid": "777"}
    redis = AsyncMock()
    from redis.exceptions import ResponseError
    redis.getdel = AsyncMock(side_effect=ResponseError("unknown command"))

    pipe = AsyncMock()
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__ = AsyncMock(return_value=False)
    pipe.get = MagicMock()
    pipe.delete = MagicMock()
    pipe.execute = AsyncMock(return_value=[json.dumps(data).encode(), 1])
    redis.pipeline = MagicMock(return_value=pipe)

    from src.apps.user.sso_session import consume_sso_session
    result = await consume_sso_session(redis, "some-sid")

    assert result == data
