# Block 2 作品投票 — 后端(含管理端)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use `- [ ]`.

**Goal:** 实现后端完整作品(官方作品)投票链路,每一层镜像角色(character),并加"前端拉投票对象列表"的 `/vote-objects/works` 端点。

**Architecture:** 新增 `candidate_work`(候选)+ `work`(处理层)两表;候选管理 category 扩 `work`(schema 驱动,零新端点);submit/vote_data/result/graphql 逐层仿 character;新增按发布时间分组的作品列表端点。

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, 现有 ComputeService

**Design Spec:** `docs/superpowers/specs/2026-06-08-works-voting-backend-design.md`

**核心方法论:** 大多数层是"读 character 的实现 → 仿写 work"。每个任务先 Read 对应 character 文件,再镜像。category key 用 `"work"`,Redis 段用 `works`。

---

## Task 1: 数据模型 candidate_work + work

**Files:** Modify `src/db_model/candidate.py`; Create `src/db_model/work.py`; Modify `__init__.py`

- [ ] **Step 1:** `candidate.py` 加(仿 CandidateCharacter):
```python
class CandidateWork(Base):
    __tablename__ = "candidate_work"
    id = Column(Integer, primary_key=True, autoincrement=True)
    vote_year = Column(Integer, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    name_jp = Column(String(255), nullable=False, server_default="")
    category = Column(String(64), nullable=False, server_default="")
    release_date = Column(String(16), nullable=True)
    __table_args__ = (UniqueConstraint("vote_year", "name", name="uq_candidate_work_year_name"),)
```
- [ ] **Step 2:** Read `src/db_model/character.py`,创建 `src/db_model/work.py` 仿写(表名 `work`,列 `id` FK user、`submit_datetime`、`work_list` JSON)。
- [ ] **Step 3:** `__init__.py` 导出 `CandidateWork`, `Work` + 加 `__all__`。
- [ ] **Step 4:** 验证 `python -c "from src.db_model import CandidateWork, Work; print(CandidateWork.__tablename__, Work.__tablename__)"` → `candidate_work work`。
- [ ] **Step 5:** flake8 + commit `feat(works): CandidateWork + Work models (B-038)`

---

## Task 2: migration 0008

- [ ] **Step 1:** 手写 `alembic/versions/0008_work_voting.py`(`revision="0008"`, `down_revision="0007"`),create_table `candidate_work` + `work`,镜像模型列与约束。参照 0003(candidate)与 character 建表。
- [ ] **Step 2:** flake8 + commit `feat(works): migration 0008 work voting tables (B-038)`
> 本地无 PG 不跑;CI + sqlite 集成测试覆盖。

---

## Task 3: 候选管理扩 work(schema 驱动)

**Files:** Modify `src/apps/admin/candidate_service.py`,候选相关 DAO/service/router/schemas

- [ ] **Step 1:** `candidate_service.py` 的 `_model_for(category)` 加分支 `"work" -> CandidateWork`。
- [ ] **Step 2:** `ComputeDAO.list_candidates`/`delete_candidate`/`update_candidate` 的 `_model_for` 等价映射加 work(若它们各自硬编码了 character/music 二选一,改为三路)。
- [ ] **Step 3:** 把候选相关 `category: Literal["character","music"]` 全部扩为 `Literal["character","music","work"]`(schemas.py 的 `ImportCandidatesRequest`、`CandidateImportRequest`、`CandidateUpdateRequest`;router 的查询参数说明)。
- [ ] **Step 4:** 写集成测试 `tests/integration/test_work_candidate.py`:`GET /admin/candidates/fields?category=work` 返回含 `release_date`;import work CSV `name,release_date,category` dry_run + commit;list 返回。
- [ ] **Step 5:** `pytest tests/integration/test_work_candidate.py -v` 通过;flake8 `src/`;commit `feat(works): candidate management supports work category (B-038)`

---

## Task 4: submit 层 validate_work + submit_work

**Files:** Modify `src/apps/submit/{schemas,service,dao}.py`; test

