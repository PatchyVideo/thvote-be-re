#!/usr/bin/env python3
"""Import a mongodump directory (BSON files) into PostgreSQL.

Reuses the existing field mappers from ``src.apps.admin.sync.runner``.
Run from the repo root::

    python scripts/import_mongo_dump.py /path/to/dump260311 -n   # dry-run
    python scripts/import_mongo_dump.py /path/to/dump260311       # live

Tables that don't exist yet will raise an UndefinedTableError — run
``alembic upgrade head`` first.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Ensure the project root is on sys.path
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.apps.admin.sync.runner import (
    _CONFLICT_COLS,
    map_candidate_character,
    map_candidate_music,
    map_final_ranking,
    map_raw_paper,
    map_raw_submit,
    map_voter,
)
from src.common.config import get_settings
from src.common.database import normalize_async_database_url

logger = logging.getLogger("import_mongo_dump")

# ── collection → (mapper, pg_table) mapping ──────────────────────────────

_COLLECTION_CONFIG: dict[str, tuple] = {
    # db_dir: collection_name → (mapper_fn, pg_table)
    "thvote_users/voters": (map_voter, "user"),
    "submits_v1/raw_character": (
        lambda d: map_raw_submit(d, "characters"), "raw_character"),
    "submits_v1/raw_music": (
        lambda d: map_raw_submit(d, "music"), "raw_music"),
    "submits_v1/raw_cp": (
        lambda d: map_raw_submit(d, "cps"), "raw_cp"),
    "submits_v1/raw_dojin": (
        lambda d: map_raw_submit(d, "dojins"), "raw_dojin"),
    "submits_v1/raw_paper": (map_raw_paper, "raw_paper"),
    "submits_v1_final/chars": (map_candidate_character, "candidate_character"),
    "submits_v1_final/musics": (map_candidate_music, "candidate_music"),
    "submits_v1_final/final_ranking_char": (
        lambda d: map_final_ranking(d, "character"), "final_ranking"),
    "submits_v1_final/final_ranking_music": (
        lambda d: map_final_ranking(d, "music"), "final_ranking"),
}


def _conflict_clause(pg_table: str) -> str:
    col = _CONFLICT_COLS.get(pg_table, "legacy_mongo_id")
    if "(" in col:
        return f"ON CONFLICT {col} DO NOTHING"
    return f"ON CONFLICT ({col}) DO NOTHING"


async def _import_collection(
    session_maker,
    bson_path: Path,
    mapper,
    pg_table: str,
    *,
    batch_size: int = 500,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    """Import one .bson file. Returns (inserted, skipped, errors)."""
    from bson import decode_all

    raw = bson_path.read_bytes()
    docs = decode_all(raw)
    total = len(docs)
    inserted = skipped = errors = 0

    for start in range(0, total, batch_size):
        chunk = docs[start : start + batch_size]
        batch: list[dict] = []
        for doc in chunk:
            try:
                batch.append(mapper(doc))
            except Exception:
                errors += 1

        if dry_run or not batch:
            inserted += len(batch)
            continue

        conflict = _conflict_clause(pg_table)
        async with session_maker() as session:
            async with session.begin():
                # Multi-row INSERT: single round trip for the whole batch
                cols = list(batch[0].keys())
                col_names = ", ".join(f'"{c}"' for c in cols)
                ph = ", ".join(
                    f"({', '.join(f':{c}_{i}' for c in cols)})"
                    for i in range(len(batch))
                )
                values = {}
                for i, row in enumerate(batch):
                    for c in cols:
                        values[f"{c}_{i}"] = row[c]
                sql = text(
                    f'INSERT INTO "{pg_table}" ({col_names}) '
                    f"VALUES {ph} {conflict}"
                )
                try:
                    result = await session.execute(sql, values)
                    if result.rowcount:
                        inserted += result.rowcount
                    # skipped can't be accurately counted per-row with multi-row INSERT
                except Exception:
                    errors += len(batch)

        logger.info(
            "  %s: %d/%d  ins=%d skip=%d err=%d",
            pg_table, min(start + batch_size, total), total,
            inserted, skipped, errors,
        )

    return inserted, skipped, errors


async def main(dump_dir: str, *, dry_run: bool = False, table_filter: set | None = None) -> None:
    settings = get_settings()
    db_url = normalize_async_database_url(settings.database_url)
    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    dump = Path(dump_dir)
    if not dump.is_dir():
        logger.error("Dump directory not found: %s", dump_dir)
        sys.exit(1)

    totals = {"inserted": 0, "skipped": 0, "errors": 0}
    mode = "DRY-RUN" if dry_run else "LIVE"

    for rel_path, (mapper, pg_table) in _COLLECTION_CONFIG.items():
        if table_filter and pg_table not in table_filter:
            continue
        bson_file = dump / rel_path
        if not bson_file.with_suffix(".bson").is_file():
            logger.warning("SKIP: missing %s.bson", bson_file)
            continue

        logger.info("[%s] %s → %s …", mode, rel_path, pg_table)
        ins, skip, err = await _import_collection(
            session_maker,
            bson_file.with_suffix(".bson"),
            mapper,
            pg_table,
            dry_run=dry_run,
        )
        totals["inserted"] += ins
        totals["skipped"] += skip
        totals["errors"] += err
        logger.info("  done: ins=%d skip=%d err=%d", ins, skip, err)

    await engine.dispose()

    print(f"\n{'='*50}")
    print(f"{mode} complete.")
    print(f"  inserted: {totals['inserted']}")
    print(f"  skipped:  {totals['skipped']}")
    print(f"  errors:   {totals['errors']}")
    print(f"{'='*50}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )
    p = argparse.ArgumentParser(description="Import mongodump into PostgreSQL")
    p.add_argument("dump_dir", help="Path to the dump directory")
    p.add_argument(
        "-n", "--dry-run", action="store_true",
        help="Decode + map only; do not write to PG",
    )
    p.add_argument(
        "--tables", default=None,
        help="Comma-separated PG table names to import (default: all)",
    )
    args = p.parse_args()
    table_filter = set(args.tables.split(",")) if args.tables else None
    asyncio.run(main(args.dump_dir, dry_run=args.dry_run, table_filter=table_filter))
