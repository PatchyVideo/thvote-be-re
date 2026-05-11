from sqlalchemy import Boolean, CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class User(Base):
    """User database model.

    Stores user account information including authentication credentials
    and registration metadata.  Field set aligned with Rust user-manager
    Voter struct (MongoDB thvote_users.voters).
    """

    __tablename__ = "user"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    phone_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    password_hash: Mapped[str | None] = mapped_column(String(512), nullable=True)
    legacy_salt: Mapped[str | None] = mapped_column(String(255), nullable=True)

    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pfp: Mapped[str | None] = mapped_column(String(512), nullable=True)

    removed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    register_date: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    register_ip_address: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )

    __table_args__ = (
        # Soft-deleted rows are allowed to have both identifiers cleared
        # (mirrors Rust remove_voter behavior).  Active rows must keep at
        # least one identifier so we can locate them via login.
        CheckConstraint(
            "removed = TRUE OR phone_number IS NOT NULL OR email IS NOT NULL",
            name="at_least_one_identifier",
        ),
    )
