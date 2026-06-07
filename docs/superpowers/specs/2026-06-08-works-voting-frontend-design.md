# Block 2 作品投票 — 前端设计稿(thvote-fe)

> 创建日期：2026-06-08
> 最后更新：2026-06-08
> 配套后端设计稿：[`2026-06-08-works-voting-backend-design.md`](./2026-06-08-works-voting-backend-design.md)
> 仓库：`D:\personal\thvote-fe`，包：`packages/vote`、`packages/result`

## 一、背景

官方作品投票是全新部门,前端无 vote-work 页。本块新增作品投票页(仿 vote-character),并**首次从后端拉投票对象列表**(不再像角色/音乐那样用前端静态 `shared/data`)—— 这是 Block 3 投票对象迁后端的前端试点。

## 二、改动点

### 1. 新增作品投票页 `packages/vote/src/vote-work/`
仿 `vote-character/` 整页结构(组件 + lib + 提交):
- **数据来源(关键差异)**:作品候选列表**从后端拉** `GET /vote-objects/works?vote_year=`,而非 import 静态 data。
  - 返回已按发布时间分类(`groups`),前端直接渲染分类选择组件。
  - 可做轻缓存(本次会话内),但来源是后端。
- 选择交互:仿角色(多选、上限 8、一个本命 first、每项 reason)。
- 提交:`submitWorkVote` mutation(voteToken + works[]{id, first, reason}),仿 `submitCharacterVote`。
- 回填:`getSubmitWorkVote`(voteToken)回显已提交。

### 2. 路由 + 导航
- `packages/vote/src/main/main.ts` 加作品投票路由;导航/入口加"作品"。
- 路由守卫沿用现有:未完成问卷 / 不在投票窗 → 拦截(与角色一致)。

### 3. 结果展示 `packages/result/`
- 加作品排名展示,仿角色/音乐的 ranking 组件 + GraphQL work ranking query。
- 数据源模式(local/graphql/auto)沿用现有结果页框架。

### 4. 导出图片(可选,本期可不做)
- 现有导出支持角色/音乐/CP。作品导出仿写,优先级低,可下期。

## 三、与现有架构的差异(重要)

| 维度 | 角色/音乐(现状) | 作品(本块) |
|---|---|---|
| 候选列表来源 | 前端静态 `@touhou-vote/shared/data/*` | **后端 `/vote-objects/works`** |
| 分类 | 前端按 work/album 分组 | **后端返回已分组** |
| 提交 | submitCharacterVote 等 | submitWorkVote(同形态) |

→ 作品页是"从后端拉列表"的样板。Block 3 会把角色/音乐也改成这种从后端拉的模式,可复用作品页的数据加载封装。

## 四、GraphQL 契约(以后端 SDL 为准)
- mutation `submitWorkVote(WorkSubmitGQL{ voteToken, works:[{id, first, reason}] })`
- query `getSubmitWorkVote(voteToken) → { works:[{id, first, reason}] }`
- query work ranking(result 页用),仿 character ranking
- REST `GET /vote-objects/works?vote_year=` → `{ vote_year, groups:[{group, items:[{id,name,name_jp,release_date,category}]}] }`

## 五、测试/验收(手工)
- 作品投票页:从后端拉到分类列表并渲染;选择/本命/理由/上限校验与角色一致。
- 提交 → 回填正确;门禁(未完成问卷)被拦截。
- 结果页作品排名正确展示。
- 回归:角色/音乐/CP/二创/问卷不受影响。

## 六、文件变更一览(前端)

| 文件 | 操作 |
|---|---|
| `packages/vote/src/vote-work/`(整目录) | 新建,仿 vote-character |
| `packages/vote/src/vote-work/lib/workDataSource.ts` | 新建:从后端拉作品列表 |
| `packages/vote/src/graphql/`(submitWorkVote/getSubmitWorkVote) | 新增 + codegen |
| `packages/vote/src/main/main.ts` | 加路由 + 守卫 |
| 导航/入口组件 | 加"作品"入口 |
| `packages/result/`(work ranking 展示) | 新增 |

## 七、依赖
- **依赖后端 Block 2 + `/vote-objects/works` 先合并**,前端按最终 SDL 对齐。

## 八、关联
- 后端设计稿:[`2026-06-08-works-voting-backend-design.md`](./2026-06-08-works-voting-backend-design.md)
