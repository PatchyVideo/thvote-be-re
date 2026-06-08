# Block 3B 投票对象迁后端 — 前端(thvote-fe)Implementation Plan

> **For agentic workers:** 前端 Vue 3,手工验收为主。**一次性切换**,后端 `/vote-objects/characters|music` 先合并。
> 仓库：`D:\personal\thvote-fe`，包：`packages/vote`
> 前置：后端 3B 合并 + 候选数据导入(含自动合并)。

**Goal:** 角色/音乐(及 CP 的角色来源)投票列表改从后端拉,新建通用数据加载封装。

---

## File Map

| 文件 | 操作 |
|---|---|
| `packages/vote/src/common/lib/voteObjectsDataSource.ts` | 新建(通用投票对象数据源) |
| `packages/vote/src/vote-character/lib/*` | 列表来源改后端 |
| `packages/vote/src/vote-music/lib/*` | 同上 |
| `packages/vote/src/vote-couple/lib/*` | 角色来源切后端 |

---

## Task 1: 通用投票对象数据源

**File:** Create `packages/vote/src/common/lib/voteObjectsDataSource.ts`

- [ ] **Step 1:** 新建 `fetchVoteObjects(category: 'characters'|'music', voteYear) → groups`,调 `GET /vote-objects/{category}?vote_year=`。
- [ ] **Step 2:** 类型对齐后端返回 `{vote_year, groups:[{group, items:[...]}]}`(items 字段随 category 不同:角色 origin/first_appearance,音乐 album)。
- [ ] **Step 3:** commit `feat(vote): vote-objects data source`

---

## Task 2: 角色投票页改从后端拉

**Files:** `packages/vote/src/vote-character/lib/*`, `VoteCharacter.vue`

- [ ] **Step 1:** Read 现有 `vote-character/lib/characterList.ts`(import 自 `shared/data/character`)与分组逻辑。
- [ ] **Step 2:** 列表来源换成 `fetchVoteObjects('characters', voteYear)`;后端已按首登作品分组,移除前端分组逻辑(或改为消费后端 groups)。
- [ ] **Step 3:** 选择/本命/理由/提交不变。
- [ ] **Step 4:** commit `feat(vote): character ballot list from backend`

---

## Task 3: 音乐投票页改从后端拉

**Files:** `packages/vote/src/vote-music/lib/*`, `VoteMusic.vue`

- [ ] **Step 1:** 同 Task 2,列表来源换成 `fetchVoteObjects('music', voteYear)`(后端按专辑分组)。
- [ ] **Step 2:** commit `feat(vote): music ballot list from backend`

---

## Task 4: CP 页角色来源切后端

**Files:** `packages/vote/src/vote-couple/lib/*`

- [ ] **Step 1:** CP 由角色组合;把角色来源从 `shared/data/character` 切到 `fetchVoteObjects('characters', ...)`。CP 组合逻辑不变。
- [ ] **Step 2:** commit `feat(vote): couple page character source from backend`

---

## 手工验收清单
- [ ] 角色页:从后端拉到按首登作品分组的列表,渲染与切换前一致
- [ ] 音乐页:按专辑分组正确
- [ ] 合并生效:重名角色/同曲名不同专辑在列表只出现规范化主候选
- [ ] CP 页角色来源正常,组合逻辑不受影响
- [ ] 回归:提交/本命/理由/结果页不受影响

---

## 依赖
- 后端 `/vote-objects/characters|music` 先合并;字段以后端返回为准。

## 关联
- 后端 plan：`2026-06-08-vote-objects-backend.md`
