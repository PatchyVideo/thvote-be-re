import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_qq_exchange_code_returns_openid():
    mock_response_token = MagicMock()
    mock_response_token.text = AsyncMock(
        return_value="access_token=mock_token&expires_in=7776000&refresh_token=mock_refresh"
    )
    mock_response_me = MagicMock()
    mock_response_me.text = AsyncMock(
        return_value='callback( {"client_id":"12345","openid":"ABCDEF"} );\n'
    )

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(side_effect=[mock_response_token, mock_response_me])
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        from src.apps.user.sso_clients import qq_exchange_code
        openid = await qq_exchange_code(
            code="test_code",
            app_id="12345",
            app_secret="secret",
            redirect_uri="https://example.com/callback",
        )

    assert openid == "ABCDEF"


@pytest.mark.asyncio
async def test_thbwiki_exchange_code_returns_uid():
    import jwt as pyjwt

    uid = "42"
    secret = "test_secret"
    token = pyjwt.encode(
        {"sub": uid, "username": "TestUser"},
        secret,
        algorithm="HS256",
    )

    mock_response = MagicMock()
    mock_response.json = AsyncMock(
        return_value={"access_token": "tok", "id_token": token}
    )
    mock_session = AsyncMock()
    mock_session.post = AsyncMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        from src.apps.user.sso_clients import thbwiki_exchange_code
        result_uid = await thbwiki_exchange_code(
            code="test_code",
            client_id="wiki_id",
            client_secret=secret,
            redirect_uri="https://example.com/callback",
        )

    assert result_uid == uid


def test_qq_authorize_url_contains_required_params():
    from src.apps.user.sso_clients import qq_authorize_url
    url = qq_authorize_url("MY_APP_ID", "https://example.com/cb", "state123")
    assert "graph.qq.com" in url
    assert "MY_APP_ID" in url
    assert "response_type=code" in url


def test_thbwiki_authorize_url_contains_required_params():
    from src.apps.user.sso_clients import thbwiki_authorize_url
    url = thbwiki_authorize_url("WIKI_ID", "https://example.com/cb", "state456")
    assert "thwiki.cc" in url
    assert "WIKI_ID" in url
    assert "response_type=code" in url
