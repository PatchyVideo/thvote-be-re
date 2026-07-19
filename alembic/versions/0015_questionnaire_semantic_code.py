"""0015 add semantic ``code`` columns to question_def/option_def.

Part of the result-graphql-compat plan (§B: 问卷地基). The live DB's
``question_def.id``/``option_def.id`` are plain autoincrement (1, 2, 3…), not
the authoritative 7-digit semantic code scheme (题 5 位如 ``11011``，选项 7
位如 ``1101101``) that the frontend and gender/segment config address
questions by. The admin questionnaire editor will only ever produce
autoincrement PKs, so the semantic code cannot replace the primary key — it
has to be its own nullable, indexed column.

Idempotent ``ADD COLUMN/INDEX IF NOT EXISTS`` (Postgres-only, same convention
as 0011/0012/0013/0014). sqlite test schemas are built via ``create_all`` and
skip this migration entirely.
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        'ALTER TABLE "question_def" ADD COLUMN IF NOT EXISTS code VARCHAR(16)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "ix_question_def_code" '
        'ON "question_def" (code)'
    )
    op.execute(
        'ALTER TABLE "option_def" ADD COLUMN IF NOT EXISTS code VARCHAR(16)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "ix_option_def_code" ON "option_def" (code)'
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute('DROP INDEX IF EXISTS "ix_option_def_code"')
    op.execute('ALTER TABLE "option_def" DROP COLUMN IF EXISTS code')
    op.execute('DROP INDEX IF EXISTS "ix_question_def_code"')
    op.execute('ALTER TABLE "question_def" DROP COLUMN IF EXISTS code')
