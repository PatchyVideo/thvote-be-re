"""MongoDB → PostgreSQL full historical data sync CLI.

Usage:
    MONGODB_URI=mongodb://... DATABASE_URL=postgresql+asyncpg://... \\
        python scripts/sync_from_mongodb.py [--collections voters raw_character] \\
                                            [--batch-size 500] [--dry-run] \\
                                            [--resume-run-id <uuid>]

Prerequisite: alembic upgrade head (migration 0006 applied).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import uuid

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ALL_COLLECTIONS = [
    "voters",
    "raw_character", "raw_music", "raw_cp", "raw_work", "raw_paper", "raw_dojin",
    "final_ranking_char", "final_ranking_music",
    "chars", "musics",
]


async def main_async(args: argparse.Namespace) -> None:
    import fakeredis.aioredis as fakeredis_mod
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from src.apps.admin.sync.runner import COLLECTION_CONFIG, run_collection
    from src.db_model import Base

    mongodb_uri = os.environ.get("MONGODB_URI")
    database_url = os.environ.get("DATABASE_URL")
    mongodb_db_users = os.environ.get("MONGODB_DB_USERS", "thvote_users")
    mongodb_db_submits = os.environ.get("MONGODB_DB_SUBMITS", "submits_v1")
    mongodb_db_results = os.environ.get("MONGODB_DB_RESULTS", "submits_v1_final")

    if not mongodb_uri:
        logger.error("MONGODB_URI is required")
        sys.exit(1)
    if not database_url and not args.dry_run:
        logger.error("DATABASE_URL is required (or use --dry-run)")
        sys.exit(1)

    run_id = args.resume_run_id or str(uuid.uuid4())
    logger.info("Run ID: %s", run_id)

    redis = fakeredis_mod.FakeRedis()

    if not args.dry_run:
        engine = create_async_engine(database_url, echo=False)
        session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    else:
        engine = None
        session_maker = None

    collections_to_run = args.collections or ALL_COLLECTIONS

    db_map = {
        "mongodb_db_users": mongodb_db_users,
        "mongodb_db_submits": mongodb_db_submits,
        "mongodb_db_results": mongodb_db_results,
    }

    if not args.dry_run:
        import pymongo as _pymongo
        client = _pymongo.MongoClient(mongodb_uri)
    else:
        client = None

    total_inserted = total_skipped = total_errors = 0

    try:
        for db_attr, coll_name, pg_table, mapper, _ in COLLECTION_CONFIG:
            if coll_name not in collections_to_run:
                continue
            db_name = db_map[db_attr]
            logger.info("Processing %s.%s → %s", db_name, coll_name, pg_table)

            if args.dry_run:
                import pymongo as _pm
                dry_client = _pm.MongoClient(mongodb_uri)
                coll = dry_client[db_name][coll_name]
                total = coll.count_documents({})
                logger.info("[dry-run] %s: %d documents", coll_name, total)
                for doc in coll.find({}).limit(3):
                    try:
                        row = mapper(doc)
                        logger.info("  sample: %s",
                                    {k: str(v)[:40] for k, v in list(row.items())[:4]})
                    except Exception as exc:
                        logger.warning("  mapping error: %s", exc)
                dry_client.close()
                continue

            ins, skp, err = await run_collection(
                mongo_db=client[db_name],
                collection_name=coll_name,
                pg_table=pg_table,
                mapper=mapper,
                run_id=run_id,
                batch_size=args.batch_size,
                redis=redis,
                session_maker=session_maker,
                error_path=f"migrate_errors_{run_id[:8]}.jsonl",
            )
            total_inserted += ins
            total_skipped += skp
            total_errors += err
            logger.info("%s done: inserted=%d skipped=%d errors=%d",
                        coll_name, ins, skp, err)
    finally:
        if client:
            client.close()
        if engine:
            await engine.dispose()

    logger.info("All done: inserted=%d skipped=%d errors=%d",
                total_inserted, total_skipped, total_errors)
    if total_errors:
        logger.warning("Errors written to migrate_errors_%s.jsonl", run_id[:8])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync MongoDB historical data to PostgreSQL"
    )
    parser.add_argument(
        "--collections", nargs="*",
        help=f"Collections to sync (default: all). Options: {', '.join(ALL_COLLECTIONS)}"
    )
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true",
                        help="Read from MongoDB, print samples, do not write to PostgreSQL")
    parser.add_argument("--resume-run-id",
                        help="Resume from checkpoint of a previous run_id")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
