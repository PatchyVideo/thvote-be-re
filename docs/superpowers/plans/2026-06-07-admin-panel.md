# 管理端扩展 (Admin Panel) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 扩展管理端：在现有 3 个端点基础上，新增用户管理、投票统计、排名预览、候选项管理、审计日志、CSV 导出共 12 个 REST 端点，并提供一个单文件原生 JS Web UI 托管在 `/admin-ui`。

**Architecture:** 现有 `src/apps/admin/` 扩展 service/schema/router；新增 DAO 方法加到 `src/apps/user/dao.py` 和 `src/apps/result/compute_dao.py`；Web UI 是单个 `src/admin_ui/index.html`，由 FastAPI `StaticFiles` 挂载。

**Tech Stack:** FastAPI, SQLAlchemy async, Python 3.12, 原生 HTML/CSS/JS（无框架）

**Design Spec:** `docs/superpowers/specs/2026-06-07-admin-panel-design.md`

---

## File Map

| 文件 | 操作 | 说明 |
|---|---|---|
| `src/apps/user/dao.py` | Modify | 新增 `search_users()`, `get_by_id_any()`, `set_removed()` |
| `src/apps/result/compute_dao.py` | Modify | 新增 `delete_candidate()`, `list_candidates()` |
| `src/apps/admin/service.py` | Modify | 新增 `AdminService` 方法：stats, preview, users, candidates, logs, export |
| `src/apps/admin/schemas.py` | Modify | 新增 UserAdminItem, StatsResponse, CandidateListResponse 等 |
| `src/apps/admin/router.py` | Modify | 新增 12 个端点 |
| `src/admin_ui/index.html` | **Create** | 单文件 Web UI |
| `src/main.py` | Modify | 挂载 StaticFiles |
| `tests/unit/test_admin_service_ext.py` | **Create** | AdminService 新方法单元测试 |
| `tests/integration/test_admin_routes_ext.py` | **Create** | 新端点集成测试 |
| `tests/contract/test_admin_endpoints_ext.py` | **Create** | 新端点 contract 测试 |

---

## Task 1: UserDAO 扩展 + 用户管理端点（TDD）

**Files:**
- Modify: `src/apps/user/dao.py`
- Modify: `src/apps/admin/schemas.py`
- Modify: `src/apps/admin/service.py`
- Modify: `src/apps/admin/router.py`
- Create: `tests/integration/test_admin_routes_ext.py`

- [ ] **Step 1: 写失败集成测试**

创建 `tests/integration/test_admin_routes_ext.py`：

```python
"""Integration tests for admin panel extensions."""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text


@pytest.mark.asyncio
async def test_search_users_by_email(app, db_session, admin_secret):
    """Search by email returns matching user."""
    # Create a user via raw SQL to avoid coupling with user service
    await db_session.execute(
        text(
            "INSERT INTO \"user\" (id, email, email_verified, phone_verified, removed) "
            "VALUES ('aaa', 'find@example.com', true, false, false)"
        )
    )
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/admin/users?email=find@example.com",
            headers={"X-Admin-Secret": admin_secret},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(u["email"] == "find@example.com" for u in data["items"])


@pytest.mark.asyncio
async def test_ban_and_unban_user(app, db_session, admin_secret):
    await db_session.execute(
        text(
            "INSERT INTO \"user\" (id, email, email_verified, phone_verified, removed) "
            "VALUES ('bbb', 'ban@example.com', true, false, false)"
        )
    )
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Ban
        resp = await ac.patch("/admin/users/bbb/ban",
                              headers={"X-Admin-Secret": admin_secret})
        assert resp.status_code == 200
        assert resp.json()["removed"] is True

        # Unban
        resp = await ac.patch("/admin/users/bbb/unban",
                              headers={"X-Admin-Secret": admin_secret})
        assert resp.status_code == 200
        assert resp.json()["removed"] is False


@pytest.mark.asyncio
async def test_get_user_detail(app, db_session, admin_secret):
    await db_session.execute(
        text(
            "INSERT INTO \"user\" (id, email, email_verified, phone_verified, removed) "
            "VALUES ('ccc', 'detail@example.com', true, false, false)"
        )
    )
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/admin/users/ccc",
                            headers={"X-Admin-Secret": admin_secret})

    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["id"] == "ccc"
    assert "vote_submitted" in data
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/integration/test_admin_routes_ext.py -xvs
```

Expected: 404 (端点不存在) 或 ImportError

- [ ] **Step 3: 在 user/dao.py 末尾追加新方法**

```python
    async def search_users(
        self,
        email: str | None = None,
        phone: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[User], int]:
        from sqlalchemy import func as sqlfunc, or_
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
        """Get user regardless of removed status (admin use)."""
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
```

- [ ] **Step 4: 在 schemas.py 追加用户管理模型**

```python
# ── User admin schemas ─────────────────────────────────────────────────────────

class UserAdminItem(BaseModel):
    id: str
    nickname: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    email_verified: bool = False
    phone_verified: bool = False
    register_date: Optional[str] = None
    removed: bool = False


class UserListResponse(BaseModel):
    items: list[UserAdminItem]
    total: int


class UserDetailResponse(BaseModel):
    user: UserAdminItem
    vote_submitted: dict[str, bool]


class BanResponse(BaseModel):
    ok: bool = True
    removed: bool
```

- [ ] **Step 5: 在 service.py 追加用户管理方法**

在 `AdminService.__init__` 的参数中增加 `session: AsyncSession`（同时在现有 `get_admin_service` 依赖中传入）。

在 `AdminService` 类末尾追加：

