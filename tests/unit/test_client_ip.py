"""get_client_ip: trust X-Real-IP only from trusted proxies, CIDR-aware (B-044)."""

from types import SimpleNamespace
from unittest.mock import patch

from src.apps.user.deps import _peer_is_trusted_proxy, get_client_ip


def _req(peer: str, headers: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        client=SimpleNamespace(host=peer),
        headers=headers or {},
    )


def _with_trusted(trusted: list[str]):
    return patch(
        "src.apps.user.deps.get_settings",
        return_value=SimpleNamespace(trusted_proxy_ips=trusted),
    )


# ── _peer_is_trusted_proxy ───────────────────────────────────────────


def test_exact_ip_match():
    assert _peer_is_trusted_proxy("172.20.0.5", ["172.20.0.5"])
    assert not _peer_is_trusted_proxy("172.20.0.6", ["172.20.0.5"])


def test_cidr_match():
    assert _peer_is_trusted_proxy("172.20.0.5", ["172.16.0.0/12"])
    assert not _peer_is_trusted_proxy("10.0.0.5", ["172.16.0.0/12"])


def test_empty_trusted_never_matches():
    assert not _peer_is_trusted_proxy("172.20.0.5", [])
    assert not _peer_is_trusted_proxy("", ["172.16.0.0/12"])


def test_malformed_entry_falls_back_to_string():
    assert _peer_is_trusted_proxy("not-an-ip", ["not-an-ip"])


# ── get_client_ip ────────────────────────────────────────────────────


def test_trusted_peer_reads_x_real_ip():
    """nginx-set X-Real-IP is the true peer; client XFF prefix is ignored."""
    req = _req("172.20.0.2", {"X-Real-IP": "203.0.113.9", "X-Forwarded-For": "1.2.3.4"})
    with _with_trusted(["172.16.0.0/12"]):
        assert get_client_ip(req) == "203.0.113.9"


def test_untrusted_peer_returns_peer_not_headers():
    """A direct public caller cannot spoof via X-Real-IP/XFF headers."""
    req = _req("203.0.113.50", {"X-Real-IP": "9.9.9.9", "X-Forwarded-For": "1.1.1.1"})
    with _with_trusted(["172.16.0.0/12"]):
        assert get_client_ip(req) == "203.0.113.50"


def test_trusted_peer_no_real_ip_uses_rightmost_xff():
    """Without X-Real-IP, take the hop nginx appended (rightmost), not [0]."""
    req = _req("172.20.0.2", {"X-Forwarded-For": "1.2.3.4, 203.0.113.9"})
    with _with_trusted(["172.16.0.0/12"]):
        assert get_client_ip(req) == "203.0.113.9"


def test_no_trusted_config_returns_peer():
    req = _req("172.20.0.2", {"X-Real-IP": "203.0.113.9"})
    with _with_trusted([]):
        assert get_client_ip(req) == "172.20.0.2"
