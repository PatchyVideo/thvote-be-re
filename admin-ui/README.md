# THVote 管理台前端 (Vue 3 + Vite + TypeScript)

B-049 Plan 2：把旧的 `src/admin_ui/index.html`（1115 行单文件）拆成模块化 Vue 应用。

## 构建方式：commit-dist（重要）

产物**提交进仓库**（输出到 `src/admin_ui/`），由后端 StaticFiles 服务、随 `COPY src/` 进镜像 —— **部署管线零改动**。

⚠️ **改完前端源码,必须本地重新构建再提交**（否则线上 dist 与源码漂移）：

```bash
cd admin-ui
pnpm install          # 首次
pnpm build            # vue-tsc 类型检查 + vite build → ../src/admin_ui/
# 提交:admin-ui/(源码) + src/admin_ui/(构建产物)
```

本地开发热更新：`pnpm dev`（Vite dev server；API 需另配代理到后端，或直接部署到测试机验收）。

## 结构

- `src/api/` —— 唯一网络层：`client.ts`（fetch 封装：`/api/v1` 前缀、`X-Admin-Secret`、403→登出、裸 `/admin/reload-config`）+ 类型化端点模块（`admin.ts`/`monitor.ts`）+ `types.ts`（后端契约镜像）。
- `src/composables/` —— `useAuth`/`useToast`/`useAsync`/`usePagination`。
- `src/components/` —— 共享组件：`DataTable`（分页表格）/`Modal`/`Toast`/`FilterBar`/`StatCard`/`AppShell`/`LoginOverlay`。
- `src/views/` —— 一页一文件（`DashboardView`/`UsersView`/`monitor/*`）。

新增页面 = 1 个 view + 1 条路由（`router.ts`）+ 若干 `api/*.ts` 方法。

## 服务路径

- **`/admin-ui`** —— 新 Vue 管理台（需管理密钥登录）。
- **`/admin-ui-legacy`** —— 旧单文件面板，作迁移期兜底：尚未迁到 Vue 的工具（候选项/数据同步/提名审核/问卷嵌套编辑器/审计日志/导出）仍在这里用。新台顶栏有"更多工具(旧版)"入口指向它。

## Phase 1 已含

仪表盘 + 5 个安全监控页（流量概览 / IP·设备聚类 / 可疑名单 / 投票浏览器+作废恢复 / 账号钻取+人工复核）+ 用户（搜索/封解封，作为模块化打样）。

其余 7 个旧工具后续增量迁移；全部迁完后删除 `src/admin_ui_legacy/` 与本兜底入口。
