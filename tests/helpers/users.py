"""Test helper: build a User account with identity rows in one call.

Replaces the pre-2026-09-06 ``User(email=..., phone=...)`` constructions —
contact identifiers now live in ``user_identity``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.user.schemas import generate_user_id
from src.apps.user.utils.security import AuthProvider
from src.db_model.user import User
from src.db_model.user_identity import UserIdentity


def build_user(
    *,
    user_id: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    qq: str | None = None,
    thbwiki: str | None = None,
    password: str | None = None,
    nickname: str | None = None,
    removed: bool = False,
    verified: bool = True,
    register_ip: str = "127.0.0.1",
) -> User:
    """Return an unsaved User with one identity per non-None identifier."""
    now = datetime.now(UTC)
    user = User(
        id=user_id or generate_user_id(),
        nickname=nickname,
        password_hash=AuthProvider.hash_password(password) if password else None,
        removed=removed,
        register_date=now,
        register_ip_address=register_ip,
    )
    for provider, subject in (
        ("email", email),
        ("phone", phone),
        ("qq", qq),
        ("thbwiki", thbwiki),
    ):
        if subject is None:
            continue
        user.identities.append(
            UserIdentity(
                provider=provider,
                subject=subject,
                verified=verified,
                verified_at=now if verified else None,
                created_at=now,
                created_ip=register_ip,
            )
        )
    return user


async def make_user(session: AsyncSession, **kwargs) -> User:
    """``build_user`` + commit + refresh."""
    user = build_user(**kwargs)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
