"""0005 reconcile ``user`` table columns (idempotent).

Some deployments have a drifted ``user`` table: a pre-existing / incomplete
table was auto-stamped to 0001 by ``env.py``'s ``_maybe_baseline_existing_schema``,
so 0001's CREATE never actually ran and columns like ``phone_verified`` are
missing — login then fails with ``UndefinedColumnError``.

This migration idempotently ``ADD COLUMN IF NOT EXISTS`` every ``user`` column
so the table matches the model. On a correctly-built DB every statement is a
no-op. NOT NULL columns carry a server-side DEFAULT so existing rows backfill.

Postgres-only (``ADD COLUMN IF NOT EXISTS`` is a PG feature). Test/CI alembic
runs target Postgres; sqlite test schemas are built via ``create_all`` and skip
migrations, so the dialect guard makes this a no-op elsewhere.

NOTE: targeted band-aid for the ``user`` table to unblock login. Other tables
may carry the same baseline drift; the clean fix is to rebuild the schema on an
empty DB once DB privileges allow (see BACKLOG B-025).
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

# Mirrors the column definitions in 0001 (+ SSO columns from 0004).
_USER_COLUMN_CLAUSES = [
    "ADD COLUMN IF NOT EXISTS phone_number VARCHAR(32)",
    "ADD COLUMN IF NOT EXISTS phone_verified BOOLEAN NOT NULL DEFAULT false",
    "ADD COLUMN IF NOT EXISTS email VARCHAR(255)",
    "ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT false",
    "ADD COLUMN IF NOT EXISTS password_hash VARCHAR(512)",
    "ADD COLUMN IF NOT EXISTS legacy_salt VARCHAR(255)",
    "ADD COLUMN IF NOT EXISTS nickname VARCHAR(64)",
    "ADD COLUMN IF NOT EXISTS pfp VARCHAR(512)",
    "ADD COLUMN IF NOT EXISTS removed BOOLEAN NOT NULL DEFAULT false",
    "ADD COLUMN IF NOT EXISTS register_date TIMESTAMPTZ NOT NULL DEFAULT now()",
    "ADD COLUMN IF NOT EXISTS register_ip_address VARCHAR(64) NOT NULL DEFAULT ''",
    "ADD COLUMN IF NOT EXISTS thbwiki_uid VARCHAR(128)",
    "ADD COLUMN IF NOT EXISTS qq_openid VARCHAR(128)",
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for clause in _USER_COLUMN_CLAUSES:
        op.execute(f'ALTER TABLE "user" {clause}')


def downgrade() -> None:
    # Reconcile-only: never drop these columns (they are part of the model and
    # exist on a correctly-built DB). No-op downgrade.
    pass
