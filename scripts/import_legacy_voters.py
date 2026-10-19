#!/usr/bin/env python3
"""Import the legacy Mongo ``thvote_users.voters`` dump into PostgreSQL.

Design: docs/migration/legacy-voter-import.md (decision D1-A/D2-B/D3-A/D4-A).

What it does
------------
* streams ``voters.bson`` (one-off, ~122k docs);
* normalises e-mail/phone, strips the legacy trailing quote from ``signup_ip``;
* merges duplicate e-mail/phone records, choosing the one with the latest
  ``voter_logs`` activity (read-only — logs themselves are NOT imported);
* creates ``user`` (UUID4) + ``user_identity`` + ``legacy_user_mapping``;
* keeps an existing account when an identity already exists (D8-A).

Usage
-----
    python scripts/import_legacy_voters.py --dump-dir ../thvote_users \\
        --include-test-accounts --report-dir /tmp/thvote-import --preflight

    python scripts/import_legacy_voters.py ... --commit --batch-id <uuid>

``--preflight`` is the default: it reads the dump and the target database but
never writes.  ``--commit`` is the only mode that inserts rows.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from bson import decode_file_iter
from pydantic import EmailStr, TypeAdapter
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.common.config import get_settings  # noqa: E402
from src.common.database import normalize_async_database_url  # noqa: E402
from src.db_model.legacy_user_mapping import LegacyUserMapping  # noqa: E402
from src.db_model.user import User  # noqa: E402
from src.db_model.user_identity import UserIdentity  # noqa: E402

logger = logging.getLogger("import_legacy_voters")

# 测试账号：测试库用 --include-test-accounts 导入，生产默认过滤。
TEST_ACCOUNT_EMAILS = frozenset(
    f"votetester{i}@touhou.ai" for i in range(1, 6)
)

_EMAIL_ADAPTER = TypeAdapter(EmailStr)
_MIN_ACTIVITY = datetime.min.replace(tzinfo=UTC)


# ── data model ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class LegacyVoter:
    """One normalised ``voters`` document."""

    legacy_id: str
    email: str | None
    email_verified: bool
    phone: str | None
    phone_verified: bool
    qq_openid: str | None
    thbwiki_uid: str | None
    nickname: str | None
    pfp: str | None
    password_hash: str | None
    legacy_salt: str | None
    removed: bool
    created_at: datetime
    signup_ip: str

    @property
    def is_bcrypt(self) -> bool:
        return bool(self.password_hash and self.password_hash.startswith("$2"))


@dataclass
class ImportPlan:
    """Result of the pure, DB-free planning phase."""

    winners: list[LegacyVoter] = field(default_factory=list)
    # loser legacy id -> winner legacy id
    losers: dict[str, str] = field(default_factory=dict)
    # winner legacy id -> [loser legacy ids]
    losers_by_winner: dict[str, list[str]] = field(default_factory=dict)
    invalid: list[LegacyVoter] = field(default_factory=list)
    test_skipped: list[LegacyVoter] = field(default_factory=list)
    # (winner id, field, loser id)
    merged_fields: list[tuple[str, str, str]] = field(default_factory=list)
    manual_review: list[LegacyVoter] = field(default_factory=list)

    @property
    def duplicate_count(self) -> int:
        return len(self.losers)


@dataclass
class Stats:
    raw: int = 0
    invalid: int = 0
    test_skipped: int = 0
    winners: int = 0
    duplicates: int = 0
    already_mapped: int = 0
    users_created: int = 0
    identities_created: int = 0
    mappings_created: int = 0
    conflicts_existing: int = 0
    multi_conflicts: int = 0
    errors: int = 0


# ── normalisation / planning (pure functions, unit-tested) ───────────


def clean_ip(raw: Any) -> str:
    """Strip whitespace and the legacy trailing ``'`` seen in the dump."""
    if not isinstance(raw, str):
        return ""
    return raw.strip().rstrip("'").strip()[:64]


