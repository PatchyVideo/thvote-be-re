#!/usr/bin/env python3
"""Convert mongodump BSON files to PostgreSQL INSERT SQL.

Usage:
    python scripts/bson_to_sql.py \
        C:/Users/HUAWEI/Downloads/dump260311_2/dump260311/dump260311 \
        -t candidate_character,candidate_music \
        -o D:/personal/thvote/.tmp_import.sql
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

from src.apps.admin.sync.runner import (
    _CONFLICT_COLS,
    map_candidate_character,
    map_candidate_music,
    map_final_ranking,
    map_raw_paper,
    map_raw_submit,
    map_voter,
)

# mapper name → function
_MAPPERS = {
    "map_voter": map_voter,
    "map_raw_submit": map_raw_submit,
    "map_raw_paper": map_raw_paper,
    "map_candidate_character": map_candidate_character,
    "map_candidate_music": map_candidate_music,
    "map_final_ranking": map_final_ranking,
}

# The existing COLLECTION_CONFIG references mapper lambdas.
# We build a name-keyed lookup: pg_table → (relative_bson_path, mapper_name, mapper_fn)
_COLLECTION_BY_TABLE: dict[str, tuple[str, str, callable]] = {}

# Manual registration matching COLLECTION_CONFIG order:
_REGISTRY: list[tuple[str, str, str, callable]] = [
    # relative_path, mapper_name, pg_table
    ("thvote_users/voters.bson", "map_voter", "user"),
    ("submits_v1/raw_character.bson", "map_raw_submit:characters", "raw_character"),
    ("submits_v1/raw_music.bson", "map_raw_submit:music", "raw_music"),
    ("submits_v1/raw_cp.bson", "map_raw_submit:cps", "raw_cp"),
    ("submits_v1/raw_dojin.bson", "map_raw_submit:dojins", "raw_dojin"),
    ("submits_v1/raw_paper.bson", "map_raw_paper", "raw_paper"),
    ("submits_v1_final/chars.bson", "map_candidate_character", "candidate_character"),
    ("submits_v1_final/musics.bson", "map_candidate_music", "candidate_music"),
    ("submits_v1_final/final_ranking_char.bson", "map_final_ranking:character", "final_ranking"),
    ("submits_v1_final/final_ranking_music.bson", "map_final_ranking:music", "final_ranking"),
]


def _wrap_row(c: str, row: dict) -> str:
    """Format a single value for PostgreSQL SQL."""
    v = row.get(c)
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        escaped = v.replace("\\", "\\\\").replace("'", "''")
        return f"'{escaped}'"
    # fallback: list/dict → escaped string
    escaped = str(v).replace("\\", "\\\\").replace("'", "''")
    return f"'{escaped}'"


def _pg_value(row: dict, col: str) -> str:
    """Format one column value for PG — handles list/dict as string literal."""
    v = row.get(col)
    if v is None:
        return "NULL"
    if isinstance(v, str):
        return "'" + v.replace("'", "''") + "'"
    return str(v)


def generate_sql(dump_dir: str, tables: list[str]) -> str:
    import bson

    parts: list[str] = []
    parts.append("BEGIN;\n")

    for rel_path, mapper_key, pg_table in _REGISTRY:
        if tables and pg_table not in tables:
            continue

        bson_path = Path(dump_dir) / rel_path
        if not bson_path.is_file():
            parts.append(f"-- SKIP: {bson_path} not found\n")
            continue

        docs = bson.decode_all(bson_path.read_bytes())

        # Resolve mapper
        if ":" in mapper_key:
            name, arg = mapper_key.split(":", 1)
            mapper_fn = _MAPPERS[name]
        else:
            mapper_fn = _MAPPERS[mapper_key]
            arg = None

        rows = []
        for doc in docs:
            try:
                row = mapper_fn(doc) if arg is None else mapper_fn(doc, arg)
                rows.append(row)
            except Exception as e:
                parts.append(f"-- WARNING: map error for _id={doc.get('_id')}: {e}\n")

        cols = list(rows[0].keys()) if rows else []
        col_names = ", ".join(f'"{c}"' for c in cols)
        conflict_str = _CONFLICT_COLS.get(pg_table, "(vote_year, name)")

        if pg_table == "user":
            parts.append("CREATE EXTENSION IF NOT EXISTS \"pgcrypto\";\n")

        parts.append(f"\n-- {pg_table}: {len(rows)} rows from {rel_path}\n")
        parts.append(f"TRUNCATE TABLE {pg_table} CASCADE;\n")

        batch_size = 100
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            values_lines = []
            for r in batch:
                vals = ", ".join(
                    "gen_random_uuid()" if pg_table == "user" and c == "id"
                    else _pg_value(r, c) for c in cols
                )
                values_lines.append(f"  ({vals})")
            parts.append(
                f"INSERT INTO {pg_table} ({col_names}) VALUES\n"
                f"{',\n'.join(values_lines)}\n"
                f"ON CONFLICT {conflict_str} DO NOTHING;\n"
            )

    parts.append("\nCOMMIT;\n")
    return "".join(parts)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="BSON → PostgreSQL SQL")
    p.add_argument("dump_dir", help="Path to mongodump directory")
    p.add_argument("-t", "--tables", required=True,
                   help="Comma-separated PG table names")
    p.add_argument("-o", "--output", help="Output SQL file (default: stdout)")
    args = p.parse_args()

    table_list = [t.strip() for t in args.tables.split(",")]
    sql = generate_sql(args.dump_dir, table_list)

    if args.output:
        Path(args.output).write_text(sql, encoding="utf-8")
        print(f"Written to {args.output}")
    else:
        sys.stdout.write(sql)
