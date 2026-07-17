"""_build_client_env: server UA from header + whitelisted client env (B-046)."""

from types import SimpleNamespace

from src.api.graphql.resolvers.submit_bridge import _build_client_env


def _info(ua: str | None):
    headers = {"user-agent": ua} if ua is not None else {}
    request = SimpleNamespace(headers=headers)
    return SimpleNamespace(context={"request": request})


def test_ua_from_header_and_client_keys_merged():
    raw = '{"tz": "Asia/Shanghai", "screen": "1920x1080@2", "lang": "zh-CN"}'
    env = _build_client_env(_info("Mozilla/5.0 ..."), raw)
    assert env == {
        "ua": "Mozilla/5.0 ...",
        "tz": "Asia/Shanghai",
        "screen": "1920x1080@2",
        "lang": "zh-CN",
    }


def test_only_whitelisted_keys_kept():
    raw = '{"tz": "UTC", "evil": "drop me", "cookie": "secret"}'
    env = _build_client_env(_info("UA"), raw)
    assert env == {"ua": "UA", "tz": "UTC"}


def test_api_bot_no_client_env_still_records_ua():
    """A scripted client that sends no clientEnv still gets its UA captured."""
    env = _build_client_env(_info("python-requests/2.31"), None)
    assert env == {"ua": "python-requests/2.31"}


def test_missing_ua_and_env_is_none():
    assert _build_client_env(_info(None), None) is None


def test_malformed_json_ignored_keeps_ua():
    env = _build_client_env(_info("UA"), "{not valid json")
    assert env == {"ua": "UA"}


def test_oversized_env_ignored():
    env = _build_client_env(_info("UA"), '{"tz":"' + "x" * 5000 + '"}')
    assert env == {"ua": "UA"}  # >2048 → client part dropped


def test_values_truncated():
    env = _build_client_env(_info("U" * 1000), '{"tz":"' + "z" * 500 + '"}')
    assert len(env["ua"]) == 512
    assert len(env["tz"]) == 128
