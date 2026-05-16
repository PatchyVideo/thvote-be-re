import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_user_table_has_sso_columns(session_maker):
    """Migration 0004 must add thbwiki_uid and qq_openid to user table.

    Uses PRAGMA table_info for SQLite (local/CI in-memory) and falls back
    to information_schema for Postgres.
    """
    async with session_maker() as session:
        # Detect dialect
        dialect = session.bind.dialect.name  # type: ignore[union-attr]
        if dialect == "sqlite":
            result = await session.execute(text("PRAGMA table_info('user')"))
            # PRAGMA table_info returns rows: (cid, name, type, notnull, dflt_value, pk)
            cols = {row[1] for row in result.fetchall()}
        else:
            result = await session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'user' "
                    "AND column_name IN ('thbwiki_uid', 'qq_openid')"
                )
            )
            cols = {row[0] for row in result.fetchall()}

    assert "thbwiki_uid" in cols, "thbwiki_uid column missing"
    assert "qq_openid" in cols, "qq_openid column missing"
