"""Unit tests for ``src.common.crypto``.

Cover the PII encryption primitives: roundtrip, AAD binding, blind-index
determinism/provider binding, DEK presence/length fail-fast, fingerprint and
the /24 prefix helper.
"""

from __future__ import annotations

import base64
import os

import pytest
from cryptography.exceptions import InvalidTag

from src.common import crypto


@pytest.fixture
def fresh_dek(tmp_path, monkeypatch):
    """Point the module at a throwaway DEK and reset its key caches."""
    dek = base64.b64encode(os.urandom(32)).decode()
    dek_file = tmp_path / "pii_dek"
    dek_file.write_text(dek, encoding="utf-8")
    monkeypatch.setattr(crypto, "DEK_PATH", dek_file)
    crypto._dek.cache_clear()
    crypto._content_key.cache_clear()
    crypto._index_key.cache_clear()
    return dek_file


def test_encrypt_roundtrip(fresh_dek):
    aad = crypto.aad_for("user_identity", "subject", "u1")
    blob = crypto.encrypt("alice@example.com", aad)
    assert isinstance(blob, bytes)
    assert blob[:1] == crypto.VERSION
    assert crypto.decrypt(blob, aad) == "alice@example.com"


def test_encrypt_empty_returns_none(fresh_dek):
    assert crypto.encrypt("", b"aad") is None
    assert crypto.encrypt(None, b"aad") is None
    assert crypto.decrypt(None, b"aad") is None


def test_aad_mismatch_fails(fresh_dek):
    blob = crypto.encrypt("alice@example.com", crypto.aad_for("t", "c", "u1"))
    with pytest.raises(InvalidTag):
        crypto.decrypt(blob, crypto.aad_for("t", "c", "u2"))


def test_blind_index_deterministic(fresh_dek):
    a = crypto.blind_index("email", "alice@example.com")
    b = crypto.blind_index("email", "alice@example.com")
    assert a == b
    assert isinstance(a, bytes) and len(a) == 32


def test_blind_index_provider_and_subject_bound(fresh_dek):
    base = crypto.blind_index("email", "alice@example.com")
    assert base != crypto.blind_index("phone", "alice@example.com")
    assert base != crypto.blind_index("email", "bob@example.com")


def test_missing_dek_raises(monkeypatch):
    crypto._dek.cache_clear()
    crypto._content_key.cache_clear()
    crypto._index_key.cache_clear()
    monkeypatch.setattr(crypto, "DEK_PATH", crypto.DEK_PATH / "does-not-exist")
    with pytest.raises(RuntimeError, match="missing"):
        crypto._dek()


def test_bad_length_dek_raises(tmp_path, monkeypatch):
    bad = tmp_path / "bad_dek"
    bad.write_text(base64.b64encode(b"short").decode(), encoding="utf-8")
    crypto._dek.cache_clear()
    crypto._content_key.cache_clear()
    crypto._index_key.cache_clear()
    monkeypatch.setattr(crypto, "DEK_PATH", bad)
    with pytest.raises(RuntimeError, match="length"):
        crypto._dek()


def test_fingerprint_stable(fresh_dek):
    assert crypto.fingerprint() == crypto.fingerprint()
    assert len(crypto.fingerprint()) == 8


def test_ip_prefix():
    assert crypto.ip_prefix("203.0.113.7") == "203.0.113.0/24"
    assert crypto.ip_prefix("") is None
    assert crypto.ip_prefix("not-an-ip") is None
