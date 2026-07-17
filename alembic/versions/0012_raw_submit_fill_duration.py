"""0012 add ``fill_duration_ms`` to raw_* submit tables (B-045).

Client-reported active fill duration (milliseconds) for each vote/questionnaire
submission — an anti-vote-farming signal (bots click through in ~0ms). Forensic
only, never an auth gate. Paired with the (now server-computed) ``attempt``
counter so a "too fast" heuristic applies to first submits only.

Idempotent ``ADD COLUMN IF NOT EXISTS`` (Postgres-only, same convention as
0005/0011). sqlite test schemas are built via ``create_all`` and skip migrations.
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_TABLES = ("raw_character", "raw_music", "raw_cp", "raw_paper", "raw_dojin", "raw_work")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in _TABLES:
        op.execute(
            f'ALTER TABLE "{table}" '
            "ADD COLUMN IF NOT EXISTS fill_duration_ms INTEGER"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in _TABLES:
        op.execute(f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS fill_duration_ms')
