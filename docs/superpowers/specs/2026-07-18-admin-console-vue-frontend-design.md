# 管理后台 Vue 前端重写设计（B-049 Plan 2）

> 创建日期：2026-07-18
> 最后更新：2026-07-18（初稿）
>
> 关联：后端设计 [admin-console-vue-security-monitoring-design](./2026-07-17-admin-console-vue-security-monitoring-design.md) §八（前端总纲）；后端 Plan 1 已实现并上线（监控 API + 处置动作 + fail-closed 鉴权，PR #15/#16）。本文是**前端（Plan 2）**的落地设计。

## 一、目标与动机

现有管理后台是**单文件 `src/admin_ui/index.html`（1115 行 HTML+JS）**，每个子页面各自内联实现表格、弹窗、fetch、错误处理——难维护、难扩展、无法承载 B-049 新增的安全监控页。

**本次重写的首要目的：拆掉这个巨大 HTML，让管理端模块化、可扩展。** 其次才是补齐监控 UI。判据：

- 加/改一个页面 = 新增一个 view + 一条路由 + 一个类型化 api 调用，复用共享组件；不再复制粘贴表格/弹窗。
- 契约（路径/字段/响应形状）集中在一层类型化 api client，改一处即全站生效（把刚做完的 UI↔API 对齐固化下来）。
- 新监控页与旧工具用同一套骨架，风格统一。

## 二、已定决策（本设计的前提）

| 决策 | 选择 | 理由 |
|---|---|---|
| 构建与交付 | **本地 `pnpm build` → 提交产物 dist** 到 `src/admin_ui/`，StaticFiles 服务，`COPY src/` 进镜像 | 与现状（提交静态文件）一致，**部署管线零改动**，最轻量、迭代最快。代价：git 里含编译产物。 |
| 语言 | **TypeScript** | 模块化/可扩展/可维护优先，编译期抓契约漂移，与类型化 Python 后端对称。 |
| 框架 | Vue 3 `<script setup>` + Vite | 设计 §八已定；SFC + composable 天然模块化。 |
| 路由 | **vue-router hash 模式** | 纯静态文件服务，hash 路由无需服务端 rewrite/SPA fallback。 |
| 状态 | **无 Pinia**，composable 管共享状态 | 内部小工具，轻量。 |
| 迁移策略 | **渐进 + 旧版兜底** | 旧面板移到 `/admin-ui-legacy` 保活，直到 Vue 达到功能对等再删。 |
| Phase 1 范围 | 骨架 + 鉴权壳 + 共享组件 + api 层 + Dashboard + **全部 5 个监控页** + **Users（打样）** | 快速兑现"模块化骨架 + 新监控价值"；其余 7 个工具后续增量迁移。 |

本设计的其他部分（架构/布局/接口）在这些决策下展开。

## 三、总体架构

### 3.1 目录结构

Vue 源码放仓库根的 `admin-ui/`（**不进 Python `src/` 包**）；Vite 产物输出到 `src/admin_ui/`（被 StaticFiles 服务、`COPY src/` 进镜像）。