def _clean_str(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    return value or None


def is_valid_email(email: str) -> bool:
    try:
        _EMAIL_ADAPTER.validate_python(email)
    except Exception:  # noqa: BLE001 - pydantic raises several subclasses
        return False
    return True


def _aware(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def normalize_voter(doc: dict[str, Any]) -> LegacyVoter:
    """Turn one BSON document into a :class:`LegacyVoter`."""
    email = _clean_str(doc.get("email"))
    if email is not None:
        email = email.lower()
    phone = _clean_str(doc.get("phone"))
    password_hash = _clean_str(doc.get("password_hashed"))
    salt = _clean_str(doc.get("salt"))
    # 旧库只有 bcrypt 行带 salt；argon2 行即使有残留也不走 bcrypt 分支。
    if not (password_hash and password_hash.startswith("$2")):
        salt = None
    created_at = _aware(doc.get("created_at")) or datetime.now(UTC)
    return LegacyVoter(
        legacy_id=str(doc["_id"]),
        email=email,
        email_verified=bool(doc.get("email_verified")),
        phone=phone,
        phone_verified=bool(doc.get("phone_verified")),
        qq_openid=_clean_str(doc.get("qq_openid")),
        thbwiki_uid=_clean_str(doc.get("thbwiki_uid")),
        nickname=_clean_str(doc.get("nickname")),
        pfp=_clean_str(doc.get("pfp")),
        password_hash=password_hash,
        legacy_salt=salt,
        removed=bool(doc.get("removed")),
        created_at=created_at,
        signup_ip=clean_ip(doc.get("signup_ip")),
    )


def iter_voters(path: Path) -> Iterable[dict[str, Any]]:
    """Stream documents out of a BSON file without loading it whole."""
    with path.open("rb") as handle:
        yield from decode_file_iter(handle)


def load_last_activity(path: Path) -> dict[str, datetime]:
    """Return ``legacy voter id -> max(created_at)`` from ``voter_logs``.

    Read-only: this is the D4-A winner criterion.  The logs themselves are
    deliberately *not* imported (decision D6-B).
    """
    last: dict[str, datetime] = {}
    for doc in iter_voters(path):
        for key, value in doc.items():
            if key == "_id" or not isinstance(value, dict):
                continue
            uid = value.get("uid")
            ts = _aware(value.get("created_at"))
            if uid is None or ts is None:
                continue
            legacy_id = str(uid)
            current = last.get(legacy_id)
            if current is None or ts > current:
                last[legacy_id] = ts
    return last


def _merge_missing(
    winner: LegacyVoter,
    losers: list[LegacyVoter],
) -> tuple[LegacyVoter, list[tuple[str, str]]]:
    """Fill fields the winner lacks; returns (winner, [(field, loser_id)])."""
    updates: dict[str, Any] = {}
    merged: list[tuple[str, str]] = []
    for loser in losers:
        for field_name in ("phone", "qq_openid", "thbwiki_uid", "pfp"):
            if getattr(winner, field_name) is None:
                candidate = getattr(loser, field_name)
                if candidate is not None and field_name not in updates:
                    updates[field_name] = candidate
                    merged.append((field_name, loser.legacy_id))
        if not winner.email_verified and loser.email_verified:
            updates["email_verified"] = True
        if not winner.phone_verified and loser.phone_verified:
            updates["phone_verified"] = True
    return (replace(winner, **updates) if updates else winner), merged


def _sort_key(voter: LegacyVoter, last_activity: dict[str, datetime]):
    # latest activity first, then oldest registration, then smallest id
    return (
        -last_activity.get(voter.legacy_id, _MIN_ACTIVITY).timestamp(),
        voter.created_at,
        voter.legacy_id,
    )


def plan_import(
    voters: Iterable[LegacyVoter],
    last_activity: dict[str, datetime],
    *,
    include_test_accounts: bool,
) -> ImportPlan:
    """Group, filter and pick winners.  Pure — no I/O."""
    plan = ImportPlan()
    email_groups: dict[str, list[LegacyVoter]] = defaultdict(list)
    phone_groups: dict[str, list[LegacyVoter]] = defaultdict(list)

    for voter in voters:
        if voter.email is not None and not is_valid_email(voter.email):
            plan.invalid.append(voter)
            continue
        if not include_test_accounts and voter.email in TEST_ACCOUNT_EMAILS:
            plan.test_skipped.append(voter)
            continue
        if voter.email is not None:
            email_groups[voter.email].append(voter)
        else:
            # 纯手机号记录按手机号归组，防御性处理（当前 dump 手机号无重复）。
            phone_groups[voter.phone or ""].append(voter)

    groups = list(email_groups.values()) + list(phone_groups.values())
    for group in groups:
        ordered = sorted(group, key=lambda v: _sort_key(v, last_activity))
        winner = ordered[0]
        winner, merged = _merge_missing(winner, ordered[1:])
        plan.winners.append(winner)
        for field_name, loser_id in merged:
            plan.merged_fields.append((winner.legacy_id, field_name, loser_id))
        loser_ids = [loser.legacy_id for loser in ordered[1:]]
        plan.losers_by_winner[winner.legacy_id] = loser_ids
        for loser_id in loser_ids:
            plan.losers[loser_id] = winner.legacy_id
        if len(ordered) > 1:
            hashes = {v.password_hash for v in ordered}
            if len(hashes) > 1 and all(
                v.legacy_id not in last_activity for v in ordered
            ):
                plan.manual_review.append(winner)
    return plan


# ── database phase ───────────────────────────────────────────────────


def _identity_rows(voter: LegacyVoter, user_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for provider, subject, verified in (
        ("email", voter.email, voter.email_verified),
        ("phone", voter.phone, voter.phone_verified),
        ("qq", voter.qq_openid, True),
        ("thbwiki", voter.thbwiki_uid, True),
    ):
        if subject is None:
            continue
        rows.append(
            {
                "user_id": user_id,
                "provider": provider,
                "subject": subject,
                "verified": bool(verified),
                "verified_at": voter.created_at if verified else None,
                "created_at": voter.created_at,
                "created_ip": voter.signup_ip,
                "created_device_id": "",
                "last_login_at": None,
            }
        )
    return rows


def _user_row(voter: LegacyVoter, user_id: str) -> dict[str, Any]:
    return {
        "id": user_id,
        "nickname": voter.nickname,
        "pfp": voter.pfp,
        "password_hash": voter.password_hash,
        "legacy_salt": voter.legacy_salt if voter.is_bcrypt else None,
        "removed": voter.removed,
        "register_date": voter.created_at,
        "register_ip_address": voter.signup_ip,
        "register_device_id": "",
    }


async def _existing_identities(session, voters: list[LegacyVoter]) -> dict:
    emails = [v.email for v in voters if v.email]
    phones = [v.phone for v in voters if v.phone]
    found: dict[tuple[str, str], str] = {}
    if emails:
        result = await session.execute(
            select(
                UserIdentity.provider,
                UserIdentity.subject,
                UserIdentity.user_id,
            ).where(
                UserIdentity.provider == "email",
                UserIdentity.subject.in_(emails),
            )
        )
        for provider, subject, user_id in result:
            found[(provider, subject)] = user_id
    if phones:
        result = await session.execute(
            select(
                UserIdentity.provider,
                UserIdentity.subject,
                UserIdentity.user_id,
            ).where(
                UserIdentity.provider == "phone",
                UserIdentity.subject.in_(phones),
            )
        )
        for provider, subject, user_id in result:
            found[(provider, subject)] = user_id
    return found


async def _load_mapped(session, *, commit: bool) -> set[str]:
    """Return already-imported legacy ids.

    Preflight tolerates a database where migration 0020 has not run yet
    (the mapping table does not exist); commit mode lets the error surface.
    """
    try:
        result = await session.execute(
            select(LegacyUserMapping.legacy_object_id)
        )
    except Exception:  # noqa: BLE001 - only preflight is allowed to continue
        if commit:
            raise
        logger.warning("legacy_user_mapping missing; preflight assumes empty")
        await session.rollback()
        return set()
    return {row[0] for row in result}


def _classify(
    voter: LegacyVoter, existing: dict[tuple[str, str], str]
) -> tuple[str, str | None]:
    """Return (kind, owner_user_id).  kind ∈ create / conflict / multi."""
    owners: dict[str, str] = {}
    if voter.email:
        owner = existing.get(("email", voter.email))
        if owner:
            owners[owner] = "email"
    if voter.phone:
        owner = existing.get(("phone", voter.phone))
        if owner:
            owners[owner] = "phone"
    if not owners:
        return "create", None
    if len(owners) > 1:
        return "multi", None
    return "conflict", next(iter(owners))


async def _process_batch(
    session,
    winners: list[LegacyVoter],
    plan: ImportPlan,
    existing: dict[tuple[str, str], str],
    mapped: set[str],
    batch_id: str,
    stats: Stats,
    conflicts: list[dict[str, Any]],
    *,
    commit: bool,
) -> None:
    users: list[dict[str, Any]] = []
    identities: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []

    for voter in winners:
        if voter.legacy_id in mapped:
            stats.already_mapped += 1
            continue
        kind, owner = _classify(voter, existing)
        if kind == "multi":
            stats.multi_conflicts += 1
            conflicts.append(
                {
                    "legacy_id": voter.legacy_id,
                    "reason": "multi_owner",
                    "email": mask_email(voter.email),
                    "phone": mask_phone(voter.phone),
                    "existing_user_id": "",
                }
            )
            continue
        if kind == "conflict":
            stats.conflicts_existing += 1
            conflicts.append(
                {
                    "legacy_id": voter.legacy_id,
                    "reason": "identity_already_exists",
                    "email": mask_email(voter.email),
                    "phone": mask_phone(voter.phone),
                    "existing_user_id": owner,
                }
            )
            for legacy_id in [voter.legacy_id, *plan.losers_by_winner.get(
                voter.legacy_id, []
            )]:
                if legacy_id in mapped:
                    continue
                mappings.append(
                    {
                        "legacy_object_id": legacy_id,
                        "user_id": owner,
                        "role": "conflict_existing",
                        "batch_id": batch_id,
                    }
                )
                mapped.add(legacy_id)
            continue

        user_id = str(uuid.uuid4())
        users.append(_user_row(voter, user_id))
        identities.extend(_identity_rows(voter, user_id))
        for legacy_id, role in [
            (voter.legacy_id, "primary"),
            *[(lid, "duplicate") for lid in plan.losers_by_winner.get(
                voter.legacy_id, []
            )],
        ]:
            if legacy_id in mapped:
                continue
            mappings.append(
                {
                    "legacy_object_id": legacy_id,
                    "user_id": user_id,
                    "role": role,
                    "batch_id": batch_id,
                }
            )
            mapped.add(legacy_id)

    stats.users_created += len(users)
    stats.identities_created += len(identities)
    stats.mappings_created += len(mappings)

    if not commit:
        return
    if users:
        await session.execute(insert(User), users)
    if identities:
        await session.execute(insert(UserIdentity), identities)
    if mappings:
        await session.execute(insert(LegacyUserMapping), mappings)


# ── reports ──────────────────────────────────────────────────────────


def mask_email(value: str | None) -> str:
    if not value:
        return ""
    local, _, domain = value.partition("@")
    return f"{local[:1]}***@{domain}"


def mask_phone(value: str | None) -> str:
    if not value:
        return ""
    return f"{value[:3]}****{value[-2:]}"


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_reports(
    report_dir: Path,
    *,
    plan: ImportPlan,
    stats: Stats,
    conflicts: list[dict[str, Any]],
    batch_id: str,
    commit: bool,
    duration: float,
) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "batch_id": batch_id,
        "mode": "commit" if commit else "preflight",
        "duration_seconds": round(duration, 1),
        "raw_documents": stats.raw,
        "invalid_email_skipped": stats.invalid,
        "test_accounts_skipped": stats.test_skipped,
        "winners": stats.winners,
        "duplicates_merged": stats.duplicates,
        "already_mapped": stats.already_mapped,
        "users_created": stats.users_created,
        "identities_created": stats.identities_created,
        "mappings_created": stats.mappings_created,
        "conflicts_existing": stats.conflicts_existing,
        "multi_conflicts": stats.multi_conflicts,
        "errors": stats.errors,
    }
    (report_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_csv(
        report_dir / "conflicts.csv",
        conflicts,
        ["legacy_id", "reason", "email", "phone", "existing_user_id"],
    )
    _write_csv(
        report_dir / "invalid_email.csv",
        [
            {
                "legacy_id": v.legacy_id,
                "email": v.email,
                "phone": mask_phone(v.phone),
                "nickname": v.nickname,
            }
            for v in plan.invalid
        ],
        ["legacy_id", "email", "phone", "nickname"],
    )
    _write_csv(
        report_dir / "test_accounts.csv",
        [
            {"legacy_id": v.legacy_id, "email": v.email, "nickname": v.nickname}
            for v in plan.test_skipped
        ],
        ["legacy_id", "email", "nickname"],
    )
    _write_csv(
        report_dir / "duplicates.csv",
        [
            {"loser_legacy_id": loser, "winner_legacy_id": winner}
            for loser, winner in plan.losers.items()
        ],
        ["loser_legacy_id", "winner_legacy_id"],
    )
    _write_csv(
        report_dir / "merged_fields.csv",
        [
            {"winner_legacy_id": w, "field": f, "loser_legacy_id": loser}
            for w, f, loser in plan.merged_fields
        ],
        ["winner_legacy_id", "field", "loser_legacy_id"],
    )
    _write_csv(
        report_dir / "manual_review.csv",
        [
            {"legacy_id": v.legacy_id, "email": mask_email(v.email)}
            for v in plan.manual_review
        ],
        ["legacy_id", "email"],
    )


# ── entrypoint ───────────────────────────────────────────────────────


async def run(
    dump_dir: Path,
    *,
    include_test_accounts: bool,
    commit: bool,
    batch_id: str,
    report_dir: Path,
    batch_size: int,
    limit: int | None,
) -> Stats:
    started = datetime.now(UTC)
    voters: list[LegacyVoter] = []
    for index, doc in enumerate(iter_voters(dump_dir / "voters.bson")):
        if limit is not None and index >= limit:
            break
        voters.append(normalize_voter(doc))
    last_activity = load_last_activity(dump_dir / "voter_logs.bson")
    plan = plan_import(
        voters,
        last_activity,
        include_test_accounts=include_test_accounts,
    )

    stats = Stats(
        raw=len(voters),
        invalid=len(plan.invalid),
        test_skipped=len(plan.test_skipped),
        winners=len(plan.winners),
        duplicates=plan.duplicate_count,
    )
    logger.info(
        "raw=%d winners=%d duplicates=%d invalid=%d test_skipped=%d",
        stats.raw,
        stats.winners,
        stats.duplicates,
        stats.invalid,
        stats.test_skipped,
    )

    settings = get_settings()
    engine = create_async_engine(
        normalize_async_database_url(settings.database_url), echo=False
    )
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    conflicts: list[dict[str, Any]] = []

    try:
        async with session_maker() as session:
            mapped = await _load_mapped(session, commit=commit)
            total = len(plan.winners)
            for start in range(0, total, batch_size):
                chunk = plan.winners[start : start + batch_size]
                existing = await _existing_identities(session, chunk)
                try:
                    await _process_batch(
                        session,
                        chunk,
                        plan,
                        existing,
                        mapped,
                        batch_id,
                        stats,
                        conflicts,
                        commit=commit,
                    )
                    if commit:
                        await session.commit()
                except Exception:
                    await session.rollback()
                    raise
                logger.info(
                    "batch %d/%d users=%d identities=%d mappings=%d",
                    min(start + batch_size, total),
                    total,
                    stats.users_created,
                    stats.identities_created,
                    stats.mappings_created,
                )
    finally:
        await engine.dispose()

    write_reports(
        report_dir,
        plan=plan,
        stats=stats,
        conflicts=conflicts,
        batch_id=batch_id,
        commit=commit,
        duration=(datetime.now(UTC) - started).total_seconds(),
    )
    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dump-dir",
        required=True,
        help="Directory containing voters.bson and voter_logs.bson",
    )
    parser.add_argument(
        "--report-dir",
        default="/tmp/thvote-legacy-import",
        help="Where summary/CSV reports are written",
    )
    parser.add_argument(
        "--batch-id",
        default=None,
        help="Import batch id (default: random UUID4)",
    )
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--include-test-accounts",
        action="store_true",
        help="Import votetester1..5@touhou.ai (test DB only)",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Read-only planning/report mode (default)",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually write to the database (default: preflight only)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.commit and args.preflight:
        parser.error("--commit and --preflight are mutually exclusive")
    dump_dir = Path(args.dump_dir)
    if not (dump_dir / "voters.bson").is_file():
        logger.error("missing %s", dump_dir / "voters.bson")
        return 2
    if not (dump_dir / "voter_logs.bson").is_file():
        logger.error("missing %s", dump_dir / "voter_logs.bson")
        return 2

    batch_id = args.batch_id or str(uuid.uuid4())
    mode = "commit" if args.commit else "preflight"
    logger.info("batch_id=%s mode=%s", batch_id, mode)
    stats = asyncio.run(
        run(
            dump_dir,
            include_test_accounts=args.include_test_accounts,
            commit=args.commit,
            batch_id=batch_id,
            report_dir=Path(args.report_dir),
            batch_size=args.batch_size,
            limit=args.limit,
        )
    )
    print(json.dumps(stats.__dict__, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
