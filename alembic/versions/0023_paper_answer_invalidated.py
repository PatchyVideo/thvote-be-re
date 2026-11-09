"""Mark complete questionnaire submission batches as invalidated.

Existing answers remain effective. Downgrade preserves answers but loses flags.
"""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("paper_answer", sa.Column(
        "invalidated", sa.Boolean(), nullable=False, server_default=sa.false(),
    ))


def downgrade() -> None:
    op.drop_column("paper_answer", "invalidated")
