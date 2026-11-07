"""One authentication source of one user account.

A ``User`` row is the account (nickname, password, registration metadata);
each ``UserIdentity`` row is one way to reach it: an e-mail address, a phone
number, a QQ openid, a THBWiki uid.  See
docs/superpowers/specs/2026-09-06-user-identity-model-design.md §3.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.common.crypto import aad_for, decrypt

from .base import Base

if TYPE_CHECKING:
    from .user import User

# Kept in sync with src/apps/user/identity.py::IdentityProvider.  Widening
# this tuple is a schema change (migration must recreate the CHECK).
PROVIDER_CHECK_VALUES: tuple[str, ...] = ("email", "phone", "qq", "thbwiki")


class UserIdentity(Base):
    __tablename__ = "user_identity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    # Plaintext subject stays NULL for new writes (encrypted into subject_enc
    # / subject_idx); migration 0023 drops this column after import is verified.
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    subject_idx: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # "When / from where was this identity attached" — anti-abuse evidence
    # at identity granularity (the account-level register_* stay as-is).
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_ip_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_device_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default="", server_default=""
    )
    last_login_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="identities")

    @property
    def subject_plain(self) -> str | None:
        """Decrypted subject, falling back to the legacy plaintext column."""
        if self.subject_enc is not None:
            return decrypt(
                self.subject_enc,
                aad_for("user_identity", "subject", self.user_id),
            )
        return self.subject

    @property
    def created_ip_plain(self) -> str:
        """Decrypted bind IP, falling back to the legacy plaintext column."""
        if self.created_ip_enc is not None:
            value = decrypt(
                self.created_ip_enc,
                aad_for("user_identity", "created_ip", self.user_id),
            )
            return value or ""
        return self.created_ip or ""

    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_user_identity_user_provider"),
        Index(
            "uq_user_identity_provider_idx",
            "provider",
            "subject_idx",
            unique=True,
        ),
        Index("ix_user_identity_subject_idx", "subject_idx"),
        CheckConstraint(
            "provider IN (" + ", ".join(f"'{v}'" for v in PROVIDER_CHECK_VALUES) + ")",
            name="ck_user_identity_provider",
        ),
    )
