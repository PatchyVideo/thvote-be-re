"""Candidate import: pure parse/validate/field-spec helpers (no DB)."""
from __future__ import annotations

import csv
import io
import json
from typing import Any

from src.db_model.candidate import CandidateCharacter, CandidateMusic


def _model_for(category: str):
    return CandidateCharacter if category == "character" else CandidateMusic


def candidate_field_specs(category: str) -> list[dict]:
    """Derive editable fields + required flag from model columns.

    Excludes ``id`` (autoincrement PK) and ``vote_year`` (chosen in UI).
    A column is required when it is NOT NULL and has no server_default.
    """
    model = _model_for(category)
    specs = []
    for c in model.__table__.columns:
        if c.key in ("id", "vote_year"):
            continue
        required = (not c.nullable) and (c.server_default is None)
        specs.append({"name": c.key, "required": required})
    return specs


def parse_content(fmt: str, content: str) -> tuple[list[dict], list[dict]]:
    """Parse raw CSV/JSON text into a list of raw row dicts.

    Returns (rows, parse_errors). parse_errors is non-empty only on a
    document-level failure (bad JSON, no CSV header, empty input).
    """
    text = (content or "").strip()
    if not text:
        return [], [{"line": 0, "reason": "内容为空"}]

    detected = fmt
    if fmt == "auto":
        detected = "json" if text[:1] in ("[", "{") else "csv"

    if detected == "json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            return [], [{"line": 0, "reason": f"JSON 解析失败: {e}"}]
        if not isinstance(data, list):
            return [], [{"line": 0, "reason": "JSON 必须是对象数组"}]
        rows: list[dict] = []
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                return [], [{"line": i, "reason": "数组元素必须是对象"}]
            rows.append(item)
        return rows, []

    # CSV
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return [], [{"line": 0, "reason": "CSV 无表头"}]
    return [dict(r) for r in reader], []


def validate_items(category: str, rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Validate + clean rows. insertSelective: drop empty values and unknown columns.

    Returns (valid, rejected). A row is rejected only when ``name`` is
    missing or blank. ``line`` in rejected is the 1-based row position.
    """
    model = _model_for(category)
    valid_cols = {
        c.key for c in model.__table__.columns if c.key not in ("id", "vote_year")
    }
    valid: list[dict] = []
    rejected: list[dict] = []
    for idx, raw in enumerate(rows):
        cleaned: dict[str, Any] = {}
        for k, v in raw.items():
            if k not in valid_cols or v is None:
                continue
            sv = str(v).strip()
            if sv == "":
                continue
            cleaned[k] = sv
        if not cleaned.get("name"):
            rejected.append({"line": idx + 1, "reason": "缺少 name"})
            continue
        valid.append(cleaned)
    return valid, rejected
