"""MongoDB → PostgreSQL sync: field mappers + batch runner."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ── datetime helper ────────────────────────────────────────────────────────────

def _coerce_datetime(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    if hasattr(val, "as_datetime"):
        dt = val.as_datetime()
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(val))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ── field mappers ──────────────────────────────────────────────────────────────

def map_voter(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "phone_number": doc.get("phone"),
        "phone_verified": bool(doc.get("phone_verified", False)),
        "email": doc.get("email"),
        "email_verified": bool(doc.get("email_verified", False)),
        "password_hash": doc.get("password_hashed"),
        "legacy_salt": doc.get("salt"),
        "register_date": _coerce_datetime(doc.get("created_at")),
        "nickname": doc.get("nickname"),
        "register_ip_address": doc.get("signup_ip") or "",
        "qq_openid": doc.get("qq_openid"),
        "pfp": doc.get("pfp"),
        "thbwiki_uid": doc.get("thbwiki_uid"),
        "removed": bool(doc.get("removed") or False),
    }


def map_raw_submit(doc: dict[str, Any], payload_key: str) -> dict[str, Any]:
    meta = doc.get("meta") or {}
    return {
        "legacy_mongo_id": str(doc["_id"]),
        "vote_id": meta.get("vote_id") or "",
        "attempt": meta.get("attempt"),
        "created_at": _coerce_datetime(meta.get("created_at")),
        "user_ip": meta.get("user_ip") or "<unknown>",
        "additional_fingreprint": meta.get("additional_fingreprint"),
        "fill_duration_ms": meta.get("fill_duration_ms"),
        "payload": doc.get(payload_key) or [],
    }


def map_raw_paper(doc: dict[str, Any]) -> dict[str, Any]:
    meta = doc.get("meta") or {}
    return {
        "legacy_mongo_id": str(doc["_id"]),
        "vote_id": meta.get("vote_id") or "",
        "attempt": meta.get("attempt"),
        "created_at": _coerce_datetime(meta.get("created_at")),
        "user_ip": meta.get("user_ip") or "<unknown>",
        "additional_fingreprint": meta.get("additional_fingreprint"),
        "fill_duration_ms": meta.get("fill_duration_ms"),
        "papers_json": doc.get("papers_json") or "{}",
    }


def map_final_ranking(doc: dict[str, Any], category: str) -> dict[str, Any]:
    return {
        "vote_year": doc.get("vote_year"),
        "category": category,
        "rank": doc.get("rank"),
        "name": doc.get("name") or "",
        "vote_count": doc.get("vote_count") or 0,
        "first_vote_count": doc.get("first_vote_count") or 0,
    }


def map_candidate_character(doc: dict[str, Any]) -> dict[str, Any]:
    kinds = doc.get("kind") or []
    works = doc.get("work") or []
    date = doc.get("date")
    return {
        "vote_year": doc.get("vote_year"),
        "name": doc.get("name") or "",
        "name_jp": doc.get("origname") or "",
        "type": kinds[0] if kinds else "",
        "origin": works[0] if works else "",
        "first_appearance": str(date) if date is not None else None,
    }


def map_candidate_music(doc: dict[str, Any]) -> dict[str, Any]:
    kinds = doc.get("kind") or []
    date = doc.get("date")
    return {
        "vote_year": doc.get("vote_year"),
        "name": doc.get("name") or "",
        "name_jp": doc.get("origname") or "",
        "type": kinds[0] if kinds else "",
        "first_appearance": str(date) if date is not None else None,
        "album": doc.get("album"),
    }


# ── collection config ──────────────────────────────────────────────────────────

# Each tuple: (settings_db_attr, mongo_collection, pg_table, mapper_fn, _unused)
COLLECTION_CONFIG = [
    # A: users
    ("mongodb_db_users", "voters", "user", map_voter, "id"),
    # B: raw submissions
    ("mongodb_db_submits", "raw_character", "raw_character",
     lambda d: map_raw_submit(d, "characters"), "legacy_mongo_id"),
    ("mongodb_db_submits", "raw_music", "raw_music",
     lambda d: map_raw_submit(d, "music"), "legacy_mongo_id"),
    ("mongodb_db_submits", "raw_cp", "raw_cp",
     lambda d: map_raw_submit(d, "cps"), "legacy_mongo_id"),
    ("mongodb_db_submits", "raw_work", "raw_work",
     lambda d: map_raw_submit(d, "works"), "legacy_mongo_id"),
    ("mongodb_db_submits", "raw_paper", "raw_paper",
     map_raw_paper, "legacy_mongo_id"),
    ("mongodb_db_submits", "raw_dojin", "raw_dojin",
     lambda d: map_raw_submit(d, "dojins"), "legacy_mongo_id"),
    # C: final rankings
    ("mongodb_db_results", "final_ranking_char", "final_ranking",
     lambda d: map_final_ranking(d, "character"), None),
    ("mongodb_db_results", "final_ranking_music", "final_ranking",
     lambda d: map_final_ranking(d, "music"), None),
    # D: candidates
    ("mongodb_db_results", "chars", "candidate_character",
     map_candidate_character, None),
    ("mongodb_db_results", "musics", "candidate_music",
     map_candidate_music, None),
]

# Conflict column per PG table — used to build ON CONFLICT clause
_CONFLICT_COLS: dict[str, str] = {
    "user": "id",
    "final_ranking": "(vote_year, category, rank)",
    "candidate_character": "(vote_year, name)",
    "candidate_music": "(vote_year, name)",
    # raw_* tables use legacy_mongo_id (handled by default below)
}


async def run_collection(
    *,
    mongo_db,
    collection_name: str,
    pg_table: str,
    mapper,
    run_id: str,
    batch_size: int,
    redis,
    session_maker,
    error_path: str,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    """Process one MongoDB collection. Returns (inserted, skipped, errors)."""
    from src.apps.admin.sync.checkpoint import load_checkpoint, save_checkpoint
    from src.apps.admin.sync.progress import check_cancel, set_progress

    coll = mongo_db[collection_name]
    last_id_str = await load_checkpoint(redis, run_id, collection_name)

    query: dict = {}
    if last_id_str:
        try:
            from bson import ObjectId
            query = {"_id": {"$gt": ObjectId(last_id_str)}}
        except Exception:
            pass  # non-ObjectId collections: start from beginning

    total = coll.count_documents(query)
    inserted = skipped = errors = 0
    batch: list[tuple[str, dict]] = []

    for i, doc in enumerate(coll.find(query).sort("_id", 1)):
        if await check_cancel(redis, run_id):
            logger.info("Sync cancelled at collection=%s i=%d", collection_name, i)
            break

        try:
            row = mapper(doc)
        except Exception as exc:
            logger.warning("Mapping error _id=%s: %s", doc.get("_id"), exc)
            _write_error(error_path, {"_id": str(doc.get("_id")), "error": str(exc)})
            errors += 1
            continue

        batch.append((str(doc["_id"]), row))

        is_last = (i == total - 1)
        if len(batch) >= batch_size or is_last:
            if not dry_run and batch:
                b_ins, b_skip, b_err = await _flush_batch(
                    batch, pg_table, session_maker, error_path
                )
                inserted += b_ins
                skipped += b_skip
                errors += b_err

            if batch:
                await save_checkpoint(redis, run_id, collection_name, batch[-1][0])

            await set_progress(
                redis, run_id,
                current_collection=collection_name,
                processed=i + 1,
                total=total,
                inserted=inserted,
                skipped=skipped,
                errors=errors,
            )
            batch = []

    return inserted, skipped, errors


async def _flush_batch(
    batch: list[tuple[str, dict]],
    pg_table: str,
    session_maker,
    error_path: str,
) -> tuple[int, int, int]:
    from sqlalchemy import text

    conflict_col = _CONFLICT_COLS.get(pg_table, "legacy_mongo_id")
    if "(" in conflict_col:
        conflict_clause = f"ON CONFLICT {conflict_col} DO NOTHING"
    else:
        conflict_clause = f"ON CONFLICT ({conflict_col}) DO NOTHING"

    inserted = skipped = errors = 0
    async with session_maker() as session:
        async with session.begin():
            for mongo_id, row in batch:
                cols = ", ".join(f'"{k}"' for k in row)
                params = ", ".join(f":{k}" for k in row)
                sql = text(
                    f'INSERT INTO "{pg_table}" ({cols}) '
                    f"VALUES ({params}) {conflict_clause}"
                )
                try:
                    result = await session.execute(sql, row)
                    if result.rowcount == 0:
                        skipped += 1
                    else:
                        inserted += 1
                except Exception as exc:
                    errors += 1
                    _write_error(error_path, {"mongo_id": mongo_id, "error": str(exc)})
    return inserted, skipped, errors


def _write_error(path: str, record: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
