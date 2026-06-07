# 候选项管理增强 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给管理端候选项 Tab 增加 CSV/JSON 导入(dry-run 预览)、单条编辑(=详情页)、列表完善,并把整个管理端改为白色主题。

**Architecture:** 后端解析+校验(`candidate_service.py` 纯函数,CSV 用 `csv.DictReader`/JSON 用 `json.loads`),字段集合从模型列推导(insertSelective 语义)。新增 3 个端点(fields/import/edit),复用现有 `upsert_candidates`/`list_candidates`/`delete_candidate`。前端在单文件 `index.html` 内改主题 + 加三界面。

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, Python `csv`/`json`, 原生 HTML/CSS/JS

**Design Spec:** `docs/superpowers/specs/2026-06-08-candidate-management-design.md`

---

## File Map

| 文件 | 操作 | 说明 |
|---|---|---|
| `src/apps/admin/candidate_service.py` | **Create** | 纯函数:`candidate_field_specs`、`parse_content`、`validate_items` |
| `src/apps/result/compute_dao.py` | Modify | 加 `update_candidate()` |
| `src/apps/admin/service.py` | Modify | 加 `get_candidate_fields`、`import_candidates_from_content`、`update_candidate` |
| `src/apps/admin/schemas.py` | Modify | 加 fields/import/edit 的 request/response 模型 |
| `src/apps/admin/router.py` | Modify | 加 3 端点 |
| `src/admin_ui/index.html` | Modify | 主题改白 + 候选项 Tab 三界面 |
| `tests/unit/test_candidate_import.py` | **Create** | parse/validate/fields 单元测试 |
| `tests/integration/test_candidate_admin.py` | **Create** | import/edit 集成测试 |
| `tests/contract/test_candidate_endpoints.py` | **Create** | 新端点 contract 测试 |

---

## Task 1: candidate_service.py 纯函数(TDD)

**Files:**
- Create: `tests/unit/test_candidate_import.py`
- Create: `src/apps/admin/candidate_service.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/test_candidate_import.py`：

```python
"""Unit tests for candidate parse/validate/field-spec pure functions."""


# ── field specs ─────────────────────────────────────────────────────────────

def test_field_specs_character():
    from src.apps.admin.candidate_service import candidate_field_specs

    specs = candidate_field_specs("character")
    by_name = {s["name"]: s["required"] for s in specs}
    assert "id" not in by_name
    assert "vote_year" not in by_name
    assert by_name["name"] is True
    assert by_name["name_jp"] is False
    assert by_name["origin"] is False
    assert by_name["type"] is False
    assert by_name["first_appearance"] is False


def test_field_specs_music():
    from src.apps.admin.candidate_service import candidate_field_specs

    by_name = {s["name"]: s["required"] for s in candidate_field_specs("music")}
    assert by_name["name"] is True
    assert by_name["album"] is False
    assert "origin" not in by_name


# ── parse_content ───────────────────────────────────────────────────────────

def test_parse_json_array():
    from src.apps.admin.candidate_service import parse_content

    rows, errs = parse_content("auto", '[{"name":"A"},{"name":"B"}]')
    assert errs == []
    assert rows == [{"name": "A"}, {"name": "B"}]


def test_parse_json_not_array():
    from src.apps.admin.candidate_service import parse_content

    rows, errs = parse_content("auto", '{"name":"A"}')
    assert rows == []
    assert errs and "数组" in errs[0]["reason"]


def test_parse_csv_with_header():
    from src.apps.admin.candidate_service import parse_content

    csv_text = "name,name_jp,type\n博丽灵梦,博麗霊夢,human\n雾雨魔理沙,霧雨魔理沙,human\n"
    rows, errs = parse_content("auto", csv_text)
    assert errs == []
    assert rows[0]["name"] == "博丽灵梦"
    assert rows[0]["name_jp"] == "博麗霊夢"
    assert rows[1]["name"] == "雾雨魔理沙"


def test_parse_csv_quoted_comma():
    from src.apps.admin.candidate_service import parse_content

    csv_text = 'name,origin\n灵梦,"东方,红魔乡"\n'
    rows, errs = parse_content("auto", csv_text)
    assert errs == []
    assert rows[0]["origin"] == "东方,红魔乡"


def test_parse_empty():
    from src.apps.admin.candidate_service import parse_content

    rows, errs = parse_content("auto", "   ")
    assert rows == []
    assert errs


def test_parse_explicit_csv_format():
    from src.apps.admin.candidate_service import parse_content

    # content starts with [ but format forced to csv → treated as CSV header
    rows, errs = parse_content("csv", "name\nA\n")
    assert errs == []
    assert rows[0]["name"] == "A"


# ── validate_items ──────────────────────────────────────────────────────────

def test_validate_drops_empty_and_unknown():
    from src.apps.admin.candidate_service import validate_items

    rows = [{"name": "灵梦", "name_jp": "", "album": "x", "type": "human"}]
    valid, rejected = validate_items("character", rows)
    assert rejected == []
    assert valid == [{"name": "灵梦", "type": "human"}]  # empty name_jp dropped, unknown album dropped


def test_validate_missing_name_rejected():
    from src.apps.admin.candidate_service import validate_items

    rows = [{"name": "灵梦"}, {"type": "human"}, {"name": "  "}]
    valid, rejected = validate_items("character", rows)
    assert len(valid) == 1
    assert valid[0]["name"] == "灵梦"
    assert len(rejected) == 2
    assert rejected[0]["line"] == 2
    assert rejected[1]["line"] == 3
    assert all("name" in r["reason"] for r in rejected)


def test_validate_music_keeps_album():
    from src.apps.admin.candidate_service import validate_items

    rows = [{"name": "曲", "album": "Scarlet", "origin": "x"}]
    valid, rejected = validate_items("music", rows)
    assert valid == [{"name": "曲", "album": "Scarlet"}]  # origin unknown for music → dropped
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/unit/test_candidate_import.py -x`
Expected: `ModuleNotFoundError: No module named 'src.apps.admin.candidate_service'`