```
admin-ui/
  index.html                 Vite 入口
  package.json               vue/vue-router/vite/typescript/@vitejs/plugin-vue/vue-tsc
  tsconfig.json
  vite.config.ts             base:'./'  build.outDir:'../src/admin_ui'  emptyOutDir:true
  src/
    main.ts                  createApp + router 挂载
    App.vue                  外壳:登录覆盖层 / 已登录则 AppShell + <router-view>
    router.ts                hash 路由表 + 鉴权守卫
    api/
      client.ts              唯一 fetch 封装:base /api/v1、X-Admin-Secret、403→登出、
                             错误抛出;裸端点 reloadConfig() 走 /admin/reload-config
      admin.ts               users/stats/(后续 candidates/sync/nominations/logs/export)
      monitor.ts             overview/groups/members/suspects/votes/account/actions
      types.ts               请求/响应类型(镜像后端 schema)
    composables/
      useAuth.ts             secret(sessionStorage)、login/logout、isAuthed
      useToast.ts            全局 toast
      usePagination.ts       page/pageSize/total + 翻页
      useAsync.ts            {data,loading,error,run} 包一次异步调用
    components/
      AppShell.vue           顶栏导航 + 内容槽;含"更多工具(旧版)"→/admin-ui-legacy
      DataTable.vue          列配置 + 行 + loading/empty + 分页(替换全站散落表格)
      Modal.vue / ConfirmDialog.vue / Toast.vue / FilterBar.vue / StatCard.vue
    views/
      LoginView.vue          (或 App 内覆盖层)
      DashboardView.vue      stats + 快捷动作(compute/finalize/reload-config)
      UsersView.vue          搜索 + 封/解封(打样:证明"view+共享组件+api"模式)
      monitor/
        OverviewView.vue     概览:类别总数/去重 IP·设备/按天提交
        ClustersView.vue     IP/设备聚类 + 点开看组成员
        SuspectsView.vue     可疑名单(分页,命中原因)
        VotesView.vue        可过滤分页投票浏览器 + 作废/恢复动作
        AccountView.vue      单账号钻取 + 人工复核(review)动作
```

### 3.2 模块边界与"拆巨大 HTML"的兑现

- **api client（一层）**：所有网络调用只经 `api/client.ts` 的 `request()`。它统一：`/api/v1` 前缀、`X-Admin-Secret` 头、403→登出、`!ok`→带 `detail` 抛错。**裸 ops 端点例外**（`/admin/reload-config` 不带 `/api/v1`，用专门方法）。契约集中此处，是刚做完的对齐修复的长期落点。
- **共享组件（一套）**：`DataTable`（列配置驱动 + 分页 + 空/载入态）取代旧版每个 tab 手写的表格；`Modal/ConfirmDialog/Toast/FilterBar` 取代内联弹窗与提示。子页面只组合它们。
- **view（一页一文件）**：每个 view 自包含，注入共享组件 + 类型化 api。互不引用内部实现。
- **composable（跨页状态）**：鉴权、分页、toast、异步态收敛为可复用 hook。

新增页面的成本 = 1 view + 1 路由 + 若干 `api/*.ts` 方法；这就是"可扩展"。

### 3.3 鉴权与外壳

- 未登录：App 显示登录覆盖层，输入 secret → `useAuth.login()` 用 `GET /api/v1/admin/stats` 带头探测，200 则存 `sessionStorage['adminSecret']` 并进入。
- 已登录：AppShell 顶栏 + `<router-view>`；路由守卫无 secret 一律跳登录。
- `api/client` 收到 403 → 清 secret + 回登录（与旧版 `doLogout` 行为一致，组件化）。
- **IP 白名单**：纯后端 `require_admin` 事;前端无需处理,被挡即 403→登出(可在登录页提示"IP 不在白名单")。

### 3.4 构建与服务集成

- `vite.config.ts`：`base:'./'`（相对资源路径,适配 `/admin-ui` 挂载）、`build.outDir:'../src/admin_ui'`、`emptyOutDir:true`。产物：`src/admin_ui/index.html` + `src/admin_ui/assets/*`。
- **main.py StaticFiles 调整**：
  - 旧面板 `src/admin_ui/index.html` → 移到 **`src/admin_ui_legacy/index.html`**，挂 **`/admin-ui-legacy`**（兜底,html=True）。
  - `src/admin_ui`（现为 Vite 产物）继续挂 **`/admin-ui`**（html=True）。
- hash 路由 + `base:'./'` → 资源与路由都在 `/admin-ui/` 下,StaticFiles 直接服务,无需 SPA fallback。
- **部署管线不变**：`COPY src/` 同时带上 `src/admin_ui`(新)与 `src/admin_ui_legacy`(旧)。开发者改前端后本地 `pnpm build` 再提交。

### 3.5 迁移期共存

