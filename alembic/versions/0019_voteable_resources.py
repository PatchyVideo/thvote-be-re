"""0019 voteable resources: bind image / audio / album URLs to voteables.

把投票对象的资源类 URL 从「前端静态数据文件按 name 匹配」迁到后端，
与 voteable 1:1 绑定，由公共 vote-objects 接口下发给前端统一加载。

新增列（只增不删，向后兼容）：
  voteable_character.image_url   TEXT NULL
  voteable_music.image_url       TEXT NULL
  voteable_music.music_url       TEXT NULL
  voteable_music.include         JSON NOT NULL DEFAULT '[]'

``aliases`` 列已存在（此前全空），由数据迁移脚本回填，本迁移不改结构。

Postgres-only 幂等；sqlite 测试库经 create_all 跳过本迁移。

设计: docs/superpowers/specs/2026-09-16-voteable-resource-backend-design.md
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE voteable_character ADD COLUMN IF NOT EXISTS image_url TEXT"
    )
    op.execute(
        "ALTER TABLE voteable_music ADD COLUMN IF NOT EXISTS image_url TEXT"
    )
    op.execute(
        "ALTER TABLE voteable_music ADD COLUMN IF NOT EXISTS music_url TEXT"
    )
    op.execute(
        "ALTER TABLE voteable_music ADD COLUMN IF NOT EXISTS "
        "\"include\" JSON NOT NULL DEFAULT '[]'"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute('ALTER TABLE voteable_music DROP COLUMN IF EXISTS "include"')
    op.execute("ALTER TABLE voteable_music DROP COLUMN IF EXISTS music_url")
    op.execute("ALTER TABLE voteable_music DROP COLUMN IF EXISTS image_url")
    op.execute("ALTER TABLE voteable_character DROP COLUMN IF EXISTS image_url")
