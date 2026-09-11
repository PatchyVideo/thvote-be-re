"""``UserDAO.save()`` 的 session 归属契约（B-024 / U-18）。

save() 只接受**本 session 托管**的实例，detached 实例一律报错。这不是保守，
是因为 ``User.identities`` 是 ``delete-orphan``：用 ``session.merge()`` 接纳一个
陈旧副本会按副本重建该集合，DB 里有、副本里没有的绑定会被当成 orphan 删掉；
同一次盲写还会把 ``removed`` 覆盖回去（解封）、把已硬删的行重新 INSERT 出来
（复活）。下面四个用例分别钉住正常路径与这三种损坏。

账号一律经 ``tests.helpers.users.make_user`` 构造——2026-09-06 起联系标识
（email/phone/qq/thbwiki）已归一化到 ``user_identity``，``User(email=...)``
不再是合法构造方式。
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import InvalidRequestError

from src.apps.user.dao import UserDAO
from src.db_model.user import User
from src.db_model.user_identity import UserIdentity
from tests.helpers.users import make_user


async def _providers(session, user_id: str) -> list[str]:
    result = await session.execute(
        select(UserIdentity.provider).where(UserIdentity.user_id == user_id)
    )
    return sorted(result.scalars().all())


async def _removed(session, user_id: str) -> bool | None:
    result = await session.execute(select(User.removed).where(User.id == user_id))
    return result.scalar_one_or_none()


@pytest.mark.asyncio
async def test_save_commits_managed_instance(session):
    """正常路径（现网所有 caller）：托管实例传入 → 落库、返回同一实例。"""
    dao = UserDAO(session)
    user = await make_user(session, email="attached@example.com", nickname="before")

    loaded = await dao.get_by_id(user.id)
    assert loaded is user                    # 同一身份映射实例

    loaded.nickname = "edited-while-attached"
    saved = await dao.save(loaded)
    assert saved is loaded                   # 托管实例原样返回

    # populate_existing 强制一次 DB 往返，确认值真的落库而非读缓存
    row = (await session.execute(
        select(User).where(User.id == user.id)
        .execution_options(populate_existing=True)
    )).scalar_one()
    assert row.nickname == "edited-while-attached"


@pytest.mark.asyncio
async def test_save_rejects_detached_instance(session):
    dao = UserDAO(session)
    user = await make_user(session, email="detached@example.com", nickname="before")

    session.expunge(user)
    user.nickname = "edited-while-detached"

    with pytest.raises(InvalidRequestError, match="managed by this session"):
        await dao.save(user)


@pytest.mark.asyncio
async def test_save_does_not_drop_identities_bound_elsewhere(session):
    """陈旧副本不得删掉别处新建的绑定（delete-orphan + merge 的经典事故）。"""
    dao = UserDAO(session)
    user = await make_user(session, email="keep@example.com", nickname="before")
    session.expunge(user)                    # 副本里 identities 只有 email

    now = datetime.now(UTC)
    await session.execute(insert(UserIdentity).values(
        user_id=user.id, provider="phone", subject="13800000000",
        verified=True, verified_at=now, created_at=now, created_ip="",
    ))
    await session.commit()
    assert await _providers(session, user.id) == ["email", "phone"]

    user.nickname = "edited"
    with pytest.raises(InvalidRequestError):
        await dao.save(user)

    assert await _providers(session, user.id) == ["email", "phone"]


@pytest.mark.asyncio
async def test_save_does_not_resurrect_or_unban(session):
    """陈旧副本不得把封禁覆盖回未封禁，也不得把硬删的账号重新 INSERT。"""
    dao = UserDAO(session)
    banned = await make_user(session, email="banned@example.com", nickname="before")
    session.expunge(banned)
    await session.execute(
        update(User).where(User.id == banned.id).values(removed=True)
    )
    await session.commit()

    banned.nickname = "edited"
    with pytest.raises(InvalidRequestError):
        await dao.save(banned)
    assert await _removed(session, banned.id) is True

    gone = await make_user(session, email="gone@example.com", nickname="before")
    gone_id = gone.id
    session.expunge(gone)
    await session.execute(delete(UserIdentity).where(UserIdentity.user_id == gone_id))
    await session.execute(delete(User).where(User.id == gone_id))
    await session.commit()

    gone.nickname = "edited"
    with pytest.raises(InvalidRequestError):
        await dao.save(gone)
    assert await _removed(session, gone_id) is None
