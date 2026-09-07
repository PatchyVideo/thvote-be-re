"""Account ⇄ identity operations shared by every login / bind / unbind flow.

``UserService`` orchestrates requests (codes, tokens, audit); this module
owns the four things that touch ``user_identity``:

- ``resolve``   — who owns ``(provider, subject)``?  Rejects banned owners.
- ``register``  — new account + its first identity, from one ``Meta``.
- ``bind``      — attach / replace an identity with conflict detection
                  (spec §5.1 ``_bind_identity``).
- ``unbind_all`` — soft-delete support: drop every identity row.

Provider-specific branching is confined to ``normalize_subject``; nothing
here knows what an e-mail or an openid looks like.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from src.apps.user.dao import UserDAO, UserIdentityDAO
from src.apps.user.identity import IdentityProvider, normalize_subject
from src.apps.user.schemas import Meta, generate_user_id
from src.common.exceptions import UnauthorizedError, ValidationError
from src.db_model.user import User
from src.db_model.user_identity import UserIdentity


@dataclass(frozen=True)
class BindResult:
    identity: UserIdentity
    replaced_subject: str | None  # previous subject for this provider, if any
    changed: bool  # False when the identity was already bound as-is


@dataclass
class IdentityService:
    user_dao: UserDAO
    identity_dao: UserIdentityDAO

    async def resolve(
        self, provider: IdentityProvider, raw_subject: str
    ) -> User | None:
        """Return the active account owning the identity, or None if unbound.

        Raises ``UnauthorizedError(USER_REMOVED, 403)`` when the owner is a
        soft-deleted / banned account: its identity rows are kept so an
        admin unban restores it, so the subject must not silently re-register.
        """
        subject = normalize_subject(provider, raw_subject)
        user = await self.identity_dao.find_user(provider.value, subject)
        if user is None:
            return None
        if user.removed:
            raise UnauthorizedError("USER_REMOVED", details=403)
        return user

    async def register(
        self,
        provider: IdentityProvider,
        raw_subject: str,
        nickname: str | None,
        meta: Meta,
    ) -> User:
        """Create an account whose first identity is ``(provider, subject)``.

        The account's ``register_*`` and the identity's ``created_*`` are
        filled from the same ``meta`` on purpose (spec §3.1).
        """
        subject = normalize_subject(provider, raw_subject)
        now = datetime.now(UTC)
        user = User(
            id=generate_user_id(),
            nickname=nickname,
            register_ip_address=meta.user_ip or "",
            register_device_id=meta.additional_fingureprint or "",
        )
        user.identities.append(
            _new_identity(provider, subject, meta, now, last_login_at=now)
        )
        return await self.user_dao.create(user)

    async def bind(
        self,
        user: User,
        provider: IdentityProvider,
        raw_subject: str,
        meta: Meta,
        conflict_code: str,
    ) -> BindResult:
        """Attach ``(provider, subject)`` to *user*.

        - Owned by another account (banned or not) → ``ValidationError``
          with *conflict_code*, HTTP 409.
        - Already bound to *user* as-is → no-op.
        - *user* has another subject for this provider → replace it (the
          new row carries this request's ``created_*``).
        """
        subject = normalize_subject(provider, raw_subject)
        existing = await self.identity_dao.find_identity(provider.value, subject)
        if existing is not None and existing.user_id != user.id:
            raise ValidationError(conflict_code, details=409)
        if existing is not None:
            return BindResult(identity=existing, replaced_subject=None, changed=False)

        current = user.identity(provider.value)
        replaced = current.subject if current is not None else None
        if current is not None:
            # Flush the DELETE before the INSERT: the unit of work would
            # otherwise emit INSERT first and trip uq_user_identity_user_provider.
            user.identities.remove(current)
            await self.identity_dao.session.flush()
        identity = _new_identity(provider, subject, meta, datetime.now(UTC))
        user.identities.append(identity)
        await self.user_dao.save(user)
        return BindResult(identity=identity, replaced_subject=replaced, changed=True)

    async def touch_login(self, user: User, provider: IdentityProvider) -> None:
        identity = user.identity(provider.value)
        if identity is None:
            return
        identity.last_login_at = datetime.now(UTC)
        await self.user_dao.save(user)

    async def unbind_all(self, user: User) -> None:
        """Delete every identity row (ORM delete-orphan cascade on commit)."""
        user.identities.clear()
        await self.user_dao.save(user)


def _new_identity(
    provider: IdentityProvider,
    subject: str,
    meta: Meta,
    now: datetime,
    *,
    last_login_at: datetime | None = None,
) -> UserIdentity:
    # Every creation path today runs after verification (code / OAuth), so
    # verified is always True here; the column exists for future
    # "record first, verify later" flows (spec §3.4).
    return UserIdentity(
        provider=provider.value,
        subject=subject,
        verified=True,
        verified_at=now,
        created_at=now,
        created_ip=meta.user_ip or "",
        created_device_id=meta.additional_fingureprint or "",
        last_login_at=last_login_at,
    )
