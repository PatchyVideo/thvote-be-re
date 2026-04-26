"""Contract: VoterFE JSON shape matches Rust voter-fe byte-for-byte."""

from __future__ import annotations

from datetime import UTC, datetime

from src.apps.user.schemas import VoterFE


def test_voter_fe_serializes_with_exact_rust_keys() -> None:
    fe = VoterFE(
        username="alice",
        pfp="https://cdn/pic.jpg",
        password=True,
        phone="13800000000",
        email="alice@example.com",
        thbwiki=False,
        patchyvideo=False,
        created_at=datetime(2026, 4, 1, 12, 0, 0, tzinfo=UTC),
    )
    payload = fe.model_dump(mode="json")

    assert set(payload.keys()) == {
        "username",
        "pfp",
        "password",
        "phone",
        "email",
        "thbwiki",
        "patchyvideo",
        "created_at",
    }
    assert payload["thbwiki"] is False
    assert payload["patchyvideo"] is False
    assert payload["password"] is True


def test_voter_fe_optional_fields_serialize_as_null() -> None:
    fe = VoterFE(
        username=None,
        pfp=None,
        password=False,
        phone=None,
        email=None,
        created_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    payload = fe.model_dump(mode="json")
    for key in ("username", "pfp", "phone", "email"):
        assert payload[key] is None
