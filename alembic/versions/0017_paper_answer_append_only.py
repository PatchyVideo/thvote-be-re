"""0017 paper_answer append-only: drop voter-group unique, add attempt batch marker.

Removes the uq_paper_answer_voter_group unique constraint to allow multiple
submissions per voter; adds the attempt column (batch number, NULL = pre-0017
legacy); creates ix_paper_answer_vote index to support result queries.

Postgres-only (downgrade uses DELETE ... USING). sqlite test schemas are built
via ``create_all`` and skip this migration.
"""

from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.drop_constraint(
        "uq_paper_answer_voter_group", "paper_answer", type_="unique")
    op.add_column(
        "paper_answer", sa.Column("attempt", sa.Integer(), nullable=True))
    op.create_index(
        "ix_paper_answer_vote", "paper_answer", ["vote_id", "vote_year"])


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    # 回滚前先清历史批次,只留每 (vote_id, vote_year, questionnaire_id,
    # group_id) 的最大 attempt 行,否则唯一约束加不回去。
    op.execute(
        """
        DELETE FROM paper_answer p USING paper_answer q
        WHERE p.vote_id = q.vote_id AND p.vote_year = q.vote_year
          AND p.questionnaire_id = q.questionnaire_id
          AND p.group_id = q.group_id
          AND COALESCE(p.attempt, 0) < COALESCE(q.attempt, 0)
        """
    )
    op.drop_index("ix_paper_answer_vote", table_name="paper_answer")
    op.drop_column("paper_answer", "attempt")
    op.create_unique_constraint(
        "uq_paper_answer_voter_group", "paper_answer",
        ["vote_id", "vote_year", "questionnaire_id", "group_id"])
