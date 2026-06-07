# Block 2 作品投票 — 前端(thvote-fe)Implementation Plan

> **For agentic workers:** 前端 Vue 3 monorepo,手工验收为主。代码以仓库现有 `vote-character` 模式为准镜像。
> 仓库：`D:\personal\thvote-fe`，包：`packages/vote`、`packages/result`
> 前置：后端 Block 2 + `/vote-objects/works` 必须**先合并**。

**Goal:** 新增作品投票页(仿 vote-character),**从后端拉作品列表**(Block 3 试点),并在 result 页展示作品排名。

---

## File Map

| 文件 | 操作 |
|---|---|
| `packages/vote/src/vote-work/`(整目录) | Create — 仿 vote-character |
| `packages/vote/src/vote-work/lib/workDataSource.ts` | Create — 从后端拉作品列表 |
| `packages/vote/src/graphql/`(work mutations/queries) | Create + codegen |
| `packages/vote/src/main/main.ts` | Modify — 路由 + 守卫 |
| 导航/入口组件 | Modify — 加"作品"入口 |
| `packages/result/`(work ranking 展示) | Create |

---

## Task 1: GraphQL 契约 + codegen

- [ ] **Step 1:** 以后端 SDL 为准,在 `packages/vote/src/graphql/` 加 `submitWorkVote`、`getSubmitWorkVote` 文档(仿 character 同名文件)。
- [ ] **Step 2:** 跑 codegen 更新类型(按仓库脚本,如 `pnpm --filter vote codegen`)。
- [ ] **Step 3:** commit `feat(vote): work voting graphql operations`

---

## Task 2: 作品列表数据源(从后端拉)

**File:** Create `packages/vote/src/vote-work/lib/workDataSource.ts`

- [ ] **Step 1:** 实现 `fetchWorkList(voteYear)`:`GET /vote-objects/works?vote_year=` → 返回 `groups`。可加会话内缓存。
- [ ] **Step 2:** 类型定义对齐后端返回(`{group, items:[{id,name,name_jp,release_date,category}]}`)。
- [ ] **Step 3:** commit `feat(vote): work list data source from backend`

> 这是与角色/音乐的关键差异:作品列表来自后端,不是 `shared/data`。

---

## Task 3: 作品投票页

**Files:** Create `packages/vote/src/vote-work/`(组件 + lib)

- [ ] **Step 1:** Read `packages/vote/src/vote-character/`(整页:VoteCharacter.vue + lib)作为蓝本。
- [ ] **Step 2:** 仿写 VoteWork.vue:
  - 加载时调 `fetchWorkList` 拿分类列表渲染选择组件
  - 选择交互仿角色:多选、上限 8、一个本命(first)、每项 reason
  - 提交 `submitWorkVote`(voteToken + works[])
  - 进入时 `getSubmitWorkVote` 回填
- [ ] **Step 3:** 错误处理:`QUESTIONNAIRE_NOT_COMPLETED`(同 Block 1 前端)、时间窗。
- [ ] **Step 4:** commit `feat(vote): work voting page (mirrors character)`

---

## Task 4: 路由 + 入口

- [ ] **Step 1:** `main/main.ts` 加作品投票路由;守卫沿用(问卷完成 + 投票窗)。
- [ ] **Step 2:** 导航/首页入口加"作品投票"。
- [ ] **Step 3:** commit `feat(vote): work voting route + entry`

---

## Task 5: 结果页作品排名

**Files:** `packages/result/`

- [ ] **Step 1:** Read result 包的角色/音乐 ranking 展示。
- [ ] **Step 2:** 仿写作品 ranking 组件 + work ranking query;数据源模式(local/graphql/auto)沿用。
- [ ] **Step 3:** commit `feat(result): work ranking display`

---

## Task 6:(可选)导出图片支持作品
- [ ] 低优先级,本期可不做。现有导出支持角色/音乐/CP,作品仿写下期。

---

## 手工验收清单
- [ ] 作品投票页从后端拉到分类列表并正确渲染
- [ ] 选择/本命/理由/上限(8)校验与角色一致
- [ ] 提交成功 → 重新进入正确回填
- [ ] 未完成问卷 → 被门禁拦截(友好提示)
- [ ] 结果页作品排名正确
- [ ] 回归:角色/音乐/CP/二创/问卷不受影响

---

## 依赖
- 严格以后端 SDL + `/vote-objects/works` 实际返回为准对齐字段。
- 后端先合并再联调。

## 关联
- 后端 plan：`2026-06-08-works-voting-backend.md`
