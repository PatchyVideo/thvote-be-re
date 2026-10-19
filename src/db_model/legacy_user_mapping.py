"""Bridge between legacy Mongo voter ids and new UUID user ids.

The legacy import deliberately does not reuse Mongo ``ObjectId`` values as
``user.id`` (new accounts use UUID4).  This table is the only durable link
between an old ``voters._id`` and the account created for it, so it also
carries the import batch id for precise rollback and the role that explains
why the row exists:

- ``primary``: the record whose data became the account;
- ``duplicate``: a duplicate record merged into the same account;
- ``conflict_existing``: the old record matched an account that already
  existed in the target database and was not imported again.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

MAPPING_ROLE_VALUES: tuple[str, ...] = (
    "primary",
    "duplicate",
    "conflict_existing",
)


class LegacyUserMapping(Base):
    __tablename__ = "legacy_user_mapping"

    legacy_object_id: Mapped[str] = mapped_column(String(24), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    # Import batch: lets the rollback script delete exactly one run.
    batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "role IN (" + ", ".join(f"'{v}'" for v in MAPPING_ROLE_VALUES) + ")",
            name="ck_legacy_user_mapping_role",
        ),
    )