```python
    async def list_users(
        self, email: str | None, phone: str | None, page: int, page_size: int
    ) -> dict:
        from src.apps.user.dao import UserDAO
        from src.apps.vote_data.dao import VoteDataDAO

        user_dao = UserDAO(self._session)
        users, total = await user_dao.search_users(email, phone, page, page_size)
        return {"items": users, "total": total}

    async def get_user_detail(self, user_id: str) -> dict | None:
        from src.apps.user.dao import UserDAO
        from src.apps.vote_data.dao import VoteDataDAO

        user_dao = UserDAO(self._session)
        user = await user_dao.get_by_id_any(user_id)
        if user is None:
            return None
        vote_dao = VoteDataDAO(self._session)
        char = await vote_dao.get_character_by_id(user_id)
        music = await vote_dao.get_music_by_id(user_id)
        cp = await vote_dao.get_cp_by_id(user_id)
        questionnaire = await vote_dao.get_questionnaire_by_id(user_id)
        vote_submitted = {
            "character": char is not None,
            "music": music is not None,
            "cp": cp is not None,
            "paper": questionnaire is not None,
            "dojin": False,
        }
        return {"user": user, "vote_submitted": vote_submitted}

    async def ban_user(self, user_id: str) -> object | None:
        from src.apps.user.dao import UserDAO
        dao = UserDAO(self._session)
        return await dao.set_removed(user_id, removed=True)

    async def unban_user(self, user_id: str) -> object | None:
        from src.apps.user.dao import UserDAO
        dao = UserDAO(self._session)
        return await dao.set_removed(user_id, removed=False)
```

Also update `AdminService.__init__` and `get_admin_service` to thread `session` through:

In `AdminService.__init__`:
```python
    def __init__(self, compute_service: ComputeService, compute_dao: ComputeDAO, session: AsyncSession = None):
        self.compute_service = compute_service
        self.compute_dao = compute_dao
        self._session = session
```

In `router.py`'s `get_admin_service`:
```python
async def get_admin_service(
    session: AsyncSession = Depends(get_db_session),
    redis: aioredis.Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> AdminService:
    compute_dao = ComputeDAO(session)
    compute_svc = ComputeService(compute_dao, redis, settings)
    return AdminService(compute_svc, compute_dao, session)
```

- [ ] **Step 6: 在 router.py 追加用户管理端点**

```python
from src.apps.admin.schemas import (
    UserListResponse, UserDetailResponse, BanResponse,
)


@router.get("/users", response_model=UserListResponse)
async def list_users(
    email: Optional[str] = None,
    phone: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> UserListResponse:
    _check_admin_secret(settings, x_admin_secret)
    data = await service.list_users(email, phone, page, page_size)
    items = [
        {
            "id": u.id,
            "nickname": u.nickname,
            "email": u.email,
            "phone": u.phone_number,
            "email_verified": u.email_verified,
            "phone_verified": u.phone_verified,
            "register_date": u.register_date.isoformat() if u.register_date else None,
            "removed": u.removed,
        }
        for u in data["items"]
    ]
    return UserListResponse(items=items, total=data["total"])


@router.get("/users/{user_id}", response_model=UserDetailResponse)
async def get_user_detail(
    user_id: str,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> UserDetailResponse:
    _check_admin_secret(settings, x_admin_secret)
    result = await service.get_user_detail(user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")
    u = result["user"]
    summary = result["vote_submitted"]
    return UserDetailResponse(
        user={
            "id": u.id, "nickname": u.nickname, "email": u.email,
            "phone": u.phone_number, "email_verified": u.email_verified,
            "phone_verified": u.phone_verified,
            "register_date": u.register_date.isoformat() if u.register_date else None,
            "removed": u.removed,
        },
        vote_submitted=result["vote_submitted"],
    )


@router.patch("/users/{user_id}/ban", response_model=BanResponse)
async def ban_user(
    user_id: str,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> BanResponse:
    _check_admin_secret(settings, x_admin_secret)
    user = await service.ban_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")
    return BanResponse(removed=user.removed)


@router.patch("/users/{user_id}/unban", response_model=BanResponse)
async def unban_user(
    user_id: str,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> BanResponse:
    _check_admin_secret(settings, x_admin_secret)
    user = await service.unban_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")
    return BanResponse(removed=user.removed)
```

- [ ] **Step 7: 运行集成测试**

```bash
pytest tests/integration/test_admin_routes_ext.py -xvs
```

Expected: 3 tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/apps/user/dao.py src/apps/admin/service.py src/apps/admin/schemas.py src/apps/admin/router.py tests/integration/test_admin_routes_ext.py
git commit -m "feat(admin): user management endpoints (search/detail/ban/unban) (B-035)"
```

---

## Task 2: Stats 端点

**Files:**
- Modify: `src/apps/admin/service.py`
- Modify: `src/apps/admin/schemas.py`
- Modify: `src/apps/admin/router.py`

- [ ] **Step 1: 在 schemas.py 追加**

```python
class VoteWindowStatus(BaseModel):
    status: str  # open / closed / upcoming
    start: str
    end: str


class StatsResponse(BaseModel):
    vote_year: int
    total_users: int
    vote_window: VoteWindowStatus
    submissions: dict[str, int]
