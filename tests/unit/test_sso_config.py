def test_sso_config_fields_exist():
    """Settings must expose the 5 SSO config fields."""
    from src.common.config import Settings
    s = Settings(
        QQ_APP_ID="test_id",
        QQ_APP_SECRET="test_secret",
        THBWIKI_CLIENT_ID="wiki_id",
        THBWIKI_CLIENT_SECRET="wiki_secret",
        SSO_CALLBACK_BASE_URL="https://example.com",
    )
    assert s.qq_app_id == "test_id"
    assert s.qq_app_secret == "test_secret"
    assert s.thbwiki_client_id == "wiki_id"
    assert s.thbwiki_client_secret == "wiki_secret"
    assert s.sso_callback_base_url == "https://example.com"


def test_sso_config_defaults_to_none():
    """SSO config fields must default to None when not set."""
    from src.common.config import Settings
    s = Settings()
    assert s.qq_app_id is None
    assert s.thbwiki_client_id is None
    assert s.sso_callback_base_url is None
