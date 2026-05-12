"""Activity log model for auditing user operations.

Maps to the Rust user-manager's voter_logs collection.
Records all security-relevant user actions for audit trails.
"""

from __future__ import annotations

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ActivityLog(Base):
    """Audit log for user-related operations.

    Event types (mirrors Rust ActivityLogEntry enum):
        send_email, send_sms, voter_creation, voter_login,
        update_email, update_phone, update_nickname,
        update_password, remove_voter
    """

    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    event_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )

    user_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )

    target_email: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    target_phone: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )

    old_value: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )

    new_value: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )

    detail: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    requester_ip: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )

    additional_fingerprint: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
