"""Identity-provider rules shared by the user module.

Single home for:
- ``IdentityProvider``: the closed set of authentication sources stored in
  ``user_identity.provider`` (mirrored by a CHECK constraint on the table).
- ``normalize_subject``: how a raw identifier becomes the canonical
  ``subject`` string used for uniqueness and lookup.
- ``vote_eligible_providers``: which providers' verified identities grant a
  vote token (configurable; see spec §4 / §11).

Adding a provider = add an enum member here + widen the CHECK constraint in
a migration.  Nothing else in the codebase should branch on provider names.
"""

from __future__ import annotations

from enum import StrEnum

from src.common.config import get_settings


class IdentityProvider(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    QQ = "qq"
    THBWIKI = "thbwiki"


PROVIDER_VALUES: tuple[str, ...] = tuple(p.value for p in IdentityProvider)


def normalize_subject(provider: IdentityProvider, raw: str) -> str:
    """Return the canonical subject for *raw* under *provider*.

    - email: trimmed + lower-cased (the legacy Rust gateway lower-cased too).
    - phone: trimmed.
    - qq / thbwiki: opaque provider-issued ids, kept verbatim.

    Raises ``ValueError`` on an empty subject so a blank never reaches the
    unique constraint.
    """
    if provider in (IdentityProvider.EMAIL, IdentityProvider.PHONE):
        subject = raw.strip()
        if provider is IdentityProvider.EMAIL:
            subject = subject.lower()
    else:
        subject = raw
    if not subject:
        raise ValueError(f"empty subject for provider {provider.value}")
    return subject


def vote_eligible_providers() -> set[IdentityProvider]:
    """Providers whose verified identity grants a vote token.

    Read from ``settings.vote_eligible_providers`` (default email + phone,
    matching the legacy Rust rule).  Unknown names are ignored so a typo in
    Nacos narrows eligibility instead of crashing login.
    """
    configured = get_settings().vote_eligible_providers
    result: set[IdentityProvider] = set()
    for name in configured:
        try:
            result.add(IdentityProvider(name.strip().lower()))
        except ValueError:
            continue
    return result
