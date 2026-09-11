"""UserDAO.save() detached 实例回归测试（B-024 / U-18）。

save() 现走 ``session.merge()``：
- detached 实例传入 → 更新必须落库，不再静默 no-op，并返回新的托管实例；
- attached 实例（现网所有调用方的形态）→ 行为不变、返回原实例。

账号一律经 ``tests.helpers.users.make_user`` 构造——2026-09-06 起联系标识
（email/phone/qq/thbwiki）已归一化到 ``user_identity``，``User(email=...)``
不再是合法构造方式。
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from src.apps.user.dao import UserDAO
from src.db_model.user import User
from tests.helpers.users import make_user


async def _db_value(session, user_id: str) -> User:
    """绕过身份映射强制一次 DB 往返，确认值真的落库而非读缓存。"""
    result = await session.execute(
        select(User)
        .where(User.id == user_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


@pytest.mark.asyncio
async def test_save_persists_detached_instance_changes(session):
    dao = UserDAO(session)
    user = await make_user(session, email="detached@example.com", nickname="before")

    # 把实例 detach 后再改字段——历史上 save() 会对一个没跟踪任何实例的
    # session commit（静默 no-op），随后才在 refresh(detached) 处抛错。
    session.expunge(user)
    user.nickname = "edited-while-detached"

    saved = await dao.save(user)

    assert saved is not user                 # merge() 对 detached 返回新托管对象
    assert saved.nickname == "edited-while-detached"

    row = await _db_value(session, user.id)  # populate_existing：强制 DB 往返
    assert row is saved                      # 返回的正是 session 绑定实例（身份映射命中）
    assert row is not user                   # 传入的 detached 原对象未被重新入 session
    assert row.nickname == "edited-while-detached"


@pytest.mark.asyncio
async def test_save_attached_instance_keeps_identity(session):
    """常见路径（现网所有 caller）：attached 实例传入 → 身份保持不变。"""
    dao = UserDAO(session)
    user = await make_user(session, email="attached@example.com", nickname="before")

    loaded = await dao.get_by_id(user.id)
    assert loaded is user                    # 同一身份映射实例

    loaded.nickname = "edited-while-attached"
    saved = await dao.save(loaded)

    assert saved is loaded                   # merge() 对 attached 是透传

    row = await _db_value(session, user.id)  # populate_existing：强制 DB 往返
    assert row is saved
    assert row.nickname == "edited-while-attached"
