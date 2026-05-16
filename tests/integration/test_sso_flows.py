import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_user_table_has_sso_columns(session_maker):
    """Migration 0004 must add thbwiki_uid and qq_openid to user table.

    Uses PRAGMA table_info for SQLite (local/CI in-memory) and falls back
    to information_schema for Postgres.
    """
    async with session_maker() as session:
        # Detect dialect
        dialect = session.bind.dialect.name  # type: ignore[union-attr]
        if dialect == "sqlite":
            result = await session.execute(text("PRAGMA table_info('user')"))
            # PRAGMA table_info returns rows: (cid, name, type, notnull, dflt_value, pk)
            cols = {row[1] for row in result.fetchall()}
        else:
            result = await session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'user' "
                    "AND column_name IN ('thbwiki_uid', 'qq_openid')"
                )
            )
            cols = {row[0] for row in result.fetchall()}

    assert "thbwiki_uid" in cols, "thbwiki_uid column missing"
    assert "qq_openid" in cols, "qq_openid column missing"


@pytest.mark.asyncio
async def test_bind_sso_sets_qq_column(session_maker, patch_redis):
    """bind_sso must write qq_openid into the user row when the column is NULL."""
    from datetime import datetime, timezone

    from sqlalchemy import select

    from src.apps.user.dao import ActivityLogDAO, UserDAO
    from src.apps.user.schemas import generate_user_id
    from src.apps.user.service import UserService
    from src.apps.user.utils.security import AuthProvider
    from src.common.config import get_settings
    from src.db_model.user import User

    settings = get_settings()
    auth = AuthProvider()

    async with session_maker() as session:
        user = User(
            id=generate_user_id(),
            email="bind_test@example.com",
            email_verified=True,
            register_ip_address="127.0.0.1",
            register_date=datetime.now(timezone.utc),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        session_token = auth.create_session_token(user.id)

        svc = UserService(
            user_dao=UserDAO(session),
            activity_dao=ActivityLogDAO(session_maker),
            email_code_service=None,
            sms_code_service=None,
            auth=auth,
            redis=patch_redis,
            settings=settings,
        )

        await svc.bind_sso(session_token, {"qq_openid": "test-openid-123"})

    async with session_maker() as session:
        u = await session.scalar(
            select(User).where(User.email == "bind_test@example.com")
        )
        assert u.qq_openid == "test-openid-123"


@pytest.mark.asyncio
async def test_bind_sso_409_when_openid_taken(session_maker, patch_redis):
    """bind_sso raises 409 AppException when the qq_openid belongs to another user."""
    from datetime import datetime, timezone

    from src.apps.user.dao import ActivityLogDAO, UserDAO
    from src.apps.user.schemas import generate_user_id
    from src.apps.user.service import UserService
    from src.apps.user.utils.security import AuthProvider
    from src.common.config import get_settings
    from src.common.exceptions import AppException
    from src.db_model.user import User

    settings = get_settings()
    auth = AuthProvider()

    async with session_maker() as session:
        now = datetime.now(timezone.utc)

        user1 = User(
            id=generate_user_id(),
            email="owner@example.com",
            email_verified=True,
            qq_openid="taken-openid",
            register_ip_address="127.0.0.1",
            register_date=now,
        )
        user2 = User(
            id=generate_user_id(),
            email="thief@example.com",
            email_verified=True,
            register_ip_address="127.0.0.1",
            register_date=now,
        )
        session.add_all([user1, user2])
        await session.commit()

        token2 = auth.create_session_token(user2.id)

        svc = UserService(
            user_dao=UserDAO(session),
            activity_dao=ActivityLogDAO(session_maker),
            email_code_service=None,
            sms_code_service=None,
            auth=auth,
            redis=patch_redis,
            settings=settings,
        )

        with pytest.raises(AppException) as exc_info:
            await svc.bind_sso(token2, {"qq_openid": "taken-openid"})
        assert "SSO_ID_ALREADY_BOUND" in str(exc_info.value)
