"""Verify VoterFE serialization byte-aligns with Rust user-manager."""

from __future__ import annotations

from datetime import UTC, datetime

from src.apps.user.schemas import VoterFE, voter_fe_from_user


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


class _UserStub:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_voter_fe_from_user_password_flag_reflects_hash_presence() -> None:
    user_with_password = _UserStub(
        nickname="alice",
        pfp=None,
        password_hash="$argon2id$abc",
        phone_number=None,
        email="a@example.com",
        register_date=datetime(2026, 1, 1, tzinfo=UTC),
    )
    user_no_password = _UserStub(
        nickname="bob",
        pfp=None,
        password_hash=None,
        phone_number="13800000000",
        email=None,
        register_date=datetime(2026, 1, 2, tzinfo=UTC),
    )

    fe_a = voter_fe_from_user(user_with_password)
    fe_b = voter_fe_from_user(user_no_password)

    assert fe_a.password is True
    assert fe_a.username == "alice"
    assert fe_a.email == "a@example.com"
    assert fe_b.password is False
    assert fe_b.username == "bob"
    assert fe_b.phone == "13800000000"


def test_meta_keeps_rust_typo() -> None:
    from src.apps.user.schemas import Meta

    m = Meta(user_ip="127.0.0.1", additional_fingureprint="fp")
    assert m.additional_fingureprint == "fp"
    assert "additional_fingureprint" in Meta.model_fields
