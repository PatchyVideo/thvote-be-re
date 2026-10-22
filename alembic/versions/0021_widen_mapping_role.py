"""0021 widen legacy_user_mapping.role to VARCHAR(32).

0020 created ``role VARCHAR(16)`` but the ``conflict_existing`` value is 17
characters, so the first import batch failed (and rolled back) on an
environment that had already applied 0020.  Fresh installs get VARCHAR(32)
from 0020; this migration repairs databases already stamped at 0020.

Downgrade is intentionally a no-op: shrinking the column back to 16 would
fail as soon as a single ``conflict_existing`` row exists.
"""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE legacy_user_mapping "
        "ALTER COLUMN role TYPE VARCHAR(32)"
    )


def downgrade() -> None:
    # Irreversible on purpose: VARCHAR(16) cannot hold 'conflict_existing'.
    pass
