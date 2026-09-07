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
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    subject: Mapped[str] = mapped_column(String(255), nullable=False)

    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # "When / from where was this identity attached" — anti-abuse evidence
    # at identity granularity (the account-level register_* stay as-is).
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_ip: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )
    created_device_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default="", server_default=""
    )
    last_login_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="identities")

    __table_args__ = (
        UniqueConstraint(
            "provider", "subject", name="uq_user_identity_provider_subject"
        ),
        UniqueConstraint("user_id", "provider", name="uq_user_identity_user_provider"),
        CheckConstraint(
            "provider IN (" + ", ".join(f"'{v}'" for v in PROVIDER_CHECK_VALUES) + ")",
            name="ck_user_identity_provider",
        ),
    )
