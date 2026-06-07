# Block 3A 问卷结构化系统 — 前端(thvote-fe)Implementation Plan

> **For agentic workers:** 前端 Vue 3,手工验收为主。**一次性切换**,务必后端 structure/submitPaperV2 先合并并灌入题库。
> 仓库：`D:\personal\thvote-fe`，包：`packages/vote`
> 前置：后端 3A 合并 + `/admin/questionnaire/import` 已灌入现有题库。

**Goal:** 问卷结构改从后端拉、提交改结构化答案、弃 paperJson 兼容层;保留 questionnaireV2 的 parser/规则引擎。

---

## File Map

| 文件 | 操作 |
|---|---|
| `packages/vote/src/questionnaire/lib/questionnaire.ts`(V2 入口) | 结构来源改后端 |
| `packages/vote/src/questionnaire/lib/questionnaireV2PaperJson.ts` | 停用 |
| `packages/vote/src/questionnaire/Questionnaire.vue` | 提交/回填改 v2 |
| `packages/vote/src/graphql/`(paper v2) | 新增 + codegen |
| `packages/shared/data/questionnaireV2.ts` | 运行时数据源停用,保留 interface |
| `packages/vote/src/main/main.ts` | 完成判定以后端为准 |

---

## Task 1: 结构来源改后端

- [ ] **Step 1:** Read `questionnaire/lib/questionnaire.ts` / `questionnaireV2Parser.ts`,确认 parser 消费的是 `QuestionnaireDefinitionAllV2`。
- [ ] **Step 2:** 新增 `fetchQuestionnaireStructure(voteYear)` 调 `GET /questionnaire/structure?vote_year=`,返回 `QuestionnaireDefinitionAllV2`。
- [ ] **Step 3:** 把原本 import 自 `shared/data/questionnaireV2` 的运行时结构来源换成该 fetch 结果(interface 类型保留)。
- [ ] **Step 4:** 确认 parser/渲染/related/mutex 不改即可工作(形状一致)。
- [ ] **Step 5:** commit `feat(questionnaire): load structure from backend`

---

## Task 2: 提交/回填改结构化

- [ ] **Step 1:** `packages/vote/src/graphql/` 加 `submitPaperV2`、`getPaperV2`(以后端 SDL 为准);codegen。
- [ ] **Step 2:** `Questionnaire.vue` 提交改调 `submitPaperV2(answerStateV2)`,**不再** `serializeQuestionnaireAnswerStateV2ToPaperJson`。
- [ ] **Step 3:** 回填改 `getPaperV2`。
- [ ] **Step 4:** 停用 `questionnaireV2PaperJson.ts`(删除引用;文件可留作历史)。
- [ ] **Step 5:** commit `feat(questionnaire): submit/restore structured answers via v2`

---

## Task 3: 完成判定以后端为准

- [ ] **Step 1:** `main.ts` 守卫的 `IsQuestionnaireAllDone` 以后端门禁为最终权威(前端本地预判仅作 UI 提示);确保未完成时投票被后端拦截能优雅处理(Block 1 前端兜底已加)。
- [ ] **Step 2:** commit `feat(questionnaire): defer completion gate to backend`

---

## 手工验收清单
- [ ] 问卷页从后端拉到结构并正确渲染(题组/题型/选项)
- [ ] related 跳转、mutex 互斥、问题组隐藏(initialQuestionId 末位 0)行为与切换前一致
- [ ] 提交结构化答案 → 重新进入正确回填
- [ ] 必答未答 → 投票被后端门禁拦截,前端友好提示
- [ ] 回归:问卷修改页、各投票页不受影响

---

## 依赖
- 一次性切换:后端 structure + submitPaperV2 + 题库导入 必须先就绪。
- 字段命名严格对齐后端返回(camelCase)。

## 关联
- 后端 plan：`2026-06-08-questionnaire-backend.md`
