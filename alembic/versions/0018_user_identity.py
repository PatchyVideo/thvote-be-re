"""0018 user_identity: move authentication sources out of the user table.

Creates ``user_identity`` (one row per e-mail / phone / QQ / THBWiki),
backfills it from the flat ``user`` columns, then drops those columns, the
``at_least_one_identifier`` CHECK and the four partial unique indexes.

Backfill is approximate (spec §7): per-identity ``created_*`` are copied
from the account's ``register_*``; soft-deleted accounts get no identity
rows (matches the new remove_voter behaviour).  Destructive, no compat
window — the system is not live yet.

Postgres-only; sqlite test schemas come from ``create_all``.

Design: docs/superpowers/specs/2026-09-06-user-identity-model-design.md
"""

from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

_PROVIDERS = ("email", "phone", "qq", "thbwiki")
_PROVIDER_CHECK = "provider IN (" + ", ".join(f"'{p}'" for p in _PROVIDERS) + ")"

# (provider, source column, verified expression) for the backfill.
_BACKFILL = (
    ("email", "lower(trim(email))", "email_verified"),
    ("phone", "trim(phone_number)", "phone_verified"),
    ("qq", "qq_openid", "TRUE"),
    ("thbwiki", "thbwiki_uid", "TRUE"),
)
_DROPPED_USER_COLUMNS = (
    "phone_number",
    "phone_verified",
    "email",
    "email_verified",
    "legacy_salt",
    "thbwiki_uid",
    "qq_openid",
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.create_table(
        "user_identity",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.String(length=64),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_ip", sa.String(length=64), nullable=False, server_default=""),
        sa.Column(
            "created_device_id", sa.String(length=128), nullable=False, server_default=""
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "provider", "subject", name="uq_user_identity_provider_subject"
        ),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_identity_user_provider"),
        sa.CheckConstraint(_PROVIDER_CHECK, name="ck_user_identity_provider"),
    )
    op.create_index("ix_user_identity_user_id", "user_identity", ["user_id"])

    for provider, source, verified in _BACKFILL:
        op.execute(
            f"""
            INSERT INTO user_identity
                (user_id, provider, subject, verified, verified_at,
                 created_at, created_ip, created_device_id)
            SELECT id, '{provider}', {source}, {verified},
                   CASE WHEN {verified} THEN register_date END,
                   register_date, register_ip_address, register_device_id
              FROM "user"
             WHERE {source} IS NOT NULL AND {source} <> '' AND removed = FALSE
            """
        )

    op.drop_constraint("at_least_one_identifier", "user", type_="check")
    for index in (
        "ix_user_email_unique",
        "ix_user_phone_unique",
        "uq_user_thbwiki_uid",
        "uq_user_qq_openid",
    ):
        op.execute(f"DROP INDEX IF EXISTS {index}")
    for column in _DROPPED_USER_COLUMNS:
        op.drop_column("user", column)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.add_column("user", sa.Column("phone_number", sa.String(32), nullable=True))
    op.add_column(
        "user",
        sa.Column(
            "phone_verified", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column("user", sa.Column("email", sa.String(255), nullable=True))
    op.add_column(
        "user",
        sa.Column(
            "email_verified", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column("user", sa.Column("legacy_salt", sa.String(255), nullable=True))
    op.add_column("user", sa.Column("thbwiki_uid", sa.String(128), nullable=True))
    op.add_column("user", sa.Column("qq_openid", sa.String(128), nullable=True))

    for provider, column, verified_column in (
        ("email", "email", "email_verified"),
        ("phone", "phone_number", "phone_verified"),
        ("qq", "qq_openid", None),
        ("thbwiki", "thbwiki_uid", None),
    ):
        set_clause = f"{column} = i.subject"
        if verified_column:
            set_clause += f", {verified_column} = i.verified"
        op.execute(
            f"""
            UPDATE "user" u SET {set_clause}
              FROM user_identity i
             WHERE i.user_id = u.id AND i.provider = '{provider}'
            """
        )

    op.create_index(
        "ix_user_email_unique", "user", ["email"], unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )
    op.create_index(
        "ix_user_phone_unique", "user", ["phone_number"], unique=True,
        postgresql_where=sa.text("phone_number IS NOT NULL"),
    )
    op.create_index(
        "uq_user_thbwiki_uid", "user", ["thbwiki_uid"], unique=True,
        postgresql_where=sa.text("thbwiki_uid IS NOT NULL"),
    )
    op.create_index(
        "uq_user_qq_openid", "user", ["qq_openid"], unique=True,
        postgresql_where=sa.text("qq_openid IS NOT NULL"),
    )
    # Removed accounts have no identity rows, so the CHECK holds for them via
    # the ``removed = TRUE`` branch.
    op.create_check_constraint(
        "at_least_one_identifier",
        "user",
        "removed = TRUE OR phone_number IS NOT NULL OR email IS NOT NULL",
    )

    op.drop_index("ix_user_identity_user_id", table_name="user_identity")
    op.drop_table("user_identity")
