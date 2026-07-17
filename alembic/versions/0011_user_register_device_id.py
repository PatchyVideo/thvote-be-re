"""0011 add ``user.register_device_id`` (device fingerprint at registration, B-044).

Stores the client-supplied device UUID (localStorage) captured when the
account is created, so account->device links survive in the ``user`` table
(the rolling ``activity_log`` is not a durable store).  Forensic evidence for
anti-vote-farming; never used as an auth gate (client-controlled).

Idempotent ``ADD COLUMN IF NOT EXISTS`` (Postgres-only, same convention as
0005). sqlite test schemas are built via ``create_all`` and skip migrations.
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        'ALTER TABLE "user" '
        "ADD COLUMN IF NOT EXISTS register_device_id VARCHAR(128) NOT NULL DEFAULT ''"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute('ALTER TABLE "user" DROP COLUMN IF EXISTS register_device_id')
