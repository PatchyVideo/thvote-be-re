"""Field-level encryption and blind indexing for PII columns.

One DEK (32 random bytes, base64-encoded) is read from ``PII_DEK_PATH`` and
split via HKDF into two independent keys:

- ``content_key`` — AES-256-GCM for the ciphertext columns;
- ``index_key``   — HMAC-SHA256 for deterministic blind indices.

Splitting them means a database dump cannot brute-force the phone-number space
against the content key; the index key alone only enables equality lookup.

Ciphertext layout: ``version(1B) || nonce(12B) || ciphertext || tag(16B)``.
AAD binds a ciphertext to its row: ``"{table}.{column}:{row_id}"``.

The DEK is deliberately *not* read from ``Settings``: it lives in a Docker
secret (``/run/secrets/pii_dek``) and must never appear in Nacos, ``.env``,
git or logs.  ``fingerprint()`` returns a short one-way tag safe to log so an
operator can confirm the import job and the serving process share the same DEK.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import os
from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

VERSION = b"\x01"
DEK_PATH = Path(os.getenv("PII_DEK_PATH", "/run/secrets/pii_dek"))

_CONTENT_INFO = b"thvote-pii-content"
_INDEX_INFO = b"thvote-pii-index"
_FINGERPRINT_INFO = b"thvote-dek-fingerprint"


@lru_cache(maxsize=1)
def _dek() -> bytes:
    if not DEK_PATH.exists():
        raise RuntimeError(f"PII DEK missing: {DEK_PATH}")
    raw = base64.b64decode(DEK_PATH.read_bytes().strip())
    if len(raw) != 32:
        raise RuntimeError(f"PII DEK bad length: {len(raw)}")
    return raw


@lru_cache(maxsize=1)
def _content_key() -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=_CONTENT_INFO
    ).derive(_dek())


@lru_cache(maxsize=1)
def _index_key() -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=_INDEX_INFO
    ).derive(_dek())


def fingerprint() -> str:
    """Short one-way tag of the loaded DEK, safe to log."""
    return hmac.new(_dek(), _FINGERPRINT_INFO, hashlib.sha256).hexdigest()[:8]


def aad_for(table: str, column: str, row_id: str) -> bytes:
    """AAD binding ciphertext to its row: ``table.column:row_id``."""
    return f"{table}.{column}:{row_id}".encode()


def encrypt(plaintext: str | None, aad: bytes) -> bytes | None:
    """Encrypt *plaintext* under the content key, bound to *aad*."""
    if not plaintext:
        return None
    nonce = os.urandom(12)
    ciphertext = AESGCM(_content_key()).encrypt(nonce, plaintext.encode(), aad)
    return VERSION + nonce + ciphertext


def decrypt(blob: bytes | None, aad: bytes) -> str | None:
    """Decrypt *blob*; raises on a wrong version or AAD mismatch."""
    if not blob:
        return None
    if blob[:1] != VERSION:
        raise ValueError("unsupported ciphertext version")
    return AESGCM(_content_key()).decrypt(blob[1:13], blob[13:], aad).decode()


def blind_index(provider: str, subject: str) -> bytes | None:
    """Deterministic HMAC index over the canonical ``(provider, subject)``.

    *subject* must already be canonical (``normalize_subject``) — the same
    value the DAO receives for lookups — so writes and reads agree.
    """
    if not subject:
        return None
    message = f"{provider}:{subject}".encode()
    return hmac.new(_index_key(), message, hashlib.sha256).digest()


def ip_prefix(ip: str) -> str | None:
    """Return the /24 network of an IPv4 address as a CIDR string.

    Coarse bucket for range queries (anti-vote-farming clustering) that does
    not require decrypting the full address.  ``None`` for blank/non-IPv4.
    """
    if not ip:
        return None
    try:
        return str(ipaddress.ip_network(f"{ip.strip()}/24", strict=False))
    except ValueError:
        return None
