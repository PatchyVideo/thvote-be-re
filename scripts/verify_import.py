#!/usr/bin/env python3
"""Read-only verification of the legacy voter import.

Connects to the target DB via ``get_settings()`` (Nacos), then prints a
PASS/FAIL checklist: row counts, plaintext-leak scan (the red-line check),
encrypted-column coverage, and one decrypted sample that must round-trip back
through the blind index.  Never writes.

Usage (one-off container, same image as the backend):
    docker run --rm --network thvote-net \
      --env-file /opt/thvote/prod/.env \
      -e PII_DEK_PATH=/run/secrets/pii_dek \
      -v /opt/thvote/prod/secrets:/run/secrets:ro \
      <IMAGE> \
      python scripts/verify_import.py \
        [--expect-users N] [--expect-identities N] [--expect-mappings N]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.common.config import get_settings  # noqa: E402
from src.common.crypto import aad_for, blind_index, decrypt, fingerprint  # noqa: E402
from src.common.database import normalize_async_database_url  # noqa: E402


async def _scalar(conn, sql: str) -> int:
    return int(await conn.scalar(text(sql)))


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect-users", type=int, default=None)
    parser.add_argument("--expect-identities", type=int, default=None)
    parser.add_argument("--expect-mappings", type=int, default=None)
    args = parser.parse_args(argv)

    settings = get_settings()
    engine = create_async_engine(
        normalize_async_database_url(settings.database_url), echo=False
    )
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append((name, ok, detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    try:
        async with engine.connect() as conn:
            users = await _scalar(conn, 'select count(*) from "user"')
            identities = await _scalar(conn, "select count(*) from user_identity")
            mappings = await _scalar(conn, "select count(*) from legacy_user_mapping")

            subject_plain = await _scalar(
                conn, "select count(*) from user_identity where subject is not null"
            )
            regip_plain = await _scalar(
                conn,
                'select count(*) from "user" where register_ip_address is not null',
            )
            created_ip_plain = await _scalar(
                conn, "select count(*) from user_identity where created_ip is not null"
            )
            subject_enc = await _scalar(
                conn, "select count(*) from user_identity where subject_enc is not null"
            )
            regip_enc = await _scalar(
                conn, 'select count(*) from "user" where register_ip_enc is not null'
            )
            created_ip_enc = await _scalar(
                conn,
                "select count(*) from user_identity where created_ip_enc is not null",
            )

            sample = (
                await conn.execute(
                    text(
                        "select provider, subject_enc, subject_idx, user_id "
                        "from user_identity "
                        "where provider='email' and subject_enc is not null limit 1"
                    )
                )
            ).first()
            sample_ok = False
            sample_detail = "<no sample>"
            if sample is not None:
                provider, enc, idx, uid = sample
                try:
                    plain = decrypt(enc, aad_for("user_identity", "subject", uid))
                    sample_ok = bool(plain) and blind_index(provider, plain) == idx
                    sample_detail = plain or "<empty>"
                except Exception as exc:  # noqa: BLE001 - report, don't crash
                    sample_detail = f"<decrypt failed: {exc}>"

            print("PII DEK loaded: fp=%s" % fingerprint())
            print(f"users={users} identities={identities} mappings={mappings}")

            if args.expect_users is not None:
                check("user count", users == args.expect_users, str(users))
            if args.expect_identities is not None:
                check(
                    "identity count",
                    identities == args.expect_identities,
                    str(identities),
                )
            if args.expect_mappings is not None:
                check(
                    "mapping count", mappings == args.expect_mappings, str(mappings)
                )

            check("subject plaintext is NULL", subject_plain == 0, str(subject_plain))
            check("register_ip plaintext is NULL", regip_plain == 0, str(regip_plain))
            check(
                "created_ip plaintext is NULL",
                created_ip_plain == 0,
                str(created_ip_plain),
            )
            check("subject_enc populated", subject_enc > 0, str(subject_enc))
            check("register_ip_enc populated", regip_enc > 0, str(regip_enc))
            check("created_ip_enc populated", created_ip_enc > 0, str(created_ip_enc))
            check("sample decrypt + blind-index roundtrip", sample_ok, sample_detail)
    finally:
        await engine.dispose()

    failed = [c for c in checks if not c[1]]
    print("RESULT:", "PASS" if not failed else f"{len(failed)} CHECK(S) FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
