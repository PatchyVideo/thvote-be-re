# Block 3A 问卷结构化系统 — 后端(含管理端)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development / executing-plans. Steps use `- [ ]`.

**Goal:** 把问卷结构迁到后端(模型 + admin CRUD + 整树导入 + 结构查询 + 结构化答题 + 完成校验),形状对齐前端 `questionnaireV2`。

**Architecture:** 4 张结构表(questionnaire_def/question_group_def/question_def/option_def)+ paper_answer;结构查询端点组装成 `QuestionnaireDefinitionAllV2` 形状;完成校验服务替换 Block 1 弱门禁。

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Strawberry GraphQL

**Design Spec:** `docs/superpowers/specs/2026-06-08-questionnaire-backend-design.md`
**对齐基准:** `D:\personal\thvote-fe\packages\shared\data\questionnaireV2.ts`(实现前先读其 interface)

---

## Task 1: 结构模型 + PaperAnswer + migration 0009

**Files:** Create `src/db_model/questionnaire_def.py`(含 4 模型 + PaperAnswer);Modify `__init__.py`;Create migration

- [ ] **Step 1:** 按 spec §四 创建 5 个模型(QuestionnaireDef / QuestionGroupDef / QuestionDef / OptionDef / PaperAnswer)。related/mutex 用 `JSON`。
- [ ] **Step 2:** `__init__.py` 导出全部 + `__all__`。
- [ ] **Step 3:** 验证 import OK。
- [ ] **Step 4:** 手写 `alembic/versions/0009_questionnaire_structure.py`(`down_revision` 串到 0008/最新),create 5 表 + 约束。
- [ ] **Step 5:** flake8 + commit `feat(questionnaire): structure models + PaperAnswer + migration 0009 (B-039)`

---

## Task 2: 结构组装(DB → questionnaireV2 形状)(TDD)

**Files:** Create `src/apps/questionnaire/assembler.py`(纯函数);test

- [ ] **Step 1:** 先读 `questionnaireV2.ts` 的 `QuestionnaireDefinitionAllV2` 等 interface,明确目标 JSON 形状(camelCase:questionGroups/initialQuestionId/relatedQuestionIds/mutexOptionIds/optionGroup)。
- [ ] **Step 2:** 写失败测试 `tests/unit/test_questionnaire_assembler.py`:给定若干 def 行(用普通 dict/对象模拟),`assemble_structure(questionnaires, groups, questions, options)` 返回 `{mainQuestionnaire:{requiredQuestionnaire,...}, extraQuestionnaire:{ex1..5}}`,每级字段名与形状正确,options 含 relatedQuestionIds/mutexOptionIds/optionGroup。
- [ ] **Step 3:** 实现 `assembler.py`:按 slot 把 questionnaire 归到 main/extra 的对应键;嵌套组装 groups→questions→options;字段转 camelCase。
- [ ] **Step 4:** 测试通过;flake8 + commit `feat(questionnaire): DB→questionnaireV2 structure assembler (B-039)`

---

## Task 3: 完成校验服务(TDD)

**Files:** Create `src/apps/questionnaire/completion.py`;test

- [ ] **Step 1:** 写失败测试:`is_complete(structure, answers) -> bool`(纯函数,入参为已组装结构 + 用户答案列表)。覆盖:必填问卷的必答题全答→True;缺一→False;只缺可选问卷→True。
  > "必答题"定义:category=main 且 slot 属必填问卷的、且 type≠Input 或业务标记 required 的问题(实现时与前端规则对齐;本期规则:必填问卷里每个"当前可见路径上的题"需有答案 —— 简化为"必填问卷每个问题组至少有一条 paper_answer")。
- [ ] **Step 2:** 实现 `completion.py` 的纯函数 `is_complete`。
- [ ] **Step 3:** 测试通过;flake8 + commit `feat(questionnaire): completion check pure logic (B-039)`

---

## Task 4: questionnaire domain(dao/service/router)

**Files:** Create `src/apps/questionnaire/{dao,service,schemas,router}.py`;register router

- [ ] **Step 1:** dao:读 4 张结构表(按 vote_year)、读/写 paper_answer、读必填结构供完成校验。
- [ ] **Step 2:** service:`get_structure(vote_year)`(调 assembler)、`submit_answers(vote_id, vote_year, answer_state)`(写 paper_answer,按 questionnaire+group upsert)、`get_answers(vote_id, vote_year)`、`is_complete(vote_id, vote_year)`(调 completion)。
- [ ] **Step 3:** router:`GET /questionnaire/structure?vote_year=`(公开)。注册进 `src/api/rest/v1/__init__.py`。
- [ ] **Step 4:** 集成测试:灌入结构 → structure 端点返回正确形状;submit→get 往返。
- [ ] **Step 5:** flake8 + commit `feat(questionnaire): domain service + structure endpoint (B-039)`

---

## Task 5: GraphQL submitPaperV2 / getPaperV2

**Files:** Modify `src/api/graphql/...`

- [ ] **Step 1:** 读现有 submit_bridge 的 paper(submitPaperVote)实现作蓝本。
- [ ] **Step 2:** 加 `submitPaperV2(QuestionnaireAnswerStateV2 输入)` mutation + `getPaperV2(voteToken)` query,接 questionnaire service。
- [ ] **Step 3:** contract 测试 SDL。`pytest tests/ -q` + flake8;commit `feat(questionnaire): graphql submitPaperV2/getPaperV2 (B-039)`

---

## Task 6: 完成校验接入投票门禁

**Files:** Modify `src/apps/submit/service.py`

- [ ] **Step 1:** `_require_questionnaire` 改为调 `QuestionnaireCompletionService.is_complete(vote_id, vote_year)`(替换 Block 1 的"存在任意 paper"弱校验)。
- [ ] **Step 2:** 集成测试:必答未答→门禁拦截;答全→放行。覆盖角色/音乐/CP/作品。
- [ ] **Step 3:** `pytest tests/ -q` + flake8;commit `feat(questionnaire): upgrade vote gate to required-questions completion (B-039)`

---

## Task 7: admin CRUD + 整树导入 + UI

**Files:** Modify `src/apps/admin/...`;`src/admin_ui/index.html`;test

- [ ] **Step 1:** admin 端点:questionnaires/question-groups/questions/options 的 GET/POST/PUT/DELETE(`X-Admin-Secret`)。
- [ ] **Step 2:** `POST /admin/questionnaire/import`:接收整树 JSON(questionnaireV2 形状)→ 拆解写入 4 张表(覆盖同 vote_year)。
- [ ] **Step 3:** 管理端「问卷配置」Tab:树形展示 + 增删改;整树导入入口(粘贴 JSON,复用候选导入的 dry-run 思路可选)。
- [ ] **Step 4:** 集成 + contract 测试。
- [ ] **Step 5:** `pytest tests/ -q` + flake8 `src/`;commit `feat(admin): questionnaire config CRUD + tree import + UI (B-039)`

---

## Task 8: 全量回归 + BACKLOG

- [ ] **Step 1:** `pytest tests/ -q --tb=short`;`flake8 src/ --max-line-length=88`。
- [ ] **Step 2:** BACKLOG 标 B-039;commit + push。

---

## Self-Review 注意
- 结构端点输出必须与 `questionnaireV2.ts` 的 interface **逐字段对齐**(camelCase),否则前端 parser 无法直接消费。
- 首次上线流程:后端建表 → `/admin/questionnaire/import` 灌入前端现有题库 JSON → 前端切换。
- 完成校验的"必答"规则本期取简化定义(见 Task 3 注),与前端确认后可收紧。
