# 前端 API 版本升级 v11→v12 & polyfill 移除 Implementation Plan

> **For agentic workers:** 前端 Vue 3 monorepo，仓库 `D:\personal\thvote-fe`。**前置条件：** 后端 nginx 已升级到 v12（见 `2026-06-09-nginx-routing-fix.md`），否则前端升到 v12 后全部 404。

**Goal:** 将前端 5 个文件中硬编码的 `'/v11-be/'` 替换为集中常量 `API_PREFIX = '/v12-be'`，删除已死亡的 polyfill.io 引用。

**Architecture:** 新建 `apiPrefix.ts` 导出常量，其余文件 import 使用。这是纯重构（行为不变，只是消除硬编码）。

**Tech Stack:** TypeScript, Vue 3, pnpm

---

## File Map

| 操作 | 文件 | 行号 |
|---|---|---|
| 新建 | `packages/vote/src/common/lib/apiPrefix.ts` | — |
| 修改 | `packages/vote/src/graphql/index.ts` | 36 |
| 修改 | `packages/vote/src/common/lib/voteObjectsDataSource.ts` | 31-32 |
| 修改 | `packages/vote/src/vote-doujin/components/EditDoujin.vue` | 294 |
| 修改 | `packages/vote/src/home/lib/user.ts` | 160 |
| 修改 | `packages/vote/src/questionnaire/lib/questionnaireStateV2.ts` | 21 |
| 修改 | `packages/vote/index.html` | 13 |

---

### Task 1: 新建集中常量

**Files:**
- 创建: `packages/vote/src/common/lib/apiPrefix.ts`

- [ ] **Step 1: 创建文件**

```typescript
/** API 版本前缀。后端 nginx 据此路由到正确的 Python 端点。 */
export const API_PREFIX = '/v12-be'
```

- [ ] **Step 2: 验证文件位置**

确认路径 `packages/vote/src/common/lib/apiPrefix.ts` 与 tsconfig 的路径别名 `@/common/lib/` 兼容（`@` → `src/`）。

- [ ] **Step 3: Commit**

```bash
git add packages/vote/src/common/lib/apiPrefix.ts
git commit -m "feat(api): add centralized API_PREFIX constant (/v12-be)"
```

---

### Task 2: 替换 5 个硬编码引用

- [ ] **Step 1: `graphql/index.ts`**

第 36 行：
```typescript
// 旧
uri: '/v11-be/graphql',
// 新
import { API_PREFIX } from '@/common/lib/apiPrefix'
// ...
uri: `${API_PREFIX}/graphql`,
```

- [ ] **Step 2: `voteObjectsDataSource.ts`**

第 31-32 行：
```typescript
// 旧
const CHARACTER_URL = `/v11-be/vote-objects/characters?vote_year=${voteYear}`
const MUSIC_URL = `/v11-be/vote-objects/music?vote_year=${voteYear}`
// 新
import { API_PREFIX } from '@/common/lib/apiPrefix'
// ...
const CHARACTER_URL = `${API_PREFIX}/vote-objects/characters?vote_year=${voteYear}`
const MUSIC_URL = `${API_PREFIX}/vote-objects/music?vote_year=${voteYear}`
```

- [ ] **Step 3: `EditDoujin.vue`**

第 294 行：
```typescript
// 旧
await fetch('/v11-be/doujin/api', {
// 新
import { API_PREFIX } from '@/common/lib/apiPrefix'
// ...
await fetch(`${API_PREFIX}/doujin/api`, {
```

- [ ] **Step 4: `user.ts`**

第 160 行：
```typescript
// 旧
await fetch('/v11-be/user-token-status', {
// 新
import { API_PREFIX } from '@/common/lib/apiPrefix'
// ...
await fetch(`${API_PREFIX}/user-token-status`, {
```

- [ ] **Step 5: `questionnaireStateV2.ts`**

第 21 行：
```typescript
// 旧
const STRUCTURE_URL = '/v11-be/questionnaire/structure'
// 新
import { API_PREFIX } from '@/common/lib/apiPrefix'
// ...
const STRUCTURE_URL = `${API_PREFIX}/questionnaire/structure`
```

- [ ] **Step 6: Commit**

```bash
git add packages/vote/src/graphql/index.ts \
        packages/vote/src/common/lib/voteObjectsDataSource.ts \
        packages/vote/src/vote-doujin/components/EditDoujin.vue \
        packages/vote/src/home/lib/user.ts \
        packages/vote/src/questionnaire/lib/questionnaireStateV2.ts
git commit -m "refactor(api): replace hardcoded /v11-be/ with centralized API_PREFIX

New API_PREFIX constant at @/common/lib/apiPrefix.
No behavior change — just eliminating magic strings.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: 删除 polyfill.io

**Files:**
- 修改: `packages/vote/index.html:13`

- [ ] **Step 1: 删除 polyfill 引用**

第 13 行，删除：
```html
    <script
      src="https://polyfill.io/v3/polyfill.min.js?features=es2018%2Ces2019%2Ces2020"
    ></script>
```

- [ ] **Step 2: Commit**

```bash
git add packages/vote/index.html
git commit -m "chore: remove dead polyfill.io CDN reference

Polyfill.io was acquired and compromised in 2024; all modern
browsers natively support ES2018-ES2020. The domain now returns
401 on every page load.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: 构建验证

- [ ] **Step 1: 本地构建前端**

```bash
cd D:\personal\thvote-fe
pnpm install
pnpm --filter @touhou-vote/vote run build -- --mode test
```

- [ ] **Step 2: 检查构建产物**

确认 `packages/vote/dist/` 生成且无 TypeScript 编译错误。

- [ ] **Step 3: 全局搜索残留 v11**

```bash
cd D:\personal\thvote-fe
grep -r "v11-be" packages/vote/src/ --include='*.ts' --include='*.vue' --include='*.html'
```

**预期输出:** 空（无残留）。

---

## 手工验收清单
- [ ] `grep -r "v11-be" packages/vote/src/` 无结果
- [ ] `grep -r "polyfill.io" packages/vote/` 无结果
- [ ] `pnpm build` 成功，无 TS 错误
- [ ] 部署后浏览器控制台无 polyfill 401 报错
- [ ] 前端能正常加载问卷结构、投票对象、GraphQL

---

## 依赖与顺序
- **前置：** Nginx 路由修复 plan (`2026-06-09-nginx-routing-fix.md`) 必须先部署
- 本 plan 内 Task 2 依赖 Task 1（常量文件先存在）
- Task 3（polyfill）可独立并行
