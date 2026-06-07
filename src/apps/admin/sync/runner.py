"""MongoDB → PostgreSQL sync: field mappers + batch runner."""
from __future__ import annotations

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
