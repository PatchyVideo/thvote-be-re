"""Verify VoterFE serialization byte-aligns with Rust user-manager."""

from __future__ import annotations

from datetime import UTC, datetime

from src.apps.user.schemas import VoterFE, voter_fe_from_user
from tests.helpers.users import build_user


def test_voter_fe_has_exact_rust_field_set() -> None:
    fields = set(VoterFE.model_fields.keys())
    expected = {
        "username",
        "pfp",
        "password",
        "phone",
        "email",
        "thbwiki",
        "patchyvideo",
        "created_at",
    }
    assert fields == expected


def test_voter_fe_thbwiki_and_patchyvideo_default_false() -> None:
    fe = VoterFE(password=False, created_at=datetime.now(UTC))
    assert fe.thbwiki is False
    assert fe.patchyvideo is False


def test_voter_fe_from_user_maps_identities_and_password_flag() -> None:
    user_with_password = build_user(
        nickname="alice", email="a@example.com", password="pw", thbwiki="42"
    )
    user_no_password = build_user(nickname="bob", phone="13800000000")

    fe_a = voter_fe_from_user(user_with_password)
    fe_b = voter_fe_from_user(user_no_password)

    assert fe_a.password is True
    assert fe_a.username == "alice"
    assert fe_a.email == "a@example.com"
    assert fe_a.phone is None
    assert fe_a.thbwiki is True
    assert fe_a.patchyvideo is False
    assert fe_b.password is False
    assert fe_b.username == "bob"
    assert fe_b.phone == "13800000000"
    assert fe_b.email is None
    assert fe_b.thbwiki is False


def test_meta_keeps_rust_typo() -> None:
    from src.apps.user.schemas import Meta

    m = Meta(user_ip="127.0.0.1", additional_fingureprint="fp")
    assert m.additional_fingureprint == "fp"
    assert "additional_fingureprint" in Meta.model_fields
