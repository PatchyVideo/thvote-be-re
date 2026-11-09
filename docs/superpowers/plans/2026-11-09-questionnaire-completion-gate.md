# 问卷整体完成闸门实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. 用户本轮指定 Sol 子代理修正文档；代码由主 agent 按本计划实施，未经新增授权不再扩展委派。

**Goal:** 用本届已保存的结构化答案统一执行“所有必填＋至少一份 extra 选填”，退出旧问卷放行例外。

**Architecture:** 复用 rules → completion → QuestionnaireService → SubmitService 现有调用链，main/extra 和 required 继续承载配置。前端共享政策函数提供体验预判，服务端提交前做最终判断。无新增数据模型或公开接口。

**Tech Stack:** Python / FastAPI / SQLAlchemy / pytest；TypeScript / Vue / tsx；沿用现有依赖。

**Spec:** [问卷整体完成闸门设计](../specs/2026-11-09-questionnaire-completion-gate-design.md)。

**Status:** 2026-11-09 实现、验证及独立只读审阅完成，已提交后端23fb761、前端16be240，未推送或部署。下方基线和任务步骤保留执行依据，结果见文末。

## Global Constraints

- 继续使用现有 main/extra、required 字段。
- 提交问卷继续允许合法但未完成的快照。
- 公开 API、错误类型 `QUESTIONNAIRE_NOT_COMPLETED` 和鉴权流程不变，不新增完成查询接口。
- 提名服务不调用同一闸门，本轮不扩大拦截范围。
- 不新增表、字段、配置项或依赖，不执行真实数据迁移。
- 保留两仓库无关未提交改动，不自动提交、推送或部署；原始需求附件不改写。

## Review Focus

- 只有旧 raw_paper 有内容：不能跳过本届结构化答案评估（任务1）。
- 问卷有组但没有题目，或完全没有组：不能由空集合/历史答案行数获得完成资格（任务1）。
- 角色、音乐、组合通过不同 API 提交：均须在写票前经过同一闸门（任务1）。
- A 完成但选填仅部分完成：可保存问卷，不能投票；A＋完整任一选填才能放行（任务1，已有基线用例复用）。
- 前端本地状态显示完成但后端尚未保存：后端拒绝仍须正常向用户展示，统计不套用整套配额（任务2）。

## 已核对基线

后端 `/data/sunyunbo/www/Thvote-be/thvote-be-re`、前端 `/data/sunyunbo/www/Touhou-Vote`，均在 `feat/questionnaire-backend-source`。已提交后端基线 e9dc072，前端基线 4fda4ef；以下整体政策属于已有本地改动，尚未提交：

- [x] BE `src/apps/questionnaire/completion.py:meets_completion_policy(questionnaires: list[dict], completed: set[int]) -> bool` 实现全部 required＋至少一份 extra。
- [x] FE `packages/shared/api/questionnaire.ts:meetsQuestionnaireCompletionPolicy`、`questionnaireStateV2.ts:isQuestionnaireAllDoneV2` 和首页提示使用相同规则。
- [x] 本轮规则测试基线：后端5份相关文件56 passed；前端共享问卷、运行时状态、结果索引三份文件6 passed；`pnpm vote:build` 通过。flake8、diff 和文档链接检查通过。

上述验证早于退出 legacy 兼容，不能代替任务1的验证。当前没有核验线上题库、真实账号或部署状态。

### Task 1：收口服务端门禁并移除问卷完成兜底

**Files:**
- Modify: `src/apps/submit/service.py`，只调整 `_require_questionnaire`。
- Modify: `src/apps/questionnaire/completion.py`，删除未配置问卷的 row-coverage 完成分支及其专用整形/去重逻辑。
- Test: `tests/unit/test_questionnaire_completion.py`、`tests/integration/test_paper_v2_validation.py`、`tests/integration/test_security_submit.py`。
- Adapt if affected: `tests/integration/test_submit.py` 中依赖旧 paper 放行的准备数据。

**Interfaces:**
- Consumes: `QuestionnaireService.get_answers(vote_id: str, vote_year: int) -> list[dict]` 和 `is_complete(vote_id: str, vote_year: int, *, answers: list[dict] | None = None) -> bool`。
- Produces: `_require_questionnaire(vote_id: str) -> None`；不满足条件抛现有 `QuestionnaireNotCompletedError`，拒绝发生于写票前。单份完成继续经 `completed_questionnaire_ids` 输出 `set[int]`。

- [x] 修改现有无题目兼容用例，明确“有旧行但没有真实题目”为 False；补同层零题组不完成断言。正向整体完成用例使用现有 `real_structure`，不再依赖空题库夹具。
- [x] 在现有集成夹具中覆盖非空 raw_paper 仍被拒绝、只有 A 被拒绝、A＋完整选填放行；角色/音乐/组合各提交一例拒绝并检查对应真实表无新行。复用既有合法部分保存和 A＋选填正向用例，不跨层复制整个真值表。
- [x] 删除 `_require_questionnaire` 中 `latest_paper_json` 查询与提前 return；保留本届 `vote_year`、已保存答案读取、预读答案传递及原错误映射。
- [x] 删除 `completion.py` 的无题目 row-coverage 兜底。无题目问卷不计完成；不借本次修改重做合法性、分支算法或结果计数。
- [x] 调整 `test_security_submit.py` 的旧 paper 正向预期；`test_submit.py` 的投票成功用例改用真实结构化作答准备资格。仍验证旧 paper 接口本身的用例保留，不直接删掉或放宽断言。
- [x] 在后端目录集中运行：