- [ ] **Step 3: 创建 candidate_service.py**

创建 `src/apps/admin/candidate_service.py`：

```python
"""Candidate import: pure parse/validate/field-spec helpers (no DB)."""
from __future__ import annotations

import csv
import io
import json
from typing import Any

from src.db_model.candidate import CandidateCharacter, CandidateMusic


def _model_for(category: str):
    return CandidateCharacter if category == "character" else CandidateMusic


def candidate_field_specs(category: str) -> list[dict]:
    """Derive editable fields + required flag from model columns.

    Excludes ``id`` (autoincrement PK) and ``vote_year`` (chosen in UI).
    A column is required when it is NOT NULL and has no server_default.
    """
    model = _model_for(category)
    specs = []
    for c in model.__table__.columns:
        if c.key in ("id", "vote_year"):
            continue
        required = (not c.nullable) and (c.server_default is None)
        specs.append({"name": c.key, "required": required})
    return specs


def parse_content(fmt: str, content: str) -> tuple[list[dict], list[dict]]:
    """Parse raw CSV/JSON text into a list of raw row dicts.

    Returns (rows, parse_errors). parse_errors is non-empty only on a
    document-level failure (bad JSON, no CSV header, empty input).
    """
    text = (content or "").strip()
    if not text:
        return [], [{"line": 0, "reason": "内容为空"}]

    detected = fmt
    if fmt == "auto":
        detected = "json" if text[:1] in ("[", "{") else "csv"

    if detected == "json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            return [], [{"line": 0, "reason": f"JSON 解析失败: {e}"}]
        if not isinstance(data, list):
            return [], [{"line": 0, "reason": "JSON 必须是对象数组"}]
        rows: list[dict] = []
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                return [], [{"line": i, "reason": "数组元素必须是对象"}]
            rows.append(item)
        return rows, []

    # CSV
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return [], [{"line": 0, "reason": "CSV 无表头"}]
    return [dict(r) for r in reader], []


def validate_items(category: str, rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Validate + clean rows. insertSelective: drop empty values and unknown columns.

    Returns (valid, rejected). A row is rejected only when ``name`` is
    missing or blank. ``line`` in rejected is the 1-based row position.
    """
    model = _model_for(category)
    valid_cols = {
        c.key for c in model.__table__.columns if c.key not in ("id", "vote_year")
    }
    valid: list[dict] = []
    rejected: list[dict] = []
    for idx, raw in enumerate(rows):
        cleaned: dict[str, Any] = {}
        for k, v in raw.items():
            if k not in valid_cols or v is None:
                continue
            sv = str(v).strip()
            if sv == "":
                continue
            cleaned[k] = sv
        if not cleaned.get("name"):
            rejected.append({"line": idx + 1, "reason": "缺少 name"})
            continue
        valid.append(cleaned)
    return valid, rejected
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/unit/test_candidate_import.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/apps/admin/candidate_service.py tests/unit/test_candidate_import.py
git commit -m "feat(candidate): parse/validate/field-spec pure helpers with tests (B-036)"
```

---

## Task 2: schemas

**Files:**
- Modify: `src/apps/admin/schemas.py`

- [ ] **Step 1: 在 schemas.py 末尾追加候选项管理模型**

```python
# ── Candidate management schemas ───────────────────────────────────────────────

class CandidateFieldSpec(BaseModel):
    name: str
    required: bool


class CandidateFieldsResponse(BaseModel):
    category: str
    fields: list[CandidateFieldSpec]


class CandidateImportRequest(BaseModel):
    vote_year: int
    category: Literal["character", "music"]
    format: Literal["auto", "csv", "json"] = "auto"
    content: str
    dry_run: bool = True


class CandidateRejected(BaseModel):
    line: int
    reason: str


class CandidateImportResponse(BaseModel):
    ok: bool = True
    valid_count: int
    imported: int = 0
    valid: list[dict] = []
    rejected: list[CandidateRejected] = []


class CandidateUpdateRequest(BaseModel):
    category: Literal["character", "music"]
    fields: dict
```

- [ ] **Step 2: 验证导入无误**

Run: `python -c "from src.apps.admin.schemas import CandidateImportRequest, CandidateFieldsResponse, CandidateUpdateRequest; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/apps/admin/schemas.py
git commit -m "feat(candidate): request/response schemas for fields/import/edit (B-036)"
```

