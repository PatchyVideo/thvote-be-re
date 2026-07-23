"""0016 add sort_order to candidate_character/candidate_music.

年度官方候选列表序号（0 起），名次第三级 tie-break 的数据来源
（设计稿 2026-07-23-tally-db-truth-source-design.md §三）。
Postgres-only 幂等；sqlite 测试库经 create_all 跳过本迁移。
"""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

_TABLES = ("candidate_character", "candidate_music")


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for t in _TABLES:
        op.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS sort_order INTEGER")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for t in _TABLES:
        op.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS sort_order")