Phase 1 上线后：`/admin-ui` = 新 Vue（Dashboard + 监控 + Users），`/admin-ui-legacy` = 旧全量面板。AppShell 顶栏放一个"更多工具(旧版)"入口指向 legacy，让尚未迁移的 7 个工具（候选/同步/提名/问卷编辑器/日志/导出）仍可用。逐个迁移完成后从 legacy 撤下，最终删除 legacy。

## 四、Phase 1 交付清单

1. `admin-ui/` 脚手架（Vite+Vue+TS）+ `vite.config.ts` 输出到 `src/admin_ui/` + `pnpm build` 跑通。
2. main.py：legacy 面板迁到 `/admin-ui-legacy`，`/admin-ui` 服务 Vite 产物。
3. api client + `useAuth` + 登录壳 + 路由守卫 + AppShell 顶栏。
4. 共享组件：DataTable / Modal / ConfirmDialog / Toast / FilterBar / StatCard。
5. DashboardView（stats + compute/finalize/reload-config，reload-config 走裸路径）。
6. 5 个监控 view（overview / clusters+members / suspects / votes+作废恢复 / account+review）。
7. UsersView（搜索 + 封/解封）——打样。
8. 提交 dist；文档 + CHANGELOG。

**后续增量（不在 Phase 1）**：CandidatesView（含合并/导入）、SyncView、NominationsView、QuestionnaireView（4 层嵌套编辑器,最复杂）、LogsView、ExportView；迁完删 legacy。以及几个当前无 UI 的端点顺带补上（用户详情钻取 `GET /admin/users/{id}`、建合并 `merge-into`、ranking preview）。

## 五、错误处理与显示

- `request()` 对 `!ok` 抛 `{status, detail}`；view 用 `useAsync` 捕获 → toast `detail`。杜绝旧版"500 仍提示已保存"的假成功（对齐修复的经验固化）。
- 空态/载入态由 DataTable 统一渲染。
- 破坏性动作（封号/作废/删除）走 `ConfirmDialog` 二次确认。
- 处置动作（作废/复核）成功后提示携带后端返回的 B-050 说明（"已记录;影响排名需 B-050 落地后生效"），不误导。

## 六、测试策略

内部工具，遵循后端设计 §九"前端轻量"：

- **硬门禁**：`pnpm build`（含 `vue-tsc` 类型检查）必须通过——提交 dist 前本地跑，等价于类型 + 构建冒烟。
- **可选轻测**：`vitest` 给 `api/client`（前缀/头/403/裸路径分支）与关键 composable 各一两个单测；不铺 UI 端到端。
- **人工验收**：部署到测试机后按 view 手测（登录、监控各页、Users、Dashboard 动作）。
- 不改动现有 Python 测试（后端已覆盖）。

## 七、风险与开放项

- **dist 与源码漂移**：提交 dist 有"改了源忘了 rebuild"的风险。缓解：Plan 每次以"`pnpm build` 后提交"为固定步骤；**可选** follow-up 在 CI 加 `pnpm build && git diff --exit-status src/admin_ui` 守卫（但会把 node 引入管线,与"零管线改动"取舍,暂不做）。
- **首屏体积**：Vite 默认分包足够;内部工具不做激进优化。
- **legacy 保活期**：两套面板并存期间,任何后端契约变更要同时顾及（legacy 用旧 fetch）。迁移越快越好以缩短并存窗口。
- **无头环境**：本机可 `pnpm build` 但不便开浏览器验收;验收在测试机部署后做（与后端一致）。
- **questionnaire 编辑器**（后续）：4 层嵌套 CRUD 是最复杂 view,迁移时单独细化,注意刚修的 `order` 字段与嵌套契约。

## 八、非目标

- 不做视觉/交互重设计——功能与信息架构对齐旧版 + 补监控;先模块化,不追求 UI 焕新。
- 不引入 Pinia / SSR / i18n / 组件库（保持轻量;将来需要再加,架构已可扩展）。
- 不在本阶段迁移全部旧工具（见 §四后续增量）。