- [ ] **Step 1:** Read `src/apps/submit/schemas.py` 的 CharacterSubmit/CharacterSubmitRest;加 `WorkSubmit`(id, reason, first)与 `WorkSubmitRest`(works[], meta)。
- [ ] **Step 2:** `service.py` 的 `SubmitValidator` 加 `validate_work`(仿 `validate_character`:数量[1,8]、单本命、去重)。`SubmitService` 加 `submit_work` + `get_work_submit`(仿 character,写 raw_work)。
- [ ] **Step 3:** `dao.py` 加 `create_work_submit` / `get_work_submit`(仿 character,表 RawWorkSubmit)。
- [ ] **Step 4:** 若 Block 1 已合并:`submit_work` 开头加 `await self._require_questionnaire(vote_id)`。若 Block 1 未合并,本任务实现同款门禁。
- [ ] **Step 5:** 单元测试 `validate_work`;集成测试 submit_work 写读。`pytest` + flake8;commit `feat(works): submit_work + validate_work (B-038)`

---

## Task 5: vote_data 处理层 work

**Files:** Modify `src/apps/vote_data/{models,dao,service}.py`; test

- [ ] **Step 1:** Read vote_data 的 character 处理(`submit_character_vote` / `get_character_by_id`)。
- [ ] **Step 2:** models 导出 Work;dao 加 `get_work_by_id`/`create_work`/`update_work` + `get_all_work_submissions`(仿 character)���
- [ ] **Step 3:** service 加 `submit_work_vote`(upsert work 表)。
- [ ] **Step 4:** 测试 + flake8 + commit `feat(works): vote_data work processing layer (B-038)`

---

## Task 6: ComputeService 作品计算

**Files:** Modify `src/apps/result/{compute_dao,compute,compute_service}.py`; test

- [ ] **Step 1:** Read `ComputeDAO.load_char_votes` + `load_char_candidates` + ComputeService 角色计算路径。
- [ ] **Step 2:** `compute_dao.py` 加 `load_work_votes`(读 Work 表)+ `load_work_candidates`(读 CandidateWork)。
- [ ] **Step 3:** ComputeService 的全量计算流程把 work 纳入:计算作品排名 → 写 Redis `result:{year}:works:ranking` + `:global`(仿 chars)。`finalize_ranking` 的 category 循环加 `"work"`。
- [ ] **Step 4:** 单元/集成测试作品计算(仿 `test_compute`)。flake8 + commit `feat(works): ComputeService work ranking (B-038)`

---

## Task 7: 结果查询 + GraphQL 接线

**Files:** Modify `src/apps/result/{schemas,service,dao,router}.py`, `src/api/graphql/...`

- [ ] **Step 1:** result schemas 的 category Literal 扩 `work`(RankingQuery 等)。ResultDAO 的 `_category_key` 映射加 `work -> works`。
- [ ] **Step 2:** GraphQL:加 `submitWorkVote` mutation + `getSubmitWorkVote` query(仿 submit_bridge 的 character)+ work ranking query(仿 result.py ranking)。
- [ ] **Step 3:** contract 测试:SDL 含 submitWorkVote/getSubmitWorkVote;work ranking 查询。
- [ ] **Step 4:** `pytest tests/ -q` 无回归 + flake8 `src/`;commit `feat(works): result query + graphql work voting (B-038)`

---

## Task 8: 投票对象列表端点 /vote-objects/works

**Files:** Create/Modify 一个公开路由(可放 `src/apps/result/router.py` 或新 `src/apps/vote_objects/`)

- [ ] **Step 1:** 加 `GET /vote-objects/works?vote_year=`:读 `candidate_work`,按 `release_date`(无则按 category)分组,返回 `{vote_year, groups:[{group, items:[{id,name,name_jp,release_date,category}]}]}`。公开只读。
- [ ] **Step 2:** 集成测试:导入几条 work 候选 → 端点返回正确分组。
- [ ] **Step 3:** contract 测试 shape。`pytest` + flake8;commit `feat(works): public /vote-objects/works grouped listing (B-038)`

---

## Task 9: 管理端 UI + 全量回归

**Files:** Modify `src/admin_ui/index.html`; `docs/BACKLOG.md`

- [ ] **Step 1:** 候选项 Tab 的类别下拉加 `<option value="work">作品</option>`;导入弹窗类别同。
- [ ] **Step 2:** `pytest tests/ -q --tb=short`(仅既有 pnvs 本地失败可接受);`flake8 src/ --max-line-length=88` 干净。
- [ ] **Step 3:** BACKLOG 标 B-038;commit + push。

---

## Self-Review 注意
- 每层先 Read character 对应文件再仿写,保持命名一致(category `"work"`,Redis 段 `works`)。
- 数量上限 8 对齐角色;如需不同,集中一处常量。
- migration down_revision 串到 0007(Block 1);若 Block 1 未合并,串到 0006 并在合并时调顺序。
