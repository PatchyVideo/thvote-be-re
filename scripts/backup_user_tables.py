#!/usr/bin/env python3
"""Lightweight CSV backup of the user-related tables.

``pg_dump`` is not required.  The target test database currently holds only a
handful of user rows, so a plain ``SELECT *`` + CSV per table is enough for
the pre-import safety net:

    python scripts/backup_user_tables.py --out-dir /tmp/thvote-backup

Tables: user, user_identity, legacy_user_mapping (if present), activity_log,
alembic_version.  Timestamps are serialised as ISO-8601, NULL as an empty
field.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.common.config import get_settings  # noqa: E402
from src.common.database import normalize_async_database_url  # noqa: E402

TABLES = (
    "user",
    "user_identity",
    "legacy_user_mapping",
    "activity_log",
    "alembic_version",
)


def _cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


async def run(out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(
        normalize_async_database_url(get_settings().database_url), echo=False
    )
    manifest: dict[str, Any] = {"tables": {}}
    try:
        async with engine.connect() as conn:
            for table in TABLES:
                exists = await conn.scalar(
                    text("SELECT to_regclass(:t)"), {"t": f"public.{table}"}
                )
                if not exists:
                    manifest["tables"][table] = {"exists": False}
                    continue
                result = await conn.execute(text(f'SELECT * FROM "{table}"'))
                columns = list(result.keys())
                rows = [
                    {column: _cell(value) for column, value in zip(columns, row)}
                    for row in result.fetchall()
                ]
                target = out_dir / f"{table}.csv"
                with target.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=columns)
                    writer.writeheader()
                    writer.writerows(rows)
                manifest["tables"][table] = {
                    "exists": True,
                    "rows": len(rows),
                    "file": target.name,
                }
    finally:
        await engine.dispose()
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args(argv)
    manifest = asyncio.run(run(Path(args.out_dir)))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
