"""Data access for the user module.

Two DAOs are colocated here because they share the same session and
their write paths interleave inside service-layer flows:
- ``UserDAO`` for the ``user`` table.
- ``ActivityLogDAO`` for the ``activity_log`` audit table.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db_model.activity_log import ActivityLog
from src.db_model.user import User


class UserDAO:
    """CRUD for the ``user`` table.

    Active users always have ``removed=False``; lookups exclude removed
    rows so a soft-deleted account does not block re-registration with
    the same email/phone.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.id == user_id, User.removed.is_(False))
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.email == email, User.removed.is_(False))
        )
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.phone_number == phone, User.removed.is_(False))
        )
        return result.scalar_one_or_none()

    async def create(self, user: User) -> User:
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def save(self, user: User) -> User:
        """Flush in-place modifications on a managed user instance."""
        await self.session.commit()
        await self.session.refresh(user)
        return user


class ActivityLogDAO:
    """Append-only writes to the ``activity_log`` audit table.

    Writes live in their own session/transaction so an audit failure
    cannot poison the primary business transaction.  The constructor
    accepts a session_maker rather than a session for that reason.
    """

    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        self._session_maker = session_maker

    async def write(self, **fields: Any) -> None:
        """Insert one row.  Raises whatever the DB raises — callers wrap."""
        entry = ActivityLog(**fields)
        async with self._session_maker() as session:
            session.add(entry)
            await session.commit()
