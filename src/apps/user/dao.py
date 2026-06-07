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

    async def find_by_thbwiki_uid(self, thbwiki_uid: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.thbwiki_uid == thbwiki_uid)
        )
        return result.scalar_one_or_none()

    async def find_by_qq_openid(self, qq_openid: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.qq_openid == qq_openid)
        )
        return result.scalar_one_or_none()

    async def search_users(
        self,
        email: str | None = None,
        phone: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list, int]:
        from sqlalchemy import func as sqlfunc
        query = select(User)
        if email:
            query = query.where(User.email.ilike(f"%{email}%"))
        if phone:
            query = query.where(User.phone_number.ilike(f"%{phone}%"))
        count_result = await self.session.execute(
            select(sqlfunc.count()).select_from(query.subquery())
        )
        total = count_result.scalar_one()
        result = await self.session.execute(
            query.order_by(User.id).offset((page - 1) * page_size).limit(page_size)
        )
        return result.scalars().all(), total

    async def get_by_id_any(self, user_id: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def set_removed(self, user_id: str, removed: bool) -> User | None:
        user = await self.get_by_id_any(user_id)
        if user is None:
            return None
        user.removed = removed
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
