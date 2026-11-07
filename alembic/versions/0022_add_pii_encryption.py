"""0022 add encrypted PII columns and migrate the identity unique constraint.

Adds AES-GCM ciphertext columns and HMAC blind-index columns so the plaintext
``subject`` / ``register_ip_address`` / ``created_ip`` can be retired:

- ``user_identity.subject_enc`` / ``subject_idx``   (email/phone/qq/thbwiki)
- ``user_identity.created_ip_enc``                  (per-identity bind IP)
- ``user.register_ip_enc`` / ``register_ip_prefix`` (account register IP + /24)

The old plaintext columns are kept (made nullable, server defaults dropped) so
they end up NULL for every new write; migration 0023 drops them after the
import has been verified.  The ``(provider, subject)`` unique constraint is
replaced by ``(provider, subject_idx)`` so equality lookup keeps working on the
blind index.

``register_ip_prefix`` is a plain ``String`` (CIDR ``a.b.c.0/24``) rather than
``INET`` to keep the ORM model portable across Postgres and the sqlite test
database; there is no range-query consumer yet.
"""

from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Encrypted + blind-index columns.
    op.add_column(
        "user_identity", sa.Column("subject_enc", sa.LargeBinary(), nullable=True)
    )
    op.add_column(
        "user_identity", sa.Column("subject_idx", sa.LargeBinary(), nullable=True)
    )
    op.add_column(
        "user_identity", sa.Column("created_ip_enc", sa.LargeBinary(), nullable=True)
    )
    op.add_column("user", sa.Column("register_ip_enc", sa.LargeBinary(), nullable=True))
    op.add_column(
        "user", sa.Column("register_ip_prefix", sa.String(length=64), nullable=True)
    )

    # Plaintext columns become NULL-able; drop the "" server defaults so a
    # missing value is NULL (and the §10.2 "is not null → 0" scan holds).
    op.alter_column(
        "user_identity",
        "subject",
        existing_type=sa.String(length=255),
        nullable=True,
    )
    op.alter_column(
        "user",
        "register_ip_address",
        existing_type=sa.String(length=64),
        nullable=True,
        server_default=None,
    )
    op.alter_column(
        "user_identity",
        "created_ip",
        existing_type=sa.String(length=64),
        nullable=True,
        server_default=None,
    )

    # Unique constraint migrates from plaintext subject to the blind index.
    op.drop_constraint(
        "uq_user_identity_provider_subject", "user_identity", type_="unique"
    )
    op.create_index(
        "uq_user_identity_provider_idx",
        "user_identity",
        ["provider", "subject_idx"],
        unique=True,
    )
    op.create_index(
        "ix_user_identity_subject_idx", "user_identity", ["subject_idx"]
    )


def downgrade() -> None:
    op.drop_index("ix_user_identity_subject_idx", table_name="user_identity")
    op.drop_index("uq_user_identity_provider_idx", table_name="user_identity")
    op.create_unique_constraint(
        "uq_user_identity_provider_subject",
        "user_identity",
        ["provider", "subject"],
    )
    op.alter_column(
        "user_identity",
        "created_ip",
        existing_type=sa.String(length=64),
        nullable=False,
        server_default="",
    )
    op.alter_column(
        "user",
        "register_ip_address",
        existing_type=sa.String(length=64),
        nullable=False,
        server_default="",
    )
    op.alter_column(
        "user_identity",
        "subject",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.drop_column("user", "register_ip_prefix")
    op.drop_column("user", "register_ip_enc")
    op.drop_column("user_identity", "created_ip_enc")
    op.drop_column("user_identity", "subject_idx")
    op.drop_column("user_identity", "subject_enc")