```

- [ ] **Step 2: 在 service.py 追加 get_stats()**

```python
    async def get_stats(self, vote_year: int | None = None) -> dict:
        from datetime import datetime, timezone
        from sqlalchemy import func as sqlfunc
        from src.db_model.user import User
        from src.db_model.raw_submit import (
            RawCharacterSubmit, RawMusicSubmit, RawCPSubmit, RawPaperSubmit, RawDojinSubmit,
        )

        year = vote_year or self.compute_service.settings.vote_year
        settings = self.compute_service.settings

        now = datetime.now(timezone.utc)
        start = datetime.fromisoformat(settings.vote_start_iso.replace("Z", "+00:00"))
        end = datetime.fromisoformat(settings.vote_end_iso.replace("Z", "+00:00"))
        if now < start:
            window_status = "upcoming"
        elif now > end:
            window_status = "closed"
        else:
            window_status = "open"

        total_users = (await self._session.execute(
            select(sqlfunc.count()).select_from(User).where(User.removed.is_(False))
        )).scalar_one()

        async def _count(model, id_col):
            return (await self._session.execute(
                select(sqlfunc.count(sqlfunc.distinct(id_col)))
                .select_from(model)
            )).scalar_one()

        return {
            "vote_year": year,
            "total_users": total_users,
            "vote_window": {
                "status": window_status,
                "start": settings.vote_start_iso,
                "end": settings.vote_end_iso,
            },
            "submissions": {
                "character": await _count(RawCharacterSubmit, RawCharacterSubmit.vote_id),
                "music": await _count(RawMusicSubmit, RawMusicSubmit.vote_id),
                "cp": await _count(RawCPSubmit, RawCPSubmit.vote_id),
                "paper": await _count(RawPaperSubmit, RawPaperSubmit.vote_id),
                "dojin": await _count(RawDojinSubmit, RawDojinSubmit.vote_id),
            },
        }
```

- [ ] **Step 3: 在 router.py 追加端点**

```python
from src.apps.admin.schemas import StatsResponse


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    vote_year: Optional[int] = None,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> StatsResponse:
    _check_admin_secret(settings, x_admin_secret)
    data = await service.get_stats(vote_year)
    return StatsResponse(**data)
