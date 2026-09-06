"""User account model.

An account holds what is *about the person*: nickname, avatar, password,
soft-delete flag and registration evidence.  How the person authenticates
lives in ``user_identity`` (one row per e-mail / phone / QQ / THBWiki) —
see ``user_identity.py`` and the 2026-09-06 identity-model spec.
"""

from __future__ import annotations

from sqlalchemy import Boolean, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .user_identity import UserIdentity


class User(Base):
    __tablename__ = "user"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    password_hash: Mapped[str | None] = mapped_column(String(512), nullable=True)

    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pfp: Mapped[str | None] = mapped_column(String(512), nullable=True)

    removed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    register_date: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    register_ip_address: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )
    # 注册时的客户端设备指纹(localStorage UUID),反刷票取证用(B-044)。
    register_device_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default="", server_default=""
    )

    # selectin: every account load brings its (<=4) identities in one extra
    # query, so async code never trips a lazy load.
    identities: Mapped[list[UserIdentity]] = relationship(
        back_populates="user",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def identity(self, provider: str) -> UserIdentity | None:
        """Return this account's identity for *provider*, if any."""
        for identity in self.identities:
            if identity.provider == provider:
                return identity
        return None


Index("idx_user_register_date", User.register_date)
