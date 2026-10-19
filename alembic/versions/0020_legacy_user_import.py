"""0020 legacy user import: restore bcrypt salt + legacy id bridge.

Two changes, both required by the one-off import of the old Mongo
``thvote_users.voters`` dump:

1. ``user.legacy_salt`` — the old Rust user-manager verified imported
   accounts with ``bcrypt(password + salt)``.  The salt lived in its own
   Mongo field; 0018 dropped the column when the import path was removed.
   It comes back as a nullable column, cleared on the first successful
   password login when the hash is upgraded to Argon2.
2. ``legacy_user_mapping`` — the import creates UUID4 accounts, so the old
   Mongo ``_id`` is stored here (with role and import batch) for
   traceability, idempotent re-runs and precise rollback.

Postgres-only and idempotent; sqlite test schemas come from ``create_all``
and skip migrations.
"""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS legacy_salt VARCHAR(255)')
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS legacy_user_mapping (
            legacy_object_id VARCHAR(24) PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL
                REFERENCES "user"(id) ON DELETE CASCADE,
            role VARCHAR(32) NOT NULL,
            batch_id VARCHAR(36) NOT NULL,
            imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_legacy_user_mapping_role CHECK (
                role IN ('primary', 'duplicate', 'conflict_existing')
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_legacy_user_mapping_user_id "
        "ON legacy_user_mapping (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_legacy_user_mapping_batch_id "
        "ON legacy_user_mapping (batch_id)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP TABLE IF EXISTS legacy_user_mapping")
    op.execute('ALTER TABLE "user" DROP COLUMN IF EXISTS legacy_salt')