---

## Task 3: ComputeDAO.update_candidate(TDD)

**Files:**
- Modify: `src/apps/result/compute_dao.py`
- Create: `tests/integration/test_candidate_admin.py`

- [ ] **Step 1: 写失败集成测试**

创建 `tests/integration/test_candidate_admin.py`：

```python
"""Integration tests for candidate admin: DAO update + endpoints."""
import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_update_candidate_ok(db_session):
    from src.apps.result.compute_dao import ComputeDAO

    await db_session.execute(text(
        "INSERT INTO candidate_character (vote_year, name, name_jp, origin, type) "
        "VALUES (2026, '灵梦', '霊夢', '红魔乡', 'human')"
    ))
    await db_session.commit()
    row_id = (await db_session.execute(
        text("SELECT id FROM candidate_character WHERE name='灵梦'")
    )).scalar_one()

    dao = ComputeDAO(db_session)
    result = await dao.update_candidate(row_id, "character", {"name_jp": "博麗霊夢", "type": "shrine"})
    assert result == "ok"

    name_jp = (await db_session.execute(
        text("SELECT name_jp FROM candidate_character WHERE id=:i"), {"i": row_id}
    )).scalar_one()
    assert name_jp == "博麗霊夢"


@pytest.mark.asyncio
async def test_update_candidate_not_found(db_session):
    from src.apps.result.compute_dao import ComputeDAO

    dao = ComputeDAO(db_session)
    assert await dao.update_candidate(999999, "character", {"name": "x"}) == "not_found"


@pytest.mark.asyncio
async def test_update_candidate_name_conflict(db_session):
    from src.apps.result.compute_dao import ComputeDAO

    await db_session.execute(text(
        "INSERT INTO candidate_character (vote_year, name) VALUES (2026, '灵梦')"
    ))
    await db_session.execute(text(
        "INSERT INTO candidate_character (vote_year, name) VALUES (2026, '魔理沙')"
    ))
    await db_session.commit()
    rid = (await db_session.execute(
        text("SELECT id FROM candidate_character WHERE name='魔理沙'")
    )).scalar_one()

    dao = ComputeDAO(db_session)
    # rename 魔理沙 → 灵梦 collides with existing row in same year
    assert await dao.update_candidate(rid, "character", {"name": "灵梦"}) == "conflict"
```

**Fixture note:** Read `tests/integration/conftest.py` first to confirm the `db_session` fixture name. The DAO tests above need only `db_session` (a real async session bound to the in-memory sqlite engine). The endpoint tests added in Task 5 will additionally need `app` and `admin_secret` fixtures — `tests/integration/test_admin_routes_ext.py` already defines those two inline (an `app` fixture wiring fakeredis + sqlite overrides, and an `admin_secret` fixture setting `ADMIN_SECRET` env + resetting the cached settings). If the integration `conftest.py` does not provide `app`/`admin_secret`, copy those two inline fixtures from `tests/integration/test_admin_routes_ext.py` into `tests/integration/test_candidate_admin.py`.

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/integration/test_candidate_admin.py -x`
Expected: FAIL — `AttributeError: 'ComputeDAO' object has no attribute 'update_candidate'`

- [ ] **Step 3: 在 compute_dao.py 的 ComputeDAO 类末尾追加 update_candidate**

```python
    async def update_candidate(
        self, candidate_id: int, category: str, fields: dict
    ) -> str:
        """Update one candidate row. Returns 'ok' / 'not_found' / 'conflict'.

        insertSelective: only columns present in ``fields`` (and belonging to
        the model) are written. Renaming to a name that already exists in the
        same vote_year returns 'conflict'.
        """
        from src.db_model.candidate import CandidateCharacter, CandidateMusic

        model = CandidateCharacter if category == "character" else CandidateMusic
        valid_cols = {
            c.key for c in model.__table__.columns if c.key not in ("id", "vote_year")
        }
        row = (await self.session.execute(
            select(model).where(model.id == candidate_id)
        )).scalar_one_or_none()
        if row is None:
            return "not_found"

        new_name = fields.get("name")
        if new_name and new_name != row.name:
            dup = (await self.session.execute(
                select(model).where(
                    model.vote_year == row.vote_year,
                    model.name == new_name,
                    model.id != candidate_id,
                )
            )).scalar_one_or_none()
            if dup is not None:
                return "conflict"

        for k, v in fields.items():
            if k in valid_cols:
                setattr(row, k, v)
        await self.session.commit()
        return "ok"
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/integration/test_candidate_admin.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/apps/result/compute_dao.py tests/integration/test_candidate_admin.py
git commit -m "feat(candidate): ComputeDAO.update_candidate with conflict check + tests (B-036)"
```

---

## Task 4: AdminService 方法

**Files:**
- Modify: `src/apps/admin/service.py`

- [ ] **Step 1: 在 AdminService 类末尾追加 3 个方法**

打开 `src/apps/admin/service.py`,在 `AdminService` 类内(注意是 AdminService,不是 SyncService)追加：

```python
    def get_candidate_fields(self, category: str) -> list[dict]:
        from src.apps.admin.candidate_service import candidate_field_specs
        return candidate_field_specs(category)

    async def import_candidates_from_content(
        self,
        vote_year: int,
        category: str,
        fmt: str,
        content: str,
        dry_run: bool,
    ) -> dict:
        from src.apps.admin.candidate_service import parse_content, validate_items

        rows, parse_errors = parse_content(fmt, content)
        if parse_errors:
            return {"parse_error": parse_errors[0]["reason"]}
        valid, rejected = validate_items(category, rows)
        imported = 0
        if not dry_run and valid:
            imported = await self.compute_dao.upsert_candidates(
                vote_year, category, valid
            )
        return {
            "valid": valid,
            "valid_count": len(valid),
            "rejected": rejected,
            "imported": imported,
        }

    async def update_candidate(
        self, candidate_id: int, category: str, fields: dict
    ) -> str:
        return await self.compute_dao.update_candidate(candidate_id, category, fields)
