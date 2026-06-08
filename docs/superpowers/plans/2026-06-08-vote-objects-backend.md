# Block 3B 投票对象迁后端 — 后端(含管理端)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: subagent-driven-development / executing-plans. Steps use `- [ ]`.

**Goal:** 角色/音乐投票对象迁后端管理:导入时自动去重合并 + admin 可手调 + 分类查询/详情端点。

**Architecture:** candidate_character/music 加 `merged_into` 规范化字段;`detect_merges` 纯逻辑做自动合并;`/vote-objects/characters|music|{id}` 同族端点;计票过滤/归并合并映射。

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic

**Design Spec:** `docs/superpowers/specs/2026-06-08-vote-objects-backend-design.md`

---

## Task 1: merged_into 字段 + migration 0010

**Files:** Modify `src/db_model/candidate.py`;Create migration

- [ ] **Step 1:** 给 `CandidateCharacter`、`CandidateMusic` 各加 `merged_into = Column(Integer, nullable=True, index=True)`。
- [ ] **Step 2:** 手写 `alembic/versions/0010_candidate_merge.py`(`down_revision` 串到最新),`add_column` 两表 merged_into + index。
- [ ] **Step 3:** 验证 import;flake8 + commit `feat(vote-objects): merged_into on candidate tables + migration 0010 (B-040)`

---

## Task 2: detect_merges 纯逻辑(TDD)

**Files:** Create `src/apps/admin/candidate_merge.py`;test

- [ ] **Step 1:** 写失败测试 `tests/unit/test_candidate_merge.py`:
  - `detect_merges("character", rows)`:同 vote_year 同 name 的多行 → 返回 [(dup_id, canonical_id)],canonical 取最小 id(或最早)。
  - `detect_merges("music", rows)`:同 vote_year 同 name 不同 album → 合并到 canonical;同 name 同 album 也合并。
  - 无重复 → 返回 []。
- [ ] **Step 2:** 实现 `candidate_merge.py` 的 `detect_merges(category, rows)`(rows 为含 id/vote_year/name/album 的 dict 列表)。
- [ ] **Step 3:** 测试通过;flake8 + commit `feat(vote-objects): detect_merges pure logic + tests (B-040)`

---

## Task 3: 导入时自动合并 + admin 手调端点

**Files:** Modify `src/apps/admin/{service,router,schemas}.py`;test

- [ ] **Step 1:** 候选导入(`import_candidates_from_content` / upsert)后,对该 vote_year+category 跑 `detect_merges` → 批量设 `merged_into`。
- [ ] **Step 2:** 端点:
  - `POST /admin/candidates/{id}/merge-into/{target_id}` → 设 merged_into
  - `POST /admin/candidates/{id}/unmerge` → 清 merged_into
  - `GET /admin/candidates/merges?category=&vote_year=` → 合并关系列表
  (`X-Admin-Secret`;category 经 query 传以选表)
- [ ] **Step 3:** 集成测试:导入重名 → 自动合并;手动 merge/unmerge 改 merged_into。
- [ ] **Step 4:** flake8 + commit `feat(vote-objects): auto-merge on import + admin merge/unmerge (B-040)`

---

## Task 4: 计票过滤/归并 merged_into

**Files:** Modify `src/apps/result/compute_dao.py` / compute_service

- [ ] **Step 1:** `load_*_candidates` 只取 `merged_into IS NULL`(规范化主候选)。
- [ ] **Step 2:** 计票聚合时,把投给"被合并候选 name"的票归并到主候选(按 name→canonical 映射;若投票按 name 计,合并行的 name 与主候选不同则建映射表)。
- [ ] **Step 3:** 集成测试:构造合并关系 + 票 → 主候选票数含被合并票。
- [ ] **Step 4:** flake8 + commit `feat(vote-objects): compute respects merged_into (B-040)`

---

## Task 5: /vote-objects/characters|music|{id} 端点

**Files:** Create `src/apps/vote_objects/router.py`(新建公开路由域);register 进 `src/api/rest/v1/__init__.py`

- [ ] **Step 1:** 新建 vote_objects 路由,加:
  - `GET /vote-objects/characters?vote_year=` → 按首登作品(origin/first_appearance)分组,只含 `merged_into IS NULL`
  - `GET /vote-objects/music?vote_year=` → 按 album 分组,只含主候选
  - `GET /vote-objects/{category}/{id}` → 详情(character/music)
  返回形状 `{ vote_year, groups:[{group, items:[...]}] }`;分组组装抽成共用函数。
- [ ] **Step 2:** 集成 + contract 测试。
- [ ] **Step 3:** `pytest tests/ -q` + flake8 `src/`;commit `feat(vote-objects): characters/music/detail listing endpoints (B-040)`

---

## Task 6: 管理端合并视图 + 回归

**Files:** Modify `src/admin_ui/index.html`;`docs/BACKLOG.md`

- [ ] **Step 1:** 候选 Tab 加"合并关系"视图(显示被合并→主候选)+ 合并/拆分操作按钮。
- [ ] **Step 2:** `pytest tests/ -q --tb=short`;`flake8 src/`。
- [ ] **Step 3:** BACKLOG 标 B-040;commit + push。

---

## Self-Review 注意
- 合并的"主候选"选取规则要稳定(最小 id),避免重复导入时来回横跳。
- 计票归并是本块最易错处:务必加集成测试验证"被合并票计入主候选"。
- `/vote-objects/*` 两类(character/music)保持同一返回形状,前端才能复用一套封装。
