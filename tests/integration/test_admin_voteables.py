"""B-057①:GET /admin/voteables 列表 + POST /admin/voteables/{id} 改 work_id。

复用 test_admin_routes_ext 的 app/db_session/admin_secret 夹具(同一 sqlite
内存引擎 + require_admin 环境)。
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.db_model.voteable import VoteableCharacter, VoteableMusic
from src.db_model.work import Work
from tests.integration.test_admin_routes_ext import (  # noqa: F401
    admin_secret,
    app,
    db_session,
    engine,
)

__all__ = ["engine", "app", "db_session", "admin_secret"]


async def _seed(db_session) -> dict:
    """一个 work + 两个角色(一个挂 work 一个不挂)+ 一个音乐。"""
    work = Work(name="东方风神录", type="old")
    db_session.add(work)
    await db_session.flush()
    sanae = VoteableCharacter(
        name="东风谷早苗",
        name_jp="東風谷早苗",
        type="new",
        work_id=work.id,
        image_url="https://cdn.example.com/sanae.png",
        aliases=["早苗", "sanae"],
    )
    reimu = VoteableCharacter(name="博丽灵梦", work_id=None)
    faith = VoteableMusic(
        name="信仰是为了虚幻之人",
        work_id=work.id,
        image_url="https://cdn.example.com/faith.jpg",
        music_url="https://cdn.example.com/faith.mp3",
        include=["东方风神录"],
    )
    db_session.add_all([sanae, reimu, faith])
    await db_session.commit()
    return {
        "work_id": work.id, "sanae_id": sanae.id,
        "reimu_id": reimu.id, "faith_id": faith.id,
    }


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_list_voteables_with_work_fields(app, db_session, admin_secret):
    ids = await _seed(db_session)
    async with _client(app) as ac:
        resp = await ac.get(
            "/api/v1/admin/voteables?category=character",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    by_id = {row["id"]: row for row in data["items"]}
    sanae = by_id[ids["sanae_id"]]
    assert sanae["name"] == "东风谷早苗"
    assert sanae["nameJp"] == "東風谷早苗"
    assert sanae["workId"] == ids["work_id"]
    assert sanae["workName"] == "东方风神录"
    assert sanae["workType"] == "old"
    reimu = by_id[ids["reimu_id"]]
    assert reimu["workId"] is None and reimu["workName"] is None
    # 资源字段
    assert sanae["imageUrl"] == "https://cdn.example.com/sanae.png"
    assert sanae["aliases"] == ["早苗", "sanae"]
    assert reimu["imageUrl"] is None and reimu["aliases"] == []


@pytest.mark.asyncio
async def test_list_voteables_search_and_pagination(app, db_session, admin_secret):
    await _seed(db_session)
    headers = {"X-Admin-Secret": admin_secret}
    async with _client(app) as ac:
        resp = await ac.get(
            "/api/v1/admin/voteables?category=character&q=早苗", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        resp2 = await ac.get(
            "/api/v1/admin/voteables?category=character&page=2&page_size=1",
            headers=headers,
        )
        assert resp2.status_code == 200
        body = resp2.json()
        assert body["total"] == 2 and len(body["items"]) == 1


@pytest.mark.asyncio
async def test_list_voteables_invalid_category(app, db_session, admin_secret):
    async with _client(app) as ac:
        resp = await ac.get(
            "/api/v1/admin/voteables?category=cp",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_voteable_work(app, db_session, admin_secret):
    ids = await _seed(db_session)
    work2 = Work(name="东方红魔乡", type="old")
    db_session.add(work2)
    await db_session.commit()
    headers = {"X-Admin-Secret": admin_secret}
    async with _client(app) as ac:
        # 改挂到另一个 work
        resp = await ac.post(
            f"/api/v1/admin/voteables/{ids['reimu_id']}",
            json={"category": "character", "work_id": work2.id},
            headers=headers,
        )
        assert resp.status_code == 200 and resp.json()["ok"] is True
        # 清空关联
        resp = await ac.post(
            f"/api/v1/admin/voteables/{ids['sanae_id']}",
            json={"category": "character", "work_id": None},
            headers=headers,
        )
        assert resp.status_code == 200
        # 不存在的 work → 409
        resp = await ac.post(
            f"/api/v1/admin/voteables/{ids['reimu_id']}",
            json={"category": "character", "work_id": 99999},
            headers=headers,
        )
        assert resp.status_code == 409
        # 不存在的 voteable → 404
        resp = await ac.post(
            "/api/v1/admin/voteables/99999",
            json={"category": "character", "work_id": None},
            headers=headers,
        )
        assert resp.status_code == 404
    row = (await db_session.execute(
        select(VoteableCharacter).where(VoteableCharacter.id == ids["reimu_id"])
    )).scalar_one()
    await db_session.refresh(row)
    assert row.work_id == work2.id
    row2 = (await db_session.execute(
        select(VoteableCharacter).where(VoteableCharacter.id == ids["sanae_id"])
    )).scalar_one()
    await db_session.refresh(row2)
    assert row2.work_id is None


@pytest.mark.asyncio
async def test_voteables_require_admin(app, db_session):
    async with _client(app) as ac:
        resp = await ac.get("/api/v1/admin/voteables?category=character")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_voteables_music_resource_fields(app, db_session, admin_secret):
    await _seed(db_session)
    async with _client(app) as ac:
        resp = await ac.get(
            "/api/v1/admin/voteables?category=music",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 200
    row = resp.json()["items"][0]
    assert row["imageUrl"] == "https://cdn.example.com/faith.jpg"
    assert row["musicUrl"] == "https://cdn.example.com/faith.mp3"
    assert row["include"] == ["东方风神录"]


@pytest.mark.asyncio
async def test_update_voteable_resources_character(app, db_session, admin_secret):
    ids = await _seed(db_session)
    headers = {"X-Admin-Secret": admin_secret}
    async with _client(app) as ac:
        # 部分更新：只给 image_url + aliases
        resp = await ac.put(
            f"/api/v1/admin/voteables/{ids['reimu_id']}/resources",
            json={"category": "character",
                  "image_url": "https://cdn.example.com/reimu.png",
                  "aliases": ["灵梦", "红白"]},
            headers=headers,
        )
        assert resp.status_code == 200 and resp.json()["ok"] is True
        # 空串 → 清空 image_url；aliases 并集
        resp = await ac.put(
            f"/api/v1/admin/voteables/{ids['sanae_id']}/resources",
            json={"category": "character", "image_url": "  ",
                  "aliases": ["青蛙子"]},
            headers=headers,
        )
        assert resp.status_code == 200

    db_session.expire_all()
    reimu = (await db_session.execute(
        select(VoteableCharacter).where(VoteableCharacter.id == ids["reimu_id"])
    )).scalar_one()
    assert reimu.image_url == "https://cdn.example.com/reimu.png"
    assert reimu.aliases == ["灵梦", "红白"]
    sanae = (await db_session.execute(
        select(VoteableCharacter).where(VoteableCharacter.id == ids["sanae_id"])
    )).scalar_one()
    assert sanae.image_url is None  # 清空
    assert sanae.aliases == ["青蛙子"]  # 管理端语义=整体替换


@pytest.mark.asyncio
async def test_update_voteable_resources_music(app, db_session, admin_secret):
    ids = await _seed(db_session)
    headers = {"X-Admin-Secret": admin_secret}
    async with _client(app) as ac:
        resp = await ac.put(
            f"/api/v1/admin/voteables/{ids['faith_id']}/resources",
            json={"category": "music",
                  "music_url": "https://cdn.example.com/new.mp3",
                  "include": ["东方地灵殿"],
                  "image_url": "https://cdn.example.com/new.jpg"},
            headers=headers,
        )
        assert resp.status_code == 200
    db_session.expire_all()
    faith = (await db_session.execute(
        select(VoteableMusic).where(VoteableMusic.id == ids["faith_id"])
    )).scalar_one()
    assert faith.music_url == "https://cdn.example.com/new.mp3"
    assert faith.include == ["东方地灵殿"]  # 管理端语义=整体替换
    assert faith.image_url == "https://cdn.example.com/new.jpg"


@pytest.mark.asyncio
async def test_update_voteable_resources_validation(app, db_session, admin_secret):
    ids = await _seed(db_session)
    headers = {"X-Admin-Secret": admin_secret}
    async with _client(app) as ac:
        # 非 http(s) → 422
        resp = await ac.put(
            f"/api/v1/admin/voteables/{ids['reimu_id']}/resources",
            json={"category": "character", "image_url": "javascript:alert(1)"},
            headers=headers,
        )
        assert resp.status_code == 422
        # 不存在的 voteable → 404
        resp = await ac.put(
            "/api/v1/admin/voteables/999999/resources",
            json={"category": "character", "image_url": "https://x/y.png"},
            headers=headers,
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_voteable_resources_requires_admin(app, db_session):
    ids = await _seed(db_session)
    async with _client(app) as ac:
        resp = await ac.put(
            f"/api/v1/admin/voteables/{ids['reimu_id']}/resources",
            json={"category": "character", "image_url": "https://x/y.png"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cache_stats_and_flush(app, db_session, admin_secret):
    """管理端缓存计数 + 手动刷新 + 白名单 scope 校验 + 鉴权。"""
    await _seed(db_session)
    headers = {"X-Admin-Secret": admin_secret}
    async with _client(app) as ac:
        # 触发公共接口写缓存（无候选也会写空响应缓存）
        r = await ac.get("/api/v1/vote-objects/characters?vote_year=2026")
        assert r.status_code == 200

        stats = (await ac.get("/api/v1/admin/cache/stats", headers=headers)).json()
        assert stats["counts"]["vote_objects"] >= 1
        assert "vote_objects" in stats["scopes"]

        flush = await ac.post(
            "/api/v1/admin/cache/flush",
            json={"scope": "vote_objects"},
            headers=headers,
        )
        assert flush.status_code == 200
        body = flush.json()
        assert body["ok"] is True and body["total"] >= 1

        stats2 = (await ac.get("/api/v1/admin/cache/stats", headers=headers)).json()
        assert stats2["counts"]["vote_objects"] == 0

        # 未知 scope → 422（白名单，不接受任意 pattern）
        bad = await ac.post(
            "/api/v1/admin/cache/flush", json={"scope": "nope"}, headers=headers
        )
        assert bad.status_code == 422

        # scope=all 正常
        allflush = await ac.post(
            "/api/v1/admin/cache/flush", json={"scope": "all"}, headers=headers
        )
        assert allflush.status_code == 200 and allflush.json()["ok"] is True

        # 无 secret → 403（路由级 require_admin）
        noauth = await ac.post(
            "/api/v1/admin/cache/flush", json={"scope": "all"}
        )
        assert noauth.status_code == 403
