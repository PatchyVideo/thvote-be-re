"""0014 admin monitor support (B-049): raw_*.invalidated + indexes + voter_review.

Adds a reversible ``invalidated`` soft-flag to the 6 raw_* submit tables (admin
can void a specific vote — recorded only; making it affect rankings is B-050),
btree indexes on ``raw_*.user_ip`` and ``user.register_date`` for the monitoring
aggregations, and the ``voter_review`` table (per-account review status + note).

Idempotent ``ADD COLUMN/INDEX IF NOT EXISTS`` (Postgres-only, same convention as
0011/0012/0013). sqlite test schemas are built via ``create_all`` and skip this.
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

_RAW_TABLES = (
    "raw_character", "raw_music", "raw_cp", "raw_paper", "raw_dojin", "raw_work",
)
_IP_INDEXED = ("raw_character", "raw_music", "raw_cp", "raw_paper", "raw_dojin")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in _RAW_TABLES:
        op.execute(
            f'ALTER TABLE "{table}" '
            f"ADD COLUMN IF NOT EXISTS invalidated BOOLEAN NOT NULL DEFAULT false"
        )
    for table in _IP_INDEXED:
        op.execute(
            f'CREATE INDEX IF NOT EXISTS "idx_{table}_user_ip" '
            f'ON "{table}" (user_ip)'
        )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "idx_user_register_date" '
        'ON "user" (register_date)'
    )
    op.execute(
        'CREATE TABLE IF NOT EXISTS "voter_review" ('
        "user_id VARCHAR(255) PRIMARY KEY, "
        "status VARCHAR(32) NOT NULL DEFAULT '', "
        "note TEXT NOT NULL DEFAULT '', "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute('DROP TABLE IF EXISTS "voter_review"')
    op.execute('DROP INDEX IF EXISTS "idx_user_register_date"')
    for table in _IP_INDEXED:
        op.execute(f'DROP INDEX IF EXISTS "idx_{table}_user_ip"')
    for table in _RAW_TABLES:
        op.execute(f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS invalidated')
