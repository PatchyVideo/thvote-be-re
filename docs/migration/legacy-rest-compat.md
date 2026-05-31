# Legacy REST 兼容层（旧 Rust gateway 扁平契约）

> 迁移主题文档，按 CLAUDE.md §3 维护：写现状与约束，不只写理想方案。
> 创建：2026-05-31

## 背景 / 为什么存在

前端（`Touhou-Vote`）是**与仍在线的 Rust 部署（vote.thwiki.cc）共享的同一份产物**。它通过 nginx 把
`/v11-be/` 代理到后端**根路径**（`Dockerfile.vote.template`：`location /v11-be/ { proxy_pass http://thvote-backend:8000/; }`）。

旧 Rust gateway 暴露的是**扁平**路由（如 `/user-token-status`），而 Python 重写把 REST 收敛到了
`/api/v1/...`（`src/api/rest/v1/__init__.py` prefix=`/api/v1`）。于是前端打 `/v11-be/user-token-status`
→ 后端 `/user-token-status` → **404**。

### 具体症状（2026-05-31 实测）
登录本身走 GraphQL（`/v11-be/graphql`）是通的；但登录成功后前端 `location.reload()`，bootstrap 阶段
`checkLoginStatus()`（`packages/vote/src/home/lib/user.ts`）会 `POST /v11-be/user-token-status`：
- 404 → `res.status !== 'valid'` → `deleteUserData()` → **闪一下投票页又被弹回登录页**。

即「契约漂移」而非配置问题：路径（扁平 vs `/api/v1` 嵌套）+ 响应 shape（Python 原 `token_status` 返回空体，
前端要 `{status:"valid", voting_status, papers_json}`）双双不一致。

## 方案：后端 legacy-compat 路由（A 方案）

让 Python 后端去对齐**已存在的外部契约**，而不是改前端（会把前端劈成两份）或改 nginx（责任摊到两层）。

| 维度 | 内容 |
|---|---|
| 新增位置 | `src/api/rest/legacy/`（`__init__.py` + `router.py`） |
| 挂载 | `src/main.py` `app.include_router(legacy_router)`，**无 prefix**（根路径，与 `/api/v1` 并列） |
| 端点 | `POST /user-token-status` |
| 响应 shape | `{status: "valid"|"invalid", voting_status: VotingStatus|null, papers_json: str|null}`，**HTTP 恒 200**（失效靠 body 的 `status` 表达，不用状态码） |
| 旧实现对应 | `thvote-be/gateway/src/main.rs::user_token_status`（55-91 行） |

### 行为映射（与 Rust 一致）
- `user_token` 解码失败 → `{"status":"invalid"}`（HTTP 200，**不抛 401**——抛了前端就把所有人登出）。
- `user_token` 有效 → `status:"valid"`；若带可解码的 `vote_token`：
  - `voting_status = SubmitService.get_voting_status(vote_token.user_id)`（Python 以 user_id 作 vote_id，见 `VoteTokenPayload`）。
  - 若 `voting_status.papers` 为真 → 附 `papers_json = get_paper_submit(...).papers_json`。
- `vote_token` 缺失/失效（如投票窗口外）→ 仍 `valid`，只是无 `voting_status` 可回填。
- **JWT 配置错误**（`JWTConfigurationError`，密钥未配）**不吞**，照常 500——它是服务端故障，不能伪装成「token 无效」把所有人静默登出。

## 现状

- ✅ 已实现 + 单测（`tests/unit/test_legacy_token_status.py`，6 例覆盖 invalid / valid 无 vote_token / valid 无效 vote_token / 有 voting_status 无 papers / 有 papers / 把 vote_token 误放 user_token 槽被拒）。
- ⏳ 部署后需在 `:8082/v11/` 实测：登录后停在投票页、刷新不再弹回登录。

## 未覆盖 / 已知缺口

- `/v11-be/doujin/api`（前端另一处 `/v11-be/` 调用）大概率同样 404——本次**未处理**，留待同主题补。
- 旧 gateway 的 `/server-time` 也未移植（见 BACKLOG「模块功能缺口」）。

## 风险 / 回滚

- 风险低：纯新增，不改 `/api/v1` 与 GraphQL 现有路由；旧 `POST /api/v1/user/token-status`（返回空体）保留不动。
- 回滚：删 `app.include_router(legacy_router)` 一行即恢复原状（端点消失，回到 404）。

## 移除条件（BACKLOG B-033 / CLAUDE.md §5）

同时满足才删整个 `src/api/rest/legacy/`：
1. Rust gateway 下线，无任何部署再依赖扁平契约；且
2. 前端 REST 调用迁移到原生 `/api/v1/...` + 新响应 shape（即「终态 B」）。

宜与 **B-019**（错误响应 `{"detail"}` ↔ Rust `{"error","service"}` 统一）一并收敛。