```

- [ ] **Step 4: 在集成测试文件末尾追加测试**

```python
@pytest.mark.asyncio
async def test_stats_shape(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/admin/stats", headers={"X-Admin-Secret": admin_secret})
    assert resp.status_code == 200
    data = resp.json()
    assert "total_users" in data
    assert "submissions" in data
    assert "character" in data["submissions"]
    assert data["vote_window"]["status"] in ("open", "closed", "upcoming")
```

- [ ] **Step 5: 运行**

```bash
pytest tests/integration/test_admin_routes_ext.py::test_stats_shape -xvs
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/apps/admin/service.py src/apps/admin/schemas.py src/apps/admin/router.py
git commit -m "feat(admin): GET /admin/stats endpoint (B-035)"
```

---

## Task 3: 排名预览 + 候选项管理

**Files:**
- Modify: `src/apps/result/compute_dao.py`
- Modify: `src/apps/admin/service.py`
- Modify: `src/apps/admin/schemas.py`
- Modify: `src/apps/admin/router.py`

- [ ] **Step 1: 在 compute_dao.py 追加候选项 DAO 方法**

打开 `src/apps/result/compute_dao.py`，在类末尾追加：

```python
    async def list_candidates(
        self,
        category: str,
        vote_year: int,
        q: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list, int]:
        from sqlalchemy import func as sqlfunc
        from src.db_model.candidate import CandidateCharacter, CandidateMusic

        model = CandidateCharacter if category == "character" else CandidateMusic
        query = select(model).where(model.vote_year == vote_year)
        if q:
            query = query.where(model.name.ilike(f"%{q}%"))

        total = (await self.session.execute(
            select(sqlfunc.count()).select_from(query.subquery())
        )).scalar_one()
        rows = (await self.session.execute(
            query.order_by(model.name).offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()
        return rows, total

    async def delete_candidate(self, candidate_id: int, category: str) -> bool:
        from sqlalchemy import delete
        from src.db_model.candidate import CandidateCharacter, CandidateMusic

        model = CandidateCharacter if category == "character" else CandidateMusic
        result = await self.session.execute(
            delete(model).where(model.id == candidate_id)
        )
        await self.session.commit()
        return result.rowcount > 0
```

- [ ] **Step 2: 在 schemas.py 追加**

```python
class CandidateAdminItem(BaseModel):
    id: int
    vote_year: int
    name: str
    name_jp: str = ""
    type: str = ""
    origin: Optional[str] = None
    first_appearance: Optional[str] = None
    album: Optional[str] = None


class CandidateListResponse(BaseModel):
    items: list[CandidateAdminItem]
    total: int
```

- [ ] **Step 3: 在 service.py 追加预览和候选项方法**

```python
    async def get_ranking_preview(
        self, vote_year: int | None, category: str, limit: int
    ) -> list[dict]:
        import json
        year = vote_year or self.compute_service.settings.vote_year
        cat_key = {"character": "chars", "music": "musics", "cp": "cps"}.get(category)
        if not cat_key:
            return []
        key = f"result:{year}:{cat_key}:ranking"
        raw = await self.compute_service.redis.get(key)
        if not raw:
            return []
        entries = json.loads(raw)
        return entries[:limit]

    async def list_candidates(
        self, category: str, vote_year: int, q: str | None, page: int, page_size: int
    ) -> dict:
        rows, total = await self.compute_dao.list_candidates(
            category, vote_year, q, page, page_size
        )
        return {"items": rows, "total": total}

    async def delete_candidate(self, candidate_id: int, category: str) -> bool:
        return await self.compute_dao.delete_candidate(candidate_id, category)
```

- [ ] **Step 4: 在 router.py 追加端点**

```python
from src.apps.admin.schemas import CandidateListResponse


@router.get("/ranking/preview")
async def preview_ranking(
    category: str = "character",
    vote_year: Optional[int] = None,
    limit: int = 50,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    entries = await service.get_ranking_preview(vote_year, category, limit)
    return {"category": category, "entries": entries}


@router.get("/candidates", response_model=CandidateListResponse)
async def list_candidates(
    category: str = "character",
    vote_year: Optional[int] = None,
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> CandidateListResponse:
    _check_admin_secret(settings, x_admin_secret)
    year = vote_year or settings.vote_year
    data = await service.list_candidates(category, year, q, page, page_size)
    items = [
        {
            "id": r.id, "vote_year": r.vote_year, "name": r.name,
            "name_jp": r.name_jp or "",
            "type": r.type or "",
            "origin": getattr(r, "origin", None),
            "first_appearance": r.first_appearance,
            "album": getattr(r, "album", None),
        }
        for r in data["items"]
    ]
    return CandidateListResponse(items=items, total=data["total"])


@router.delete("/candidates/{candidate_id}")
async def delete_candidate(
    candidate_id: int,
    category: str = "character",
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    deleted = await service.delete_candidate(candidate_id, category)
    if not deleted:
        raise HTTPException(status_code=404, detail="CANDIDATE_NOT_FOUND")
    return {"ok": True}
```

- [ ] **Step 5: 在集成测试追加 candidate 测试**

```python
@pytest.mark.asyncio
async def test_list_candidates_empty(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/admin/candidates?category=character&vote_year=2024",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0
```

- [ ] **Step 6: 运行**

```bash
pytest tests/integration/test_admin_routes_ext.py -xvs
```

Expected: 全部 PASS

- [ ] **Step 7: Commit**

```bash
git add src/apps/result/compute_dao.py src/apps/admin/service.py src/apps/admin/schemas.py src/apps/admin/router.py
git commit -m "feat(admin): ranking preview + candidate list/delete endpoints (B-035)"
```

---

## Task 4: 审计日志查询 + CSV 导出

**Files:**
- Modify: `src/apps/admin/service.py`
- Modify: `src/apps/admin/schemas.py`
- Modify: `src/apps/admin/router.py`

- [ ] **Step 1: 在 schemas.py 追加**

```python
class ActivityLogItem(BaseModel):
    id: int
    event_type: str
    user_id: Optional[str] = None
    requester_ip: Optional[str] = None
    created_at: str


class ActivityLogResponse(BaseModel):
    items: list[ActivityLogItem]
    total: int
```

- [ ] **Step 2: 在 service.py 追加**

```python
    async def list_activity_logs(
        self,
        user_id: str | None,
        action: str | None,
        since: str | None,
        page: int,
        page_size: int,
    ) -> dict:
        from datetime import datetime, timezone
        from sqlalchemy import func as sqlfunc, desc
        from src.db_model.activity_log import ActivityLog

        query = select(ActivityLog)
        if user_id:
            query = query.where(ActivityLog.user_id == user_id)
        if action:
            query = query.where(ActivityLog.event_type == action)
        if since:
            dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            query = query.where(ActivityLog.created_at >= dt)

        total = (await self._session.execute(
            select(sqlfunc.count()).select_from(query.subquery())
        )).scalar_one()
        rows = (await self._session.execute(
            query.order_by(desc(ActivityLog.created_at))
            .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()
        return {"items": rows, "total": total}

    async def export_votes_csv(self, vote_year: int, category: str):
        """Yield CSV rows as strings (header first, then data)."""
        from src.db_model.raw_submit import (
            RawCharacterSubmit, RawMusicSubmit, RawCPSubmit,
            RawPaperSubmit, RawDojinSubmit,
        )
        _models = {
            "character": RawCharacterSubmit,
            "music": RawMusicSubmit,
            "cp": RawCPSubmit,
            "paper": RawPaperSubmit,
            "dojin": RawDojinSubmit,
        }
        model = _models.get(category)
        if model is None:
            return

        yield "vote_id,attempt,created_at,user_ip,payload\n"

        offset = 0
        batch = 500
        while True:
            rows = (await self._session.execute(
                select(model).order_by(model.id).offset(offset).limit(batch)
            )).scalars().all()
            if not rows:
                break
            for r in rows:
                import json as _json
                payload = getattr(r, "payload", None) or getattr(r, "papers_json", "")
                payload_str = _json.dumps(payload, ensure_ascii=False).replace('"', '""')
                created = r.created_at.isoformat() if r.created_at else ""
                yield f'"{r.vote_id}",{r.attempt or ""},"{created}","{r.user_ip}","{payload_str}"\n'
            offset += batch
```

- [ ] **Step 3: 在 router.py 追加端点**

```python
from fastapi.responses import StreamingResponse
from src.apps.admin.schemas import ActivityLogResponse


@router.get("/activity-logs", response_model=ActivityLogResponse)
async def list_activity_logs(
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    since: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> ActivityLogResponse:
    _check_admin_secret(settings, x_admin_secret)
    data = await service.list_activity_logs(user_id, action, since, page, page_size)
    items = [
        {
            "id": r.id, "event_type": r.event_type,
            "user_id": r.user_id, "requester_ip": r.requester_ip,
            "created_at": r.created_at.isoformat(),
        }
        for r in data["items"]
    ]
    return ActivityLogResponse(items=items, total=data["total"])


@router.get("/export/votes")
async def export_votes(
    vote_year: int,
    category: str,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    _check_admin_secret(settings, x_admin_secret)
    filename = f"votes_{vote_year}_{category}.csv"
    return StreamingResponse(
        service.export_votes_csv(vote_year, category),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 4: 在集成测试追加测试**

```python
@pytest.mark.asyncio
async def test_activity_logs_empty(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/admin/activity-logs",
                            headers={"X-Admin-Secret": admin_secret})
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_export_votes_csv(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/admin/export/votes?vote_year=2024&category=character",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert resp.text.startswith("vote_id,attempt,")
```

- [ ] **Step 5: 运行**

```bash
pytest tests/integration/test_admin_routes_ext.py -xvs
```

Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add src/apps/admin/service.py src/apps/admin/schemas.py src/apps/admin/router.py
git commit -m "feat(admin): activity-logs + CSV export endpoints (B-035)"
```

---

## Task 5: Contract 测试

**Files:**
- Create: `tests/contract/test_admin_endpoints_ext.py`

- [ ] **Step 1: 写 contract 测试**

创建 `tests/contract/test_admin_endpoints_ext.py`：

```python
"""Contract tests for admin panel extension endpoints."""
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_users_403_without_secret(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        assert (await ac.get("/admin/users")).status_code == 403


@pytest.mark.asyncio
async def test_users_list_shape(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/admin/users", headers={"X-Admin-Secret": admin_secret})
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data and "total" in data


@pytest.mark.asyncio
async def test_stats_shape(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/admin/stats", headers={"X-Admin-Secret": admin_secret})
    assert resp.status_code == 200
    data = resp.json()
    assert {"vote_year", "total_users", "vote_window", "submissions"} <= data.keys()


@pytest.mark.asyncio
async def test_candidates_shape(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/admin/candidates?category=character&vote_year=2024",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data and "total" in data


@pytest.mark.asyncio
async def test_activity_logs_shape(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/admin/activity-logs",
                            headers={"X-Admin-Secret": admin_secret})
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data and "total" in data


@pytest.mark.asyncio
async def test_export_votes_content_type(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/admin/export/votes?vote_year=2024&category=character",
            headers={"X-Admin-Secret": admin_secret},
        )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")
```

- [ ] **Step 2: 运行**

```bash
pytest tests/contract/test_admin_endpoints_ext.py -xvs
```

Expected: 6 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/contract/test_admin_endpoints_ext.py
git commit -m "test(admin): contract tests for admin panel extensions (B-035)"
```

---

## Task 6: Web UI + StaticFiles 挂载

**Files:**
- Create: `src/admin_ui/index.html`
- Modify: `src/main.py`

- [ ] **Step 1: 在 main.py 挂载 StaticFiles**

打开 `src/main.py`，在 `create_app()` 函数里、`return app` 之前，追加：

```python
    import os
    from fastapi.staticfiles import StaticFiles
    admin_ui_dir = os.path.join(os.path.dirname(__file__), "admin_ui")
    if os.path.isdir(admin_ui_dir):
        app.mount("/admin-ui", StaticFiles(directory=admin_ui_dir, html=True), name="admin_ui")
```

And add `StaticFiles` to the imports block if not present:
```python
from fastapi.staticfiles import StaticFiles
```

- [ ] **Step 2: 创建 src/admin_ui/index.html**

创建目录 `src/admin_ui/`，新建 `index.html`：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>THVote Admin</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #111; color: #e0e0e0; min-height: 100vh; }
  #login-overlay { position: fixed; inset: 0; background: #111; display: flex; align-items: center; justify-content: center; z-index: 100; }
  #login-box { background: #1e1e1e; padding: 2rem; border-radius: 8px; width: 320px; }
  #login-box h2 { margin-bottom: 1rem; color: #fff; }
  #login-box input { width: 100%; padding: .6rem; background: #2a2a2a; border: 1px solid #444; color: #e0e0e0; border-radius: 4px; margin-bottom: .8rem; }
  #login-error { color: #f66; font-size: .85rem; margin-bottom: .5rem; min-height: 1.2em; }
  nav { background: #1e1e1e; padding: .8rem 1.5rem; display: flex; gap: .5rem; align-items: center; border-bottom: 1px solid #333; }
  nav span { color: #aaa; margin-right: auto; font-weight: bold; }
  nav button { background: none; border: none; color: #aaa; cursor: pointer; padding: .4rem .8rem; border-radius: 4px; }
  nav button.active, nav button:hover { background: #2a2a2a; color: #fff; }
  #content { padding: 1.5rem; }
  .card { background: #1e1e1e; border-radius: 8px; padding: 1.2rem; margin-bottom: 1rem; }
  .stats-row { display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }
  .stat-card { background: #2a2a2a; border-radius: 6px; padding: 1rem 1.5rem; min-width: 140px; }
  .stat-card .val { font-size: 1.8rem; font-weight: bold; color: #7af; }
  .stat-card .lbl { font-size: .8rem; color: #888; margin-top: .2rem; }
  input[type=text], input[type=number], select { background: #2a2a2a; border: 1px solid #444; color: #e0e0e0; padding: .5rem .7rem; border-radius: 4px; }
  button.btn { background: #2a5cc7; border: none; color: #fff; padding: .5rem 1rem; border-radius: 4px; cursor: pointer; }
  button.btn:hover { background: #3a6ed7; }
  button.btn.danger { background: #c73a2a; }
  button.btn.danger:hover { background: #d74a3a; }
  button.btn.sm { padding: .3rem .6rem; font-size: .85rem; }
  table { width: 100%; border-collapse: collapse; font-size: .9rem; }
  th, td { text-align: left; padding: .5rem .7rem; border-bottom: 1px solid #2a2a2a; }
  th { color: #888; font-weight: normal; }
  .search-row { display: flex; gap: .5rem; margin-bottom: 1rem; flex-wrap: wrap; align-items: center; }
  .badge { display: inline-block; padding: .15rem .5rem; border-radius: 3px; font-size: .8rem; }
  .badge.open { background: #1a4a1a; color: #4f4; }
  .badge.closed { background: #3a1a1a; color: #f44; }
  .badge.upcoming { background: #3a3a1a; color: #ff4; }
  progress { width: 100%; height: 8px; }
  .progress-wrap { margin: .5rem 0; }
  .toast { position: fixed; bottom: 1.5rem; right: 1.5rem; background: #333; color: #eee; padding: .8rem 1.2rem; border-radius: 6px; z-index: 200; opacity: 0; transition: opacity .3s; pointer-events: none; }
  .toast.show { opacity: 1; }
</style>
</head>
<body>

<div id="login-overlay">
  <div id="login-box">
    <h2>THVote Admin</h2>
    <input id="secret-input" type="password" placeholder="Admin Secret" />
    <div id="login-error"></div>
    <button class="btn" onclick="doLogin()">进入</button>
  </div>
</div>

<nav id="main-nav" style="display:none">
  <span>THVote Admin</span>
  <button onclick="showTab('dashboard')" id="tab-dashboard" class="active">Dashboard</button>
  <button onclick="showTab('users')" id="tab-users">用户管理</button>
  <button onclick="showTab('sync')" id="tab-sync">数据同步</button>
  <button onclick="showTab('candidates')" id="tab-candidates">候选项</button>
  <button onclick="showTab('logs')" id="tab-logs">审计日志</button>
  <button onclick="showTab('export')" id="tab-export">导出</button>
  <button onclick="doLogout()" style="margin-left:auto;color:#f88">退出</button>
</nav>

<div id="content" style="display:none"></div>
<div id="toast" class="toast"></div>

<script>
let SECRET = '';
let syncPollTimer = null;

// ── auth ──────────────────────────────────────────────────────────────────────

async function doLogin() {
  const val = document.getElementById('secret-input').value.trim();
  const err = document.getElementById('login-error');
  err.textContent = '';
  try {
    const r = await fetch('/admin/stats', { headers: { 'X-Admin-Secret': val } });
    if (r.status === 403) { err.textContent = '密码错误'; return; }
    SECRET = val;
    sessionStorage.setItem('adminSecret', val);
    document.getElementById('login-overlay').style.display = 'none';
    document.getElementById('main-nav').style.display = 'flex';
    document.getElementById('content').style.display = 'block';
    showTab('dashboard');
  } catch (e) { err.textContent = '连接失败: ' + e.message; }
}

function doLogout() {
  sessionStorage.removeItem('adminSecret');
  SECRET = '';
  location.reload();
}

async function api(path, opts = {}) {
  const r = await fetch(path, {
    ...opts,
    headers: { 'X-Admin-Secret': SECRET, 'Content-Type': 'application/json', ...(opts.headers || {}) }
  });
  if (r.status === 403) { doLogout(); throw new Error('Unauthorized'); }
  return r;
}

function toast(msg, ms = 3000) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), ms);
}

// ── tabs ──────────────────────────────────────────────────────────────────────

function showTab(name) {
  document.querySelectorAll('nav button[id^=tab-]').forEach(b => b.classList.remove('active'));
  const btn = document.getElementById('tab-' + name);
  if (btn) btn.classList.add('active');
  if (syncPollTimer) { clearInterval(syncPollTimer); syncPollTimer = null; }
  const content = document.getElementById('content');
  content.innerHTML = '<div style="color:#666;padding:1rem">加载中…</div>';
  ({dashboard, users, sync, candidates, logs, export: exportTab}[name] || (() => {}))();
}

// ── dashboard ─────────────────────────────────────────────────────────────────

async function dashboard() {
  const r = await api('/admin/stats');
  const d = await r.json();
  const w = d.vote_window;
  document.getElementById('content').innerHTML = `
    <div class="stats-row">
      <div class="stat-card"><div class="val">${d.total_users}</div><div class="lbl">注册用户</div></div>
      <div class="stat-card"><div class="val">${d.submissions.character}</div><div class="lbl">角色投票</div></div>
      <div class="stat-card"><div class="val">${d.submissions.music}</div><div class="lbl">音乐投票</div></div>
      <div class="stat-card"><div class="val">${d.submissions.cp}</div><div class="lbl">CP 投票</div></div>
      <div class="stat-card"><div class="val"><span class="badge ${w.status}">${w.status}</span></div><div class="lbl">投票窗口</div></div>
    </div>
    <div class="card">
      <div style="display:flex;gap:.8rem;flex-wrap:wrap">
        <button class="btn" onclick="quickAction('compute-results','POST','触发排名计算？')">Compute Results</button>
        <button class="btn" onclick="quickAction('finalize-ranking','POST','归档最终排名？')">Finalize Ranking</button>
        <button class="btn" onclick="quickAction('reload-config','POST','热更新配置？')">Reload Config</button>
      </div>
    </div>`;
}

async function quickAction(endpoint, method, confirm_msg) {
  if (!confirm(confirm_msg)) return;
  try {
    const r = await api('/admin/' + endpoint, { method });
    const d = await r.json();
    toast(JSON.stringify(d).slice(0, 80));
  } catch (e) { toast('Error: ' + e.message); }
}

// ── users ─────────────────────────────────────────────────────────────────────

async function users() {
  document.getElementById('content').innerHTML = `
    <div class="card">
      <div class="search-row">
        <input type="text" id="u-email" placeholder="邮箱" style="width:200px" />
        <input type="text" id="u-phone" placeholder="手机号" style="width:160px" />
        <button class="btn" onclick="searchUsers(1)">搜索</button>
      </div>
      <div id="users-table"></div>
    </div>`;
}

async function searchUsers(page) {
  const email = document.getElementById('u-email').value;
  const phone = document.getElementById('u-phone').value;
  let url = `/admin/users?page=${page}&page_size=20`;
  if (email) url += '&email=' + encodeURIComponent(email);
  if (phone) url += '&phone=' + encodeURIComponent(phone);
  const r = await api(url);
  const d = await r.json();
  const rows = d.items.map(u => `<tr>
    <td style="font-family:monospace;font-size:.8rem">${u.id.slice(0,12)}…</td>
    <td>${u.nickname || '-'}</td>
    <td>${u.email || '-'}</td>
    <td>${u.phone || '-'}</td>
    <td>${u.email_verified ? '✓' : '-'}</td>
    <td><span class="badge ${u.removed ? 'closed' : 'open'}">${u.removed ? '封禁' : '正常'}</span></td>
    <td>
      ${u.removed
        ? `<button class="btn sm" onclick="toggleBan('${u.id}',false)">解封</button>`
        : `<button class="btn sm danger" onclick="toggleBan('${u.id}',true)">封禁</button>`}
    </td>
  </tr>`).join('');
  document.getElementById('users-table').innerHTML = `
    <table><thead><tr><th>ID</th><th>昵称</th><th>邮箱</th><th>手机</th><th>邮箱验证</th><th>状态</th><th>操作</th></tr></thead>
    <tbody>${rows}</tbody></table>
    <div style="margin-top:.8rem;color:#888">共 ${d.total} 条</div>`;
}

async function toggleBan(userId, ban) {
  if (!confirm(ban ? '确认封禁此用户？' : '确认解封此用户？')) return;
  await api(`/admin/users/${userId}/${ban ? 'ban' : 'unban'}`, { method: 'PATCH' });
  toast(ban ? '已封禁' : '已解封');
  searchUsers(1);
}

// ── sync ──────────────────────────────────────────────────────────────────────

async function sync() {
  document.getElementById('content').innerHTML = `
    <div class="card">
      <h3 style="margin-bottom:1rem">启动同步</h3>
      <div class="search-row">
        <input type="number" id="sync-batch" value="500" style="width:100px" /> 批次大小
        <button class="btn" onclick="startSync()">Start Sync</button>
        <button class="btn danger" onclick="cancelSync()">Cancel</button>
      </div>
      <div id="sync-progress" style="margin-top:1rem"></div>
    </div>
    <div class="card">
      <h3 style="margin-bottom:.8rem">历史记录</h3>
      <div id="sync-history"></div>
    </div>`;
  await loadSyncHistory();
  syncPollTimer = setInterval(pollSyncStatus, 2000);
}

async function startSync() {
  const batch = parseInt(document.getElementById('sync-batch').value) || 500;
  const r = await api('/admin/sync/start', {
    method: 'POST',
    body: JSON.stringify({ batch_size: batch, collections: [] }),
  });
  const d = await r.json();
  toast('Started: ' + d.run_id.slice(0, 8));
}

async function cancelSync() {
  await api('/admin/sync/cancel', { method: 'POST' });
  toast('Cancel signal sent');
}

async function pollSyncStatus() {
  const r = await api('/admin/sync/status');
  const d = await r.json();
  const el = document.getElementById('sync-progress');
  if (!el) return;
  if (d.status === 'idle' || !d.run_id) {
    el.innerHTML = '<span style="color:#888">无运行中的同步</span>';
    return;
  }
  const pct = d.total > 0 ? Math.round(d.processed / d.total * 100) : 0;
  el.innerHTML = `
    <div>Run: ${(d.run_id||'').slice(0,8)} | ${d.status} | 集合: ${d.current_collection || '-'}</div>
    <div class="progress-wrap"><progress value="${d.processed}" max="${d.total}"></progress></div>
    <div style="color:#888;font-size:.85rem">${d.processed}/${d.total} | 插入:${d.inserted} 跳过:${d.skipped} 错误:${d.errors}</div>`;
  if (d.status === 'completed' || d.status === 'failed') {
    await loadSyncHistory();
  }
}

async function loadSyncHistory() {
  const r = await api('/admin/sync/history');
  const d = await r.json();
  const el = document.getElementById('sync-history');
  if (!el) return;
  const rows = d.items.map(item => `<tr>
    <td style="font-family:monospace">${item.run_id.slice(0,8)}</td>
    <td>${item.started_at.slice(0,19)}</td>
    <td><span class="badge ${item.status === 'completed' ? 'open' : item.status === 'running' ? 'upcoming' : 'closed'}">${item.status}</span></td>
    <td>${(item.collections||[]).length} 集合</td>
    <td>${item.inserted}</td>
    <td>${item.errors}</td>
    <td><button class="btn sm" onclick="retrySyncRun('${item.run_id}')">Retry</button></td>
  </tr>`).join('');
  el.innerHTML = `<table><thead><tr><th>Run ID</th><th>开始时间</th><th>状态</th><th>集合</th><th>插入</th><th>错误</th><th>操作</th></tr></thead>
  <tbody>${rows}</tbody></table>`;
}

async function retrySyncRun(runId) {
  if (!confirm('从断点重试此运行？')) return;
  await api(`/admin/sync/retry/${runId}`, { method: 'POST' });
  toast('Retry started');
}

// ── candidates ────────────────────────────────────────────────────────────────

async function candidates() {
  document.getElementById('content').innerHTML = `
    <div class="card">
      <div class="search-row">
        <select id="c-cat"><option value="character">角色</option><option value="music">音乐</option></select>
        <input type="number" id="c-year" value="${new Date().getFullYear()}" style="width:80px" />
        <input type="text" id="c-q" placeholder="名称搜索" style="width:180px" />
        <button class="btn" onclick="searchCandidates(1)">搜索</button>
      </div>
      <div id="candidates-table"></div>
    </div>`;
}

async function searchCandidates(page) {
  const cat = document.getElementById('c-cat').value;
  const year = document.getElementById('c-year').value;
  const q = document.getElementById('c-q').value;
  let url = `/admin/candidates?category=${cat}&vote_year=${year}&page=${page}&page_size=50`;
  if (q) url += '&q=' + encodeURIComponent(q);
  const r = await api(url);
  const d = await r.json();
  const rows = d.items.map(i => `<tr>
    <td>${i.name}</td><td>${i.name_jp||''}</td><td>${i.type||''}</td>
    <td>${i.origin||i.album||''}</td><td>${i.first_appearance||''}</td>
    <td><button class="btn sm danger" onclick="deleteCandidate(${i.id},'${cat}')">删除</button></td>
  </tr>`).join('');
  document.getElementById('candidates-table').innerHTML = `
    <table><thead><tr><th>名称</th><th>日文名</th><th>类型</th><th>来源/专辑</th><th>首登</th><th>操作</th></tr></thead>
    <tbody>${rows}</tbody></table>
    <div style="margin-top:.8rem;color:#888">共 ${d.total} 条</div>`;
}

async function deleteCandidate(id, category) {
  if (!confirm('确认删除此候选项？')) return;
  await api(`/admin/candidates/${id}?category=${category}`, { method: 'DELETE' });
  toast('已删除');
  searchCandidates(1);
}

// ── logs ──────────────────────────────────────────────────────────────────────

async function logs() {
  document.getElementById('content').innerHTML = `
    <div class="card">
      <div class="search-row">
        <input type="text" id="l-uid" placeholder="user_id" style="width:200px" />
        <input type="text" id="l-action" placeholder="event_type" style="width:160px" />
        <input type="text" id="l-since" placeholder="since (ISO)" style="width:180px" />
        <button class="btn" onclick="searchLogs(1)">搜索</button>
      </div>
      <div id="logs-table"></div>
    </div>`;
}

async function searchLogs(page) {
  let url = `/admin/activity-logs?page=${page}&page_size=50`;
  const uid = document.getElementById('l-uid').value;
  const action = document.getElementById('l-action').value;
  const since = document.getElementById('l-since').value;
  if (uid) url += '&user_id=' + encodeURIComponent(uid);
  if (action) url += '&action=' + encodeURIComponent(action);
  if (since) url += '&since=' + encodeURIComponent(since);
  const r = await api(url);
  const d = await r.json();
  const rows = d.items.map(i => `<tr>
    <td>${i.created_at.slice(0,19)}</td>
    <td>${i.event_type}</td>
    <td style="font-family:monospace;font-size:.8rem">${(i.user_id||'-').slice(0,16)}</td>
    <td>${i.requester_ip||'-'}</td>
  </tr>`).join('');
  document.getElementById('logs-table').innerHTML = `
    <table><thead><tr><th>时间</th><th>事件</th><th>用户ID</th><th>IP</th></tr></thead>
    <tbody>${rows}</tbody></table>
    <div style="margin-top:.8rem;color:#888">共 ${d.total} 条</div>`;
}

// ── export ────────────────────────────────────────────────────────────────────

function exportTab() {
  document.getElementById('content').innerHTML = `
    <div class="card" style="max-width:400px">
      <h3 style="margin-bottom:1rem">导出投票数据 CSV</h3>
      <div class="search-row" style="flex-direction:column;align-items:flex-start;gap:.8rem">
        <div><label>年份：<input type="number" id="exp-year" value="${new Date().getFullYear()}" style="width:100px;margin-left:.5rem" /></label></div>
        <div><label>类别：
          <select id="exp-cat" style="margin-left:.5rem">
            <option value="character">角色</option>
            <option value="music">音乐</option>
            <option value="cp">CP</option>
            <option value="paper">问卷</option>
            <option value="dojin">同人</option>
          </select>
        </label></div>
        <button class="btn" onclick="downloadCSV()">Download CSV</button>
      </div>
    </div>`;
}

function downloadCSV() {
  const year = document.getElementById('exp-year').value;
  const cat = document.getElementById('exp-cat').value;
  const url = `/admin/export/votes?vote_year=${year}&category=${cat}`;
  const a = document.createElement('a');
  a.href = url;
  a.setAttribute('download', `votes_${year}_${cat}.csv`);
  // Add secret as query param isn't possible via anchor; use fetch + blob instead
  api(url).then(r => r.blob()).then(blob => {
    const bUrl = URL.createObjectURL(blob);
    a.href = bUrl;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(bUrl);
  });
}

// ── init ──────────────────────────────────────────────────────────────────────

window.addEventListener('load', () => {
  const saved = sessionStorage.getItem('adminSecret');
  if (saved) {
    SECRET = saved;
    document.getElementById('login-overlay').style.display = 'none';
    document.getElementById('main-nav').style.display = 'flex';
    document.getElementById('content').style.display = 'block';
    showTab('dashboard');
  }
  document.getElementById('secret-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') doLogin();
  });
});
</script>
</body>
</html>
```

- [ ] **Step 3: 验证服务启动后可访问 UI**

```bash
uvicorn src.main:app --reload
```

访问 `http://localhost:8000/admin-ui/`，确认登录页面正常显示。

- [ ] **Step 4: 手工验收清单**

- [ ] 登录成功后 Dashboard 加载并显示统计数字
- [ ] 用户管理：输入邮箱搜索，结果显示并可执行 Ban/Unban
- [ ] 数据同步：Start Sync 按钮返回 202，进度栏开始更新
- [ ] 候选项：能正常列出（需先 import-candidates）
- [ ] 审计日志：列表加载正常
- [ ] 导出：Download CSV 触发文件下载，内容首行为 `vote_id,attempt,...`
- [ ] 退出按钮清除 sessionStorage 并回到登录页

- [ ] **Step 5: Commit**

```bash
git add src/admin_ui/index.html src/main.py
git commit -m "feat(admin): single-file Web UI + StaticFiles mount (B-035)"
```

---

## Task 7: 全套测试 + BACKLOG 更新

- [ ] **Step 1: 全套测试**

```bash
pytest tests/ -q
```

Expected: 全部 PASS，无回归

- [ ] **Step 2: 更新 BACKLOG.md**

将 B-035 的状态标注为已完成，格式参照其他已完成项：

```
| **B-035** | ~~管理端扩展（REST API + Web UI）~~ | ✅ 已完成 (2026-06-XX, commit hash) | — | ... |
```

- [ ] **Step 3: 最终 Commit**

```bash
git add docs/BACKLOG.md
git commit -m "docs: mark B-035 completed in BACKLOG"
```
