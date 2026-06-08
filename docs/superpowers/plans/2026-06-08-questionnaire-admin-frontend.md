# 问卷契约变更 — 投票前端(thvote-fe)Implementation Plan

> **For agentic workers:** 前端 Vue 3 monorepo,手工验收为主。**一次性切换**,后端结构端点(数组契约)+ submitPaperV2 先合并并录入题库。
> 仓库：`D:\personal\thvote-fe`，包：`packages/vote`
> 前置：后端 B-041 合并(structure 数组契约 + 扁平答案数组)。

**Goal:** 投票端问卷模块适配新契约:结构从后端拉的**问卷数组**、按 category/required/hiddenByDefault 渲染与门禁、related/mutex 用真实自增 id、提交用扁平答案数组。

**取代** B-039 原前端 plan(固定 8 槽 + questionnaireV2 静态结构)。

---

## File Map

| 文件 | 操作 |
|---|---|
| `packages/vote/src/questionnaire/lib/questionnaire.ts`(V2 入口) | 结构来源改后端 + 顶层改数组 |
| `packages/vote/src/questionnaire/lib/questionnaireV2Parser.ts` | 适配数组 + category/hiddenByDefault(算法不变) |
| `packages/vote/src/questionnaire/Questionnaire.vue` | 按数组/分区渲染;提交扁平答案数组 |
| `packages/vote/src/graphql/`(paper v2) | 对齐后端 SDL |
| `packages/shared/data/questionnaireV2.ts` | 运行时数据源停用;interface 改数组形态(留类型) |
| `packages/vote/src/main/main.ts` 守卫 | 完成判定以后端为准 |

---

## Task 1: 结构来源 + 顶层数组

- [ ] **Step 1:** Read `questionnaire/lib/questionnaire.ts` 与 `questionnaireV2Parser.ts`,确认 parser 当前消费固定 8 槽对象的入口。
- [ ] **Step 2:** 新增 `fetchQuestionnaireStructure()` 调 `GET /questionnaire/structure`(无参),返回 `{questionnaires: [...]}`。
- [ ] **Step 3:** 顶层从「8 命名槽」改为「遍历 `questionnaires[]`」:按 `category`(main/extra)分区、`order` 排序;弃用 `@touhou-vote/shared/data/questionnaireV2` 运行时数据源。
- [ ] **Step 4:** commit `feat(questionnaire): load questionnaire array from backend`

---

## Task 2: parser 适配数组 + 字段

- [ ] **Step 1:** `questionnaireV2Parser.ts`:输入改问卷数组;题组隐藏判定从 `initialQuestionId` 末位改读 `hiddenByDefault`;related 跳转 / mutex 互斥仍按 id 比对(算法不变,id 现为自增真实 id)。
- [ ] **Step 2:** 类型 `questionnaireV2.ts` interface 改数组形态(`Questionnaire{ id,key,title,category,required,order,questionGroups }`、group 加 `hiddenByDefault`、question 加 `maxInputLen`),保留作 TS 类型。
- [ ] **Step 3:** commit `feat(questionnaire): parser consumes array + category/hiddenByDefault`

---

## Task 3: 渲染 + 提交 + 回填

- [ ] **Step 1:** `Questionnaire.vue`:按 category 分区渲染问卷数组;题组按 hiddenByDefault 初始隐藏;related/mutex 行为同前。
- [ ] **Step 2:** 提交改 `submitPaperV2(voteToken, answers)`,`answers` 为**扁平数组** `[{questionnaireId, groupId, activeQuestionId, selectedOptionIds, input}]`;由当前作答状态构建。
- [ ] **Step 3:** 回填 `getPaperV2(voteToken)` → 还原作答状态。
- [ ] **Step 4:** `packages/vote/src/graphql/` 同步 submitPaperV2/getPaperV2 文档 + codegen。
- [ ] **Step 5:** commit `feat(questionnaire): render array + submit flat answers via submitPaperV2`

---

## Task 4: 完成判定以后端为准

- [ ] **Step 1:** `main.ts` 守卫:本地预判改为"所有 `required=true` 问卷的题组已答";最终以后端门禁为权威(投票被拦 → 友好提示回问卷)。
- [ ] **Step 2:** commit `feat(questionnaire): completion gate based on required questionnaires`

---

## 手工验收清单
- [ ] 从后端拉到问卷数组,按 main/extra 正确分区、排序渲染
- [ ] related 跳转、mutex 互斥、题组默认隐藏(hiddenByDefault)行为正确(id 改自增后仍对)
- [ ] 提交扁平答案 → 回填正确
- [ ] required 问卷未答 → 投票被后端门禁拦截,前端友好提示
- [ ] 回归:问卷修改、各投票页不受影响

---

## 依赖与顺序
- 一次性切换:后端 structure 数组契约 + submitPaperV2 + 题库录入 先就绪。
- 字段命名严格对齐后端(camelCase:relatedQuestionIds/mutexOptionIds/hiddenByDefault/maxInputLen/category/required)。

## 关联
- 后端 plan：`2026-06-08-questionnaire-admin-backend.md`
- 后端/前端 design：`docs/superpowers/specs/2026-06-08-questionnaire-admin-{backend,frontend}-design.md`
