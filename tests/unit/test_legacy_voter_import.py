"""Pure planning helpers of the legacy voter importer.

No database and no real dump: these tests pin normalisation, duplicate
winner selection (D4-A), test-account filtering and invalid-email skipping.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scripts.import_legacy_voters import (
    LegacyVoter,
    clean_ip,
    normalize_voter,
    plan_import,
)
from src.db_model.legacy_user_mapping import (
    MAPPING_ROLE_VALUES,
    LegacyUserMapping,
)

BASE = datetime(2022, 1, 1, tzinfo=UTC)


def _voter(
    legacy_id: str,
    *,
    email: str | None = None,
    phone: str | None = None,
    password_hash: str | None = "$argon2i$v=19$m=4096,t=3,p=1$x$y",
    salt: str | None = None,
    created_at: datetime = BASE,
    verified: bool = True,
) -> LegacyVoter:
    return LegacyVoter(
        legacy_id=legacy_id,
        email=email,
        email_verified=verified,
        phone=phone,
        phone_verified=verified,
        qq_openid=None,
        thbwiki_uid=None,
        nickname=None,
        pfp=None,
        password_hash=password_hash,
        legacy_salt=salt,
        removed=False,
        created_at=created_at,
        signup_ip="1.1.1.1",
    )


def test_clean_ip_strips_legacy_quote() -> None:
    assert clean_ip("1.1.1.1'") == "1.1.1.1"
    assert clean_ip("  1.1.1.1'' ") == "1.1.1.1"
    assert clean_ip(None) == ""


def test_normalize_lowercases_email_and_keeps_salt_only_for_bcrypt() -> None:
    doc = {
        "_id": "619cefcbd45288b3c1a382f1",
        "email": " Foo@Example.COM ",
        "email_verified": True,
        "phone": " 13800000000 ",
        "phone_verified": True,
        "password_hashed": "$2y$10$abcdefghijklmnopqrstuv",
        "salt": "GBtTzcxg",
        "created_at": datetime(2021, 11, 23, 13, 42, 35),
        "signup_ip": "1.1.1.1'",
    }
    voter = normalize_voter(doc)
    assert voter.email == "foo@example.com"
    assert voter.phone == "13800000000"
    assert voter.legacy_salt == "GBtTzcxg"
    assert voter.signup_ip == "1.1.1.1"
    assert voter.created_at.tzinfo is not None

    doc["password_hashed"] = "$argon2i$v=19$m=4096,t=3,p=1$x$y"
    assert normalize_voter(doc).legacy_salt is None


def test_duplicate_email_picks_latest_activity_not_latest_created_at() -> None:
    old = _voter("old", email="a@example.com", created_at=BASE)
    new = _voter(
        "new",
        email="a@example.com",
        created_at=BASE + timedelta(days=30),
        password_hash="$2y$10$new",
        salt="salt1234",
    )
    last_activity = {"old": BASE + timedelta(days=100)}
    plan = plan_import([new, old], last_activity, include_test_accounts=True)
    assert [v.legacy_id for v in plan.winners] == ["old"]
    assert plan.losers == {"new": "old"}
    assert plan.duplicate_count == 1


def test_duplicate_without_logs_falls_back_to_oldest_registration() -> None:
    old = _voter("old", email="a@example.com", created_at=BASE)
    new = _voter(
        "new", email="a@example.com", created_at=BASE + timedelta(days=1)
    )
    plan = plan_import([new, old], {}, include_test_accounts=True)
    assert [v.legacy_id for v in plan.winners] == ["old"]


def test_phone_only_records_are_kept() -> None:
    plan = plan_import(
        [_voter("p1", phone="13800000001")],
        {},
        include_test_accounts=True,
    )
    assert [v.legacy_id for v in plan.winners] == ["p1"]


def test_missing_phone_is_merged_from_loser() -> None:
    winner = _voter("winner", email="a@example.com")
    loser = _voter("loser", email="a@example.com", phone="13800000002")
    plan = plan_import([winner, loser], {"winner": BASE}, include_test_accounts=True)
    assert plan.winners[0].phone == "13800000002"
    assert ("winner", "phone", "loser") in plan.merged_fields


def test_test_accounts_are_filtered_unless_requested() -> None:
    test = _voter("t", email="votetester1@touhou.ai")
    prod = plan_import([test], {}, include_test_accounts=False)
    assert prod.winners == []
    assert [v.legacy_id for v in prod.test_skipped] == ["t"]

    included = plan_import([test], {}, include_test_accounts=True)
    assert [v.legacy_id for v in included.winners] == ["t"]


def test_invalid_email_is_skipped_entirely() -> None:
    bad = _voter("bad", email="1051119194@qq.com144", phone="13800000003")
    plan = plan_import([bad], {}, include_test_accounts=True)
    assert plan.winners == []
    assert [v.legacy_id for v in plan.invalid] == ["bad"]


def test_manual_review_flags_differing_hashes_without_logs() -> None:
    a = _voter("a", email="a@example.com", password_hash="$2y$10$a", salt="salt1234")
    b = _voter("b", email="a@example.com", password_hash="$2y$10$b", salt="salt1234")
    plan = plan_import([a, b], {}, include_test_accounts=True)
    assert [v.legacy_id for v in plan.manual_review] == ["a"]


def test_mapping_role_column_fits_every_role() -> None:
    """Regression for 0020: VARCHAR(16) could not hold conflict_existing."""
    column_length = LegacyUserMapping.__table__.c.role.type.length
    assert max(len(role) for role in MAPPING_ROLE_VALUES) <= column_length
