"""Data access for the user module.

Three DAOs are colocated here because they share the same session and
their write paths interleave inside service-layer flows:
- ``UserDAO`` for the ``user`` (account) table.
- ``UserIdentityDAO`` for ``user_identity`` lookups.
- ``ActivityLogDAO`` for the ``activity_log`` audit table.

Identity rows are *written* through the ``User.identities`` collection
(append / remove / clear) followed by ``UserDAO.save`` — the ORM cascade
turns that into INSERT / DELETE, so there is exactly one commit path.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db_model.activity_log import ActivityLog
from src.db_model.user import User
from src.db_model.user_identity import UserIdentity


class UserDAO:
    """CRUD for the ``user`` table.

    ``get_by_id`` excludes soft-deleted (``removed=True``) accounts so a
    session token of a deleted account stops working; ``get_by_id_any``
    is for admin tooling that must see them.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.id == user_id, User.removed.is_(False))
        )
        return result.scalar_one_or_none()

    async def get_by_id_any(self, user_id: str) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create(self, user: User) -> User:
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def save(self, user: User) -> User:
        """Commit in-place modifications (columns and the identities
        collection) on a managed user instance."""
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def search_users(
        self,
        email: str | None = None,
        phone: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[User], int]:
        query = select(User)
        if email:
            query = query.where(_has_identity_like("email", email))
        if phone:
            query = query.where(_has_identity_like("phone", phone))
        count_result = await self.session.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar_one()
        result = await self.session.execute(
            query.order_by(User.id).offset((page - 1) * page_size).limit(page_size)
        )
        return list(result.scalars().all()), total

    async def set_removed(self, user_id: str, removed: bool) -> User | None:
        user = await self.get_by_id_any(user_id)
        if user is None:
            return None
        user.removed = removed
        await self.session.commit()
        await self.session.refresh(user)
        return user


def _has_identity_like(provider: str, pattern: str):
    return User.identities.any(
        and_(
            UserIdentity.provider == provider,
            UserIdentity.subject.ilike(f"%{pattern}%"),
        )
    )


class UserIdentityDAO:
    """Read side of ``user_identity``.

    Lookups deliberately do *not* filter on ``User.removed``: the
    ``(provider, subject)`` unique constraint is absolute, so callers need
    to see a banned account's identity to answer "is this subject taken".
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_identity(self, provider: str, subject: str) -> UserIdentity | None:
        result = await self.session.execute(
            select(UserIdentity).where(
                UserIdentity.provider == provider,
                UserIdentity.subject == subject,
            )
        )
        return result.scalar_one_or_none()

    async def find_user(self, provider: str, subject: str) -> User | None:
        """The account owning ``(provider, subject)``, removed or not."""
        result = await self.session.execute(
            select(User)
            .join(User.identities)
            .where(
                UserIdentity.provider == provider,
                UserIdentity.subject == subject,
            )
        )
        return result.scalar_one_or_none()


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
