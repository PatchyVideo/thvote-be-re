"""Unit tests for src/apps/user/identity.py — provider enum, subject
normalisation and the vote-eligibility provider set."""

from __future__ import annotations

import pytest

from src.apps.user.identity import (
    IdentityProvider,
    normalize_subject,
    vote_eligible_providers,
)


def test_provider_values_are_stable_strings() -> None:
    # These strings are persisted in user_identity.provider and guarded by a
    # CHECK constraint — renaming one is a schema change.
    assert {p.value for p in IdentityProvider} == {"email", "phone", "qq", "thbwiki"}
    assert str(IdentityProvider.EMAIL) == "email"


@pytest.mark.parametrize(
    "provider, raw, expected",
    [
        (IdentityProvider.EMAIL, "  Alice@Example.COM ", "alice@example.com"),
        (IdentityProvider.PHONE, " 13800000001 ", "13800000001"),
        (IdentityProvider.QQ, "OpenID-MixedCase", "OpenID-MixedCase"),
        (IdentityProvider.THBWIKI, " 42 ", " 42 "),
    ],
)
def test_normalize_subject(provider, raw, expected) -> None:
    assert normalize_subject(provider, raw) == expected


def test_normalize_subject_rejects_empty() -> None:
    with pytest.raises(ValueError):
        normalize_subject(IdentityProvider.EMAIL, "   ")


def test_vote_eligible_providers_default(monkeypatch) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr(
        "src.apps.user.identity.get_settings",
        lambda: SimpleNamespace(vote_eligible_providers=["email", "phone"]),
    )
    assert vote_eligible_providers() == {IdentityProvider.EMAIL, IdentityProvider.PHONE}


def test_vote_eligible_providers_ignores_unknown_values(monkeypatch) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr(
        "src.apps.user.identity.get_settings",
        lambda: SimpleNamespace(vote_eligible_providers=["phone", "bogus"]),
    )
    assert vote_eligible_providers() == {IdentityProvider.PHONE}
