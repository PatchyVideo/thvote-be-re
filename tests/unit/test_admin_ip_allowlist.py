from src.apps.admin.deps import _ip_allowed


def test_empty_allowlist_allows_everything():
    assert _ip_allowed("1.2.3.4", []) is True


def test_exact_ip_match():
    assert _ip_allowed("1.2.3.4", ["1.2.3.4"]) is True
    assert _ip_allowed("1.2.3.5", ["1.2.3.4"]) is False


def test_cidr_match():
    assert _ip_allowed("10.0.5.9", ["10.0.0.0/8"]) is True
    assert _ip_allowed("11.0.5.9", ["10.0.0.0/8"]) is False


def test_malformed_client_ip_denied_when_allowlist_set():
    assert _ip_allowed("not-an-ip", ["1.2.3.4"]) is False


def test_malformed_allowlist_entry_skipped():
    assert _ip_allowed("1.2.3.4", ["garbage", "1.2.3.4"]) is True