```bash
python -m pytest tests/unit/test_questionnaire_completion.py tests/integration/test_paper_v2_validation.py tests/integration/test_questionnaire_domain.py tests/integration/test_security_submit.py tests/integration/test_submit.py tests/integration/test_result_compute.py -q
python -m flake8 src/apps/questionnaire/completion.py src/apps/submit/service.py
git diff --check
```

预期：全部通过；原始答案合法性和单份统计行为保持。若另有现存用例实际依赖 raw_paper 放行，只调整其资格准备并运行受影响文件，不屏蔽闸门。

### Task 2：核对前端反馈、统一现役文档并验收

**Files:**
- Inspect existing local changes: FE `packages/shared/api/questionnaire.ts`、`packages/vote/src/questionnaire/lib/questionnaireStateV2.ts`、首页两处提示。
- Inspect: FE `packages/vote/src/main/main.ts` 与角色/音乐/组合的现有提交错误处理；仅发现缺口时局部修复对应文件。
- Modify: BE `docs/architecture/backend-overview.md`、`docs/migration/questionnaire-audit-2026-11-09.md`、相关 API 文档、BACKLOG、CHANGELOG；FE 现役问卷/结果说明与 CHANGELOG。

**Interfaces:**
- Consumes: 服务端现有 `QUESTIONNAIRE_NOT_COMPLETED` 及前端 `meetsQuestionnaireCompletionPolicy(questionnaires, completed): boolean`。
- Produces: 文档能区分本地预判、已保存答案、单份统计、整套投票资格，并指出唯一政策修改点及实际强制入口。

- [x] 核对现有错误处理能展示后端拒绝；本地草稿不得宣称已经取得服务端资格。若现有反馈已经满足，保持原实现，不新增接口、资格缓存或状态机。
- [x] 主 agent 纳入用户指定 Sol 的文档修正，核对实际差异；旧计划只加后续政策说明，原始需求附件和已完成阶段记录保留历史。
- [x] 任务1落实后，将文档中的“计划移除 legacy/row-coverage”改为实际完成状态，记录真实配置仍待核验。不能把“文档已改”写成“线上已启用”。
- [x] 在前端目录运行：

```bash
pnpm exec tsx --tsconfig packages/vote/tsconfig.json --test packages/shared/api/__tests__/questionnaire.test.ts packages/vote/src/questionnaire/lib/__tests__/questionnaireStateV2.test.ts packages/result/src/lib/__tests__/Questionnaire.test.ts
pnpm vote:build
git diff --check
```

预期：测试和构建成功。只有文档变化时无需重复已经通过的前端构建；若本轮没有再改前端代码，沿用已记录的本地验证证据。

- [x] 检查新增文档相对链接，更新本计划状态；交付实际改动、检查结果和未验证项。真实 A/B/C/D 配置核对、清库、重算、提交和部署不在本次计划执行的默认授权内。

## 执行记录

- 移除 `_require_questionnaire` 的 legacy 查询/放行和 completion 的空定义行覆盖分支；继续按本届最新已存批次检查，无逐题查库或新增状态。
- 新用例先复现7项失败（无题目完成4项、raw_paper 放行3项），再移除分支。API 核对另复现 REST 三个入口未处理异常；局部补齐 HTTP 422 / QUESTIONNAIRE_NOT_COMPLETED 映射，无新增端点或响应字段。GraphQL 保持原错误类型，更新中文补填提示。
- 测试准备改为真实结构与 V2 保存，保留旧问卷接口本身的测试。初次集中运行的4项失败定位为新夹具遗漏了 resolver 单独导入的 Redis 依赖替换；补用既有 fakeredis，未改生产 Redis 逻辑。
- 后端上述6份文件的集中命令通过：85 passed、2项现有弃用警告。随后新增一项真实 GraphQL 拒绝反馈覆盖，仅重跑受影响文件：`python -m pytest tests/integration/test_submit.py -q --tb=short` → 26 passed、相同2项警告；没有重复扩大测试范围。
- `python -m flake8 src/apps/questionnaire/completion.py src/apps/submit/service.py src/apps/submit/router.py src/api/graphql/errors.py` 通过。两仓库 `git diff --check` 通过。
- 前端按任务2命令运行3份测试文件，6 passed；`pnpm vote:build` 通过（12.87s）。测试中的结构 HTTP 503 是已有失败重试用例的预期日志。首页说明当前状态为草稿，部分保存不再提示完整完成；三类投票页面能展示现有 human_readable_message。
- 用户指定 Sol 的文档修正已经纳入；现役架构、接口、剩余清单及前端指南同步实际退出状态，旧阶段设计仅附后续规则说明。
- executing-plans 要求的最终独立审阅已完成：只读检查实际 diff、完成评估、三类提交链路和测试断言，无需修复项。真实配置、历史清理、提名扩展不属于本轮；提交期间编辑导致的低概率提示时序不引入新状态机。
- 未核验真实 A/B/C/D 配置或真实账号，不清库、不迁移、不重算；没有浏览器交互、推送或部署。实现阶段未提交，用户随后明确授权本轮前后端提交；无schema变更，代码回退即可恢复原门禁，数据保持原样。
