"""0013 add ``client_env`` to raw_* submit tables (B-046).

Client/browser environment fingerprint per submission: ``{ua, tz, screen,
lang}`` — ``ua`` read server-side from the request header (captured even for
API bots), ``tz/screen/lang`` reported by the frontend. Anti-vote-farming
forensic signal (headless UA, browser-timezone vs IP-geo mismatch, default
screen resolution). A single JSON column so new signals need no schema change.
Forensic only, never an auth gate.

Idempotent ``ADD COLUMN IF NOT EXISTS`` (Postgres-only, same convention as
0011/0012). sqlite test schemas are built via ``create_all`` and skip migrations.
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

_TABLES = ("raw_character", "raw_music", "raw_cp", "raw_paper", "raw_dojin", "raw_work")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in _TABLES:
        # 用 JSON(非 JSONB)与模型的通用 JSON 类型一致,避免 schema 漂移;
        # 取证量级下无需 JSONB 索引,`client_env->>'ua'` 查询足够。
        op.execute(
            f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS client_env JSON'
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in _TABLES:
        op.execute(f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS client_env')