```

- [ ] **Step 2: 验证导入无误**

Run: `python -c "from src.apps.admin.service import AdminService; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/apps/admin/service.py
git commit -m "feat(candidate): AdminService fields/import/update methods (B-036)"
```

---

## Task 5: 三个端点 + 集成测试

**Files:**
- Modify: `src/apps/admin/router.py`
- Modify: `tests/integration/test_candidate_admin.py`

- [ ] **Step 1: 在 router.py 追加端点**

先把新 schema 加入 router.py 顶部的 schemas import 块(找到 `from src.apps.admin.schemas import (` 那段,加入下列名字)：

```python
    CandidateFieldsResponse,
    CandidateImportRequest,
    CandidateImportResponse,
    CandidateUpdateRequest,
```

然后在 `delete_candidate` 端点之后(或文件中候选项相关端点附近)追加：

```python
@router.get("/candidates/fields", response_model=CandidateFieldsResponse)
async def candidate_fields(
    category: str = "character",
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> CandidateFieldsResponse:
    _check_admin_secret(settings, x_admin_secret)
    return CandidateFieldsResponse(
        category=category, fields=service.get_candidate_fields(category)
    )


@router.post("/candidates/import", response_model=CandidateImportResponse)
async def import_candidates_content(
    body: CandidateImportRequest,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> CandidateImportResponse:
    _check_admin_secret(settings, x_admin_secret)
    result = await service.import_candidates_from_content(
        body.vote_year, body.category, body.format, body.content, body.dry_run
    )
    if "parse_error" in result:
        raise HTTPException(status_code=400, detail=result["parse_error"])
    return CandidateImportResponse(**result)


@router.put("/candidates/{candidate_id}")
async def update_candidate(
    candidate_id: int,
    body: CandidateUpdateRequest,
    x_admin_secret: Optional[str] = Header(None),
    service: AdminService = Depends(get_admin_service),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_admin_secret(settings, x_admin_secret)
    result = await service.update_candidate(candidate_id, body.category, body.fields)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="CANDIDATE_NOT_FOUND")
    if result == "conflict":
        raise HTTPException(status_code=409, detail="CANDIDATE_NAME_CONFLICT")
    return {"ok": True}
```

**重要:** `GET /candidates/fields` 必须在 `GET /candidates` 之后、但路由不能被 `/candidates/{candidate_id}` 之类的路径参数吞掉。FastAPI 按声明顺序匹配,`/candidates/fields` 是静态路径,需声明在任何 `/candidates/{...}` 动态路径之前。检查文件中 `DELETE /candidates/{candidate_id}` 的位置,把 `GET /candidates/fields` 声明在它前面(或确保静态路径优先)。

- [ ] **Step 2: 在集成测试文件追加端点测试**

在 `tests/integration/test_candidate_admin.py` 末尾追加：

```python
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_fields_endpoint(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/admin/candidates/fields?category=character",
                            headers={"X-Admin-Secret": admin_secret})
    assert resp.status_code == 200
    data = resp.json()
    names = {f["name"]: f["required"] for f in data["fields"]}
    assert names["name"] is True
    assert names["name_jp"] is False


@pytest.mark.asyncio
async def test_import_dry_run_then_commit(app, admin_secret):
    payload = {
        "vote_year": 2030, "category": "character", "format": "auto",
        "content": '[{"name":"灵梦","name_jp":"霊夢"},{"type":"human"}]',
        "dry_run": True,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # dry run: nothing written
        r1 = await ac.post("/api/v1/admin/candidates/import", json=payload,
                           headers={"X-Admin-Secret": admin_secret})
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["valid_count"] == 1
        assert d1["imported"] == 0
        assert len(d1["rejected"]) == 1

        # commit
        payload["dry_run"] = False
        r2 = await ac.post("/api/v1/admin/candidates/import", json=payload,
                           headers={"X-Admin-Secret": admin_secret})
        assert r2.status_code == 200
        assert r2.json()["imported"] == 1

        # list shows it
        r3 = await ac.get("/api/v1/admin/candidates?category=character&vote_year=2030",
                          headers={"X-Admin-Secret": admin_secret})
        assert r3.json()["total"] == 1


@pytest.mark.asyncio
async def test_import_parse_error(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/admin/candidates/import", json={
            "vote_year": 2030, "category": "character",
            "format": "json", "content": '{"not":"array"}', "dry_run": True,
        }, headers={"X-Admin-Secret": admin_secret})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_edit_endpoint_conflict(app, db_session, admin_secret):
    await db_session.execute(text(
        "INSERT INTO candidate_character (vote_year, name) VALUES (2031, 'A')"
    ))
    await db_session.execute(text(
        "INSERT INTO candidate_character (vote_year, name) VALUES (2031, 'B')"
    ))
    await db_session.commit()
    rid = (await db_session.execute(
        text("SELECT id FROM candidate_character WHERE name='B' AND vote_year=2031")
    )).scalar_one()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.put(f"/api/v1/admin/candidates/{rid}",
                            json={"category": "character", "fields": {"name": "A"}},
                            headers={"X-Admin-Secret": admin_secret})
    assert resp.status_code == 409
```

**Fixture note:** these endpoint tests use `app` + `admin_secret`. If not provided by `tests/integration/conftest.py`, copy the inline `app`/`admin_secret` fixtures from `tests/integration/test_admin_routes_ext.py` into this file (see the fixture note in Task 3). The admin routes are mounted under `/api/v1/admin/*`. Also add `from httpx import AsyncClient, ASGITransport` at the top of the file if not already imported (the snippet below repeats the import for clarity — dedupe if needed).

- [ ] **Step 3: 运行集成测试**

Run: `pytest tests/integration/test_candidate_admin.py -v`
Expected: 全部 PASS(3 DAO + 4 endpoint = 7)

- [ ] **Step 4: 跑全套确认无回归**

Run: `pytest tests/ -q --tb=short`
Expected: 仅既有的 test_pnvs_client 本地失败(若有),其余通过

- [ ] **Step 5: Commit**

```bash
git add src/apps/admin/router.py tests/integration/test_candidate_admin.py
git commit -m "feat(candidate): fields/import/edit endpoints + integration tests (B-036)"
```

---

## Task 6: Contract 测试

**Files:**
- Create: `tests/contract/test_candidate_endpoints.py`

- [ ] **Step 1: 写 contract 测试**

创建 `tests/contract/test_candidate_endpoints.py`：

```python
"""Contract tests for candidate management endpoints."""
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_fields_403_without_secret(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/admin/candidates/fields?category=character")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_fields_shape(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/admin/candidates/fields?category=music",
                            headers={"X-Admin-Secret": admin_secret})
    assert resp.status_code == 200
    data = resp.json()
    assert data["category"] == "music"
    assert any(f["name"] == "album" for f in data["fields"])


@pytest.mark.asyncio
async def test_import_shape(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/admin/candidates/import", json={
            "vote_year": 2040, "category": "character", "format": "auto",
            "content": "name\n测试角色\n", "dry_run": True,
        }, headers={"X-Admin-Secret": admin_secret})
    assert resp.status_code == 200
    data = resp.json()
    assert {"valid_count", "imported", "valid", "rejected"} <= data.keys()


@pytest.mark.asyncio
async def test_edit_404(app, admin_secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.put("/api/v1/admin/candidates/99999",
                            json={"category": "character", "fields": {"name_jp": "x"}},
                            headers={"X-Admin-Secret": admin_secret})
    assert resp.status_code == 404
```

- [ ] **Step 2: 运行**

Run: `pytest tests/contract/test_candidate_endpoints.py -v`
Expected: 4 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/contract/test_candidate_endpoints.py
git commit -m "test(candidate): contract tests for candidate endpoints (B-036)"
```

---

## Task 7: 前端主题改白色

**Files:**
- Modify: `src/admin_ui/index.html`(仅 `<style>` 块)

- [ ] **Step 1: 替换 `<style>` 块的配色**

打开 `src/admin_ui/index.html`,把 `<style>...</style>` 内的深色配色整体替换为白色主题。保持选择器结构不变,只改颜色值。用下列对照替换:

```css
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #f0f2f5; color: #1a1a1a; min-height: 100vh; }
  #login-overlay { position: fixed; inset: 0; background: #f0f2f5; display: flex; align-items: center; justify-content: center; z-index: 100; }
  #login-box { background: #fff; padding: 2rem; border-radius: 8px; width: 320px; border: 1px solid #e2e2e2; box-shadow: 0 4px 20px rgba(0,0,0,.08); }
  #login-box h2 { margin-bottom: 1rem; color: #111; }
  #login-box input { width: 100%; padding: .6rem; background: #fff; border: 1px solid #ccc; color: #1a1a1a; border-radius: 4px; margin-bottom: .8rem; }
  #login-error { color: #dc2626; font-size: .85rem; margin-bottom: .5rem; min-height: 1.2em; }
  nav { background: #fff; padding: .8rem 1.5rem; display: flex; gap: .5rem; align-items: center; border-bottom: 1px solid #e2e2e2; }
  nav .brand { color: #555; margin-right: auto; font-weight: bold; }
  nav button { background: none; border: none; color: #555; cursor: pointer; padding: .4rem .8rem; border-radius: 4px; }
  nav button.active, nav button:hover { background: #eef2ff; color: #2563eb; }
  #content { padding: 1.5rem; }
  .card { background: #fff; border: 1px solid #e2e2e2; border-radius: 8px; padding: 1.2rem; margin-bottom: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
  .stats-row { display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }
  .stat-card { background: #f7f9fc; border: 1px solid #e2e2e2; border-radius: 6px; padding: 1rem 1.5rem; min-width: 140px; }
  .stat-card .val { font-size: 1.8rem; font-weight: bold; color: #2563eb; }
  .stat-card .lbl { font-size: .8rem; color: #888; margin-top: .2rem; }
  input[type=text], input[type=number], input[type=password], select, textarea {
    background: #fff; border: 1px solid #ccc; color: #1a1a1a;
    padding: .5rem .7rem; border-radius: 4px; font-family: inherit; }
  button.btn { background: #2563eb; border: none; color: #fff; padding: .5rem 1rem; border-radius: 4px; cursor: pointer; }
  button.btn:hover { background: #1d4ed8; }
  button.btn.danger { background: #dc2626; }
  button.btn.danger:hover { background: #b91c1c; }
  button.btn.green { background: #16a34a; }
  button.btn.green:hover { background: #15803d; }
  button.btn.ghost { background: #fff; color: #374151; border: 1px solid #ccc; }
  button.btn.sm { padding: .3rem .6rem; font-size: .85rem; }
  table { width: 100%; border-collapse: collapse; font-size: .9rem; }
  th, td { text-align: left; padding: .5rem .7rem; border-bottom: 1px solid #eee; }
  th { color: #888; font-weight: 500; }
  .search-row { display: flex; gap: .5rem; margin-bottom: 1rem; flex-wrap: wrap; align-items: center; }
  .badge { display: inline-block; padding: .15rem .5rem; border-radius: 3px; font-size: .8rem; }
  .badge.open { background: #dcfce7; color: #16a34a; }
  .badge.closed { background: #fee2e2; color: #dc2626; }
  .badge.upcoming { background: #fef9c3; color: #a16207; }
  progress { width: 100%; height: 8px; }
  .progress-wrap { margin: .5rem 0; }
  .toast { position: fixed; bottom: 1.5rem; right: 1.5rem; background: #1a1a1a; color: #fff;
           padding: .8rem 1.2rem; border-radius: 6px; z-index: 200; opacity: 0;
           transition: opacity .3s; pointer-events: none; }
  .toast.show { opacity: 1; }
  .loading { color: #888; padding: 1rem; }
  /* modal */
  .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.35); display: flex;
                   align-items: flex-start; justify-content: center; padding-top: 6vh; z-index: 150; }
  .modal { width: 460px; max-width: 92vw; background: #fff; border-radius: 10px;
           box-shadow: 0 12px 40px rgba(0,0,0,.2); overflow: hidden; }
  .modal-head { padding: .8rem 1.1rem; border-bottom: 1px solid #eee; font-weight: 600; }
  .modal-body { padding: 1.1rem; max-height: 60vh; overflow-y: auto; }
  .modal-foot { display: flex; gap: .5rem; padding: .8rem 1.1rem; border-top: 1px solid #eee; background: #fafafa; }
  .field { margin-bottom: .7rem; }
  .field label { display: block; font-size: .8rem; color: #555; margin-bottom: .25rem; }
  .field label .req { color: #dc2626; }
  .field input, .field textarea { width: 100%; }
  .seg { display: inline-flex; border: 1px solid #ccc; border-radius: 5px; overflow: hidden; font-size: .8rem; }
  .seg span { padding: .35rem .7rem; cursor: pointer; }
  .seg span.on { background: #2563eb; color: #fff; }
  .preview { border: 1px solid #eee; border-radius: 6px; margin-top: .6rem; }
  .preview-head { padding: .4rem .6rem; background: #f7f7f7; font-size: .8rem; border-bottom: 1px solid #eee; }
  .ok { color: #16a34a; }
  .err { color: #dc2626; }
```

- [ ] **Step 2: 本地启动目检**

Run: `uvicorn src.main:app --port 8000`(另开终端),浏览器访问 `http://localhost:8000/admin-ui/`
Expected: 登录页与各 Tab 显示为白色主题,无样式错乱。Ctrl-C 停止。

- [ ] **Step 3: Commit**

```bash
git add src/admin_ui/index.html
git commit -m "feat(admin-ui): switch admin panel to light theme + modal styles (B-036)"
```

---

## Task 8: 前端候选项 Tab 三界面

**Files:**
- Modify: `src/admin_ui/index.html`(JS 区候选项相关函数 + 全局 modal helper)

- [ ] **Step 1: 加通用 modal helper(在 `<script>` 区靠前,`api()`/`toast()` 之后)**

```javascript
function openModal(html) {
  closeModal();
  const ov = document.createElement('div');
  ov.className = 'modal-overlay';
  ov.id = 'modal-overlay';
  ov.innerHTML = '<div class="modal">' + html + '</div>';
  ov.addEventListener('click', e => { if (e.target === ov) closeModal(); });
  document.body.appendChild(ov);
}
function closeModal() {
  const ov = document.getElementById('modal-overlay');
  if (ov) ov.remove();
}
```

- [ ] **Step 2: 替换 `candidates()` 列表页(加导入按钮 + 行内编辑)**

把现有 `candidates()` 与 `searchCandidates()` 替换为：

```javascript
async function candidates() {
  document.getElementById('content').innerHTML = `
    <div class="card">
      <div class="search-row">
        <select id="c-cat"><option value="character">角色</option><option value="music">音乐</option></select>
        <input type="number" id="c-year" value="${new Date().getFullYear()}" style="width:80px" />
        <input type="text" id="c-q" placeholder="名称搜索" style="width:180px" />
        <button class="btn" onclick="searchCandidates(1)">搜索</button>
        <button class="btn green" style="margin-left:auto" onclick="openImportModal()">+ 导入</button>
      </div>
      <div id="candidates-table"></div>
    </div>`;
}

async function searchCandidates(page) {
  const cat = document.getElementById('c-cat').value;
  const year = document.getElementById('c-year').value;
  const q = document.getElementById('c-q').value;
  let url = '/admin/candidates?category=' + cat + '&vote_year=' + year + '&page=' + page + '&page_size=50';
  if (q) url += '&q=' + encodeURIComponent(q);
  const r = await api(url);
  const d = await r.json();
  window._candCache = {};
  const rows = d.items.map(i => {
    window._candCache[i.id] = i;
    return `<tr>
      <td>${i.name}</td><td>${i.name_jp||''}</td><td>${i.type||''}</td>
      <td>${i.origin||i.album||''}</td><td>${i.first_appearance||''}</td>
      <td><span class="link" style="color:#2563eb;cursor:pointer" onclick="openEditModal(${i.id})">编辑</span>
      &nbsp;<span class="link" style="color:#dc2626;cursor:pointer" onclick="deleteCandidate(${i.id},'${cat}')">删除</span></td>
    </tr>`;
  }).join('');
  document.getElementById('candidates-table').innerHTML = `
    <table><thead><tr><th>名称</th><th>日文名</th><th>类型</th><th>来源/专辑</th><th>首登</th><th>操作</th></tr></thead>
    <tbody>${rows || '<tr><td colspan="6" style="color:#888;text-align:center">无结果</td></tr>'}</tbody></table>
    <div style="margin-top:.8rem;color:#888">共 ${d.total} 条</div>`;
}
```

(保留现有 `deleteCandidate()` 不变。)

- [ ] **Step 3: 加导入弹窗逻辑**

```javascript
function openImportModal() {
  const cat = document.getElementById('c-cat').value;
  const year = document.getElementById('c-year').value;
  openModal(`
    <div class="modal-head">导入候选项</div>
    <div class="modal-body">
      <div style="display:flex;gap:.5rem;align-items:center;margin-bottom:.6rem">
        <select id="imp-cat"><option value="character"${cat==='character'?' selected':''}>角色</option><option value="music"${cat==='music'?' selected':''}>音乐</option></select>
        <input type="number" id="imp-year" value="${year}" style="width:80px" />
        <span class="seg" id="imp-fmt">
          <span class="on" data-f="auto" onclick="setFmt(this)">自动</span>
          <span data-f="csv" onclick="setFmt(this)">CSV</span>
          <span data-f="json" onclick="setFmt(this)">JSON</span>
        </span>
      </div>
      <div class="field"><textarea id="imp-text" rows="4" placeholder="粘贴 CSV / JSON 文本…"></textarea></div>
      <div style="display:flex;gap:.5rem">
        <input type="file" id="imp-file" accept=".csv,.json,.txt" style="display:none" onchange="loadImportFile(this)" />
        <button class="btn ghost" onclick="document.getElementById('imp-file').click()">选择文件</button>
        <button class="btn" onclick="previewImport()">解析预览</button>
      </div>
      <div id="imp-preview"></div>
    </div>
    <div class="modal-foot">
      <button class="btn" id="imp-confirm" style="display:none" onclick="commitImport()">确认导入</button>
      <button class="btn ghost" onclick="closeModal()">取消</button>
    </div>`);
}

let _impFmt = 'auto';
function setFmt(el) {
  _impFmt = el.dataset.f;
  el.parentElement.querySelectorAll('span').forEach(s => s.classList.remove('on'));
  el.classList.add('on');
}

function loadImportFile(input) {
  const f = input.files[0];
  if (!f) return;
  const reader = new FileReader();
  reader.onload = () => { document.getElementById('imp-text').value = reader.result; };
  reader.readAsText(f);
}

async function _importCall(dryRun) {
  return api('/admin/candidates/import', {
    method: 'POST',
    body: JSON.stringify({
      vote_year: parseInt(document.getElementById('imp-year').value),
      category: document.getElementById('imp-cat').value,
      format: _impFmt,
      content: document.getElementById('imp-text').value,
      dry_run: dryRun,
    }),
  });
}

async function previewImport() {
  const r = await _importCall(true);
  if (r.status === 400) {
    const e = await r.json();
    document.getElementById('imp-preview').innerHTML =
      `<div class="preview"><div class="preview-head err">解析失败: ${e.detail}</div></div>`;
    document.getElementById('imp-confirm').style.display = 'none';
    return;
  }
  const d = await r.json();
  const sample = d.valid.slice(0, 5).map(i =>
    `<tr><td>${i.name||''}</td><td>${i.name_jp||''}</td><td>${i.type||''}</td><td>${i.origin||i.album||''}</td></tr>`
  ).join('');
  const errLines = d.rejected.map(e => `第${e.line}行: ${e.reason}`).join('；');
  document.getElementById('imp-preview').innerHTML = `
    <div class="preview">
      <div class="preview-head">
        <span class="ok">✓ 有效 ${d.valid_count}</span>
        ${d.rejected.length ? ` &nbsp; <span class="err">✗ 错误 ${d.rejected.length}（${errLines}）</span>` : ''}
      </div>
      <table>${sample}</table>
    </div>`;
  const btn = document.getElementById('imp-confirm');
  btn.textContent = '确认导入 ' + d.valid_count + ' 条';
  btn.style.display = d.valid_count > 0 ? '' : 'none';
}

async function commitImport() {
  const r = await _importCall(false);
  if (r.status === 400) { const e = await r.json(); toast('解析失败: ' + e.detail); return; }
  const d = await r.json();
  toast('成功导入 ' + d.imported + ' 条');
  closeModal();
  searchCandidates(1);
}
```

- [ ] **Step 4: 加编辑弹窗逻辑(schema 驱动)**

```javascript
async function openEditModal(id) {
  const cat = document.getElementById('c-cat').value;
  const row = (window._candCache || {})[id] || {};
  const fr = await api('/admin/candidates/fields?category=' + cat);
  const spec = (await fr.json()).fields;
  const fieldsHtml = spec.map(f => `
    <div class="field">
      <label>${f.name}${f.required ? ' <span class="req">*</span>' : ''}</label>
      <input id="ed-${f.name}" value="${row[f.name] != null ? String(row[f.name]).replace(/"/g,'&quot;') : ''}" />
    </div>`).join('');
  openModal(`
    <div class="modal-head">编辑：${row.name || ''}</div>
    <div class="modal-body">${fieldsHtml}</div>
    <div class="modal-foot">
      <button class="btn" onclick="saveEdit(${id},'${cat}')">保存</button>
      <button class="btn danger" onclick="deleteFromEdit(${id},'${cat}')">删除</button>
      <button class="btn ghost" onclick="closeModal()">取消</button>
    </div>`);
  window._editSpec = spec.map(f => f.name);
}

async function saveEdit(id, cat) {
  const fields = {};
  (window._editSpec || []).forEach(n => {
    fields[n] = document.getElementById('ed-' + n).value;
  });
  const r = await api('/admin/candidates/' + id, {
    method: 'PUT',
    body: JSON.stringify({ category: cat, fields }),
  });
  if (r.status === 409) { toast('该名称在本年份已存在'); return; }
  if (r.status === 404) { toast('候选项不存在'); return; }
  toast('已保存');
  closeModal();
  searchCandidates(1);
}

async function deleteFromEdit(id, cat) {
  if (!confirm('确认删除此候选项？')) return;
  await api('/admin/candidates/' + id + '?category=' + cat, { method: 'DELETE' });
  toast('已删除');
  closeModal();
  searchCandidates(1);
}
```

- [ ] **Step 5: 目检三界面**

Run: `uvicorn src.main:app --port 8000`,浏览器 `http://localhost:8000/admin-ui/` → 候选项 Tab
手工验收清单:
- [ ] 列表页有「+ 导入」按钮、每行有编辑/删除
- [ ] 导入弹窗:粘贴 JSON `[{"name":"测试"}]` → 解析预览显示「✓ 有效 1」→ 确认导入 → toast + 列表刷新
- [ ] 上传 CSV 文件 → 文本框填入内容 → 预览正常
- [ ] 编辑弹窗:点编辑 → 字段按 schema 渲染、必填带 `*`、填入当前值 → 改 name_jp 保存 → 列表更新
- [ ] 编辑时把 name 改成已存在的名 → toast「该名称在本年份已存在」
- [ ] 弹窗点遮罩空白处关闭

- [ ] **Step 6: Commit**

```bash
git add src/admin_ui/index.html
git commit -m "feat(admin-ui): candidate import/edit modals + list page completion (B-036)"
```

---

## Task 9: BACKLOG 更新

**Files:**
- Modify: `docs/BACKLOG.md`

- [ ] **Step 1: 标记 B-036 完成**

把 `docs/BACKLOG.md` 中 B-036 行改为(commit hash 用 Task 8 的实际 hash)：

```
| **B-036** | ~~候选项管理增强：CSV/JSON 导入(dry-run 预览) + 单条编辑 + 列表/详情完善 + 管理端改白色主题~~ | ✅ 已完成 (2026-06-08) | — | 3 端点 + 后端解析校验 + 白色主题 + 导入/编辑弹窗 |
```

- [ ] **Step 2: Commit**

```bash
git add docs/BACKLOG.md
git commit -m "docs: mark B-036 (candidate management) completed in BACKLOG"
```
