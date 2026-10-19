#!/usr/bin/env python3
"""Roll back one legacy-voter import batch.

Deletes exactly the accounts created by ``batch_id`` (role=primary) plus all
mapping rows of that batch.  Accounts that only received a
``conflict_existing`` mapping are NOT touched.

Safety: if any account of the batch already has votes, activity or an admin
review row, the script refuses unless ``--force`` is passed — deleting those
would orphan data that lives outside the user tables.

Usage:
    python scripts/rollback_legacy_user_import.py --batch-id <uuid>
    python scripts/rollback_legacy_user_import.py --batch-id <uuid> --commit
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.common.config import get_settings  # noqa: E402
from src.common.database import normalize_async_database_url  # noqa: E402

logger = logging.getLogger("rollback_legacy_user_import")

# (table, column) that would be orphaned by deleting the account.
_REFERENCES = (
    ("raw_character", "vote_id"),
    ("raw_music", "vote_id"),
    ("raw_cp", "vote_id"),
    ("raw_paper", "vote_id"),
    ("raw_dojin", "vote_id"),
    ("raw_work", "vote_id"),
    ("dojin_nomination", "vote_id"),
    ("paper_answer", "vote_id"),
    ("activity_log", "user_id"),
    ("voter_review", "user_id"),
)


async def run(batch_id: str, *, commit: bool, force: bool) -> dict:
    settings = get_settings()
    engine = create_async_engine(
        normalize_async_database_url(settings.database_url), echo=False
    )
    result: dict = {"batch_id": batch_id, "mode": "commit" if commit else "preflight"}
    try:
        async with engine.connect() as conn:
            counts = await conn.execute(
                text(
                    "SELECT role, count(*) FROM legacy_user_mapping "
                    "WHERE batch_id = :b GROUP BY role"
                ),
                {"b": batch_id},
            )
            result["mappings_by_role"] = {row[0]: row[1] for row in counts}
            primary_count = await conn.scalar(
                text(
                    "SELECT count(*) FROM legacy_user_mapping "
                    "WHERE batch_id = :b AND role = 'primary'"
                ),
                {"b": batch_id},
            )
            result["primary_users"] = primary_count
            if not primary_count:
                result["message"] = "nothing to roll back"
                return result

            # Subquery instead of an id array: works on PG and sqlite and never
            # builds an 80k-parameter statement.
            primary_ids = (
                "SELECT user_id FROM legacy_user_mapping "
                "WHERE batch_id = :b AND role = 'primary'"
            )
            blocked: list[str] = []
            for table, column in _REFERENCES:
                exists = await conn.run_sync(
                    lambda sync_conn, t=table: inspect(sync_conn).has_table(t)
                )
                if not exists:
                    continue
                n = await conn.scalar(
                    text(
                        f'SELECT count(*) FROM "{table}" '
                        f"WHERE {column} IN ({primary_ids})"
                    ),
                    {"b": batch_id},
                )
                if n:
                    blocked.append(f"{table}.{column}={n}")
            result["blocking_references"] = blocked
            if blocked and not force:
                result["message"] = "refusing to delete accounts with references"
                return result

            if not commit:
                result["message"] = "preflight only; pass --commit to delete"
                return result

            # Explicit identity delete keeps the script correct on sqlite too
            # (sqlite does not enforce ON DELETE CASCADE by default).
            await conn.execute(
                text(
                    "DELETE FROM user_identity WHERE user_id IN "
                    f"({primary_ids})"
                ),
                {"b": batch_id},
            )
            await conn.execute(
                text(f'DELETE FROM "user" WHERE id IN ({primary_ids})'),
                {"b": batch_id},
            )
            await conn.execute(
                text("DELETE FROM legacy_user_mapping WHERE batch_id = :b"),
                {"b": batch_id},
            )
            await conn.commit()
            result["message"] = "deleted"
    finally:
        await engine.dispose()
    return result


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    out = asyncio.run(run(args.batch_id, commit=args.commit, force=args.force))
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
