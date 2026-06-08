# API 版本升级（v11→v12）& Nginx 路由修复 Design

> 创建日期: 2026-06-09  
> 最后更新: 2026-06-09  
> 根因: `thvote-vote` 容器内 nginx 将 `/v11-be/*` 全量反代到 `thvote-backend:8000/`（无 `/api/v1/` 前缀），导致新增端点 404。同时接口版本号应跟随当前年份升到 v12。

---

## 诊断结论

### 问题链路

```
浏览器 → thvote-vote:8082 (nginx) → thvote-backend:8000 (Python)
```

当前 nginx：`proxy_pass http://thvote-backend:8000/` —— 不带路径，nginx 自动丢弃 `/v11-be/` 前缀。

| 前端请求 | nginx 转发到 | 正确目标 | 状态 |
|---|---|---|---|
| `/v11-be/graphql` | `/graphql` | `/graphql` | 200 ✅ 巧合正确 |
| `/v11-be/user-token-status` | `/user-token-status` | `/user-token-status` | 405 (仅 POST) |
| `/v11-be/vote-objects/characters` | `/vote-objects/characters` | `/api/v1/vote-objects/characters` | 404 ❌ |
| `/v11-be/vote-objects/music` | `/vote-objects/music` | `/api/v1/vote-objects/music` | 404 ❌ |
| `/v11-be/questionnaire/structure` | `/questionnaire/structure` | `/api/v1/questionnaire/structure` | 404 ❌ |
| `/v11-be/doujin/api` | `/doujin/api` | `/api/v1/submit/dojin` | 404 ❌ |

### 前端 v11 来源

5 个文件内硬编码了字符串 `'/v11-be/'`，无变量配置，与 `voteYear` 无关联。

---

## 方案

### 后端：nginx location 拆分为精确匹配 + 兜底

- 文件: `D:\personal\thvote-fe\Dockerfile.vote.template`
- nginx 配置从 1 个 `location /v11-be/` 拆为 4 个 `location` 块
- 精确匹配的走 `/api/v1/`，兜底保持不变
- 版本号升到 v12

### 前端：集中常量 + polyfill 删除

- 新建 `packages/vote/src/common/lib/apiPrefix.ts`，导出 `API_PREFIX = '/v12-be'`
- 5 个文件改为引用该常量
- 删除 `index.html` 的 polyfill.io 引用

### 需要验证的端点

- [ ] `/v12-be/vote-objects/characters?vote_year=12` → 200
- [ ] `/v12-be/vote-objects/music?vote_year=12` → 200
- [ ] `/v12-be/questionnaire/structure` → 200
- [ ] `/v12-be/graphql` → 200 (兜底路径)
- [ ] `/v12-be/user-token-status` → POST 200
- [ ] `/v12-be/doujin/api` → 确认正确路径

---

## 涉及文件

### 后端仓库 (thvote-be): 0 个文件
nginx 配置在 thvote-fe 的 Dockerfile 内，Python 代码无改动。

### 前端仓库 (thvote-fe): 8 个文件

| 操作 | 文件 | 说明 |
|---|---|---|
| 修改 | `Dockerfile.vote.template` | nginx location 拆分 + v12 |
| 新建 | `packages/vote/src/common/lib/apiPrefix.ts` | `API_PREFIX = '/v12-be'` |
| 修改 | `packages/vote/src/graphql/index.ts` | 引用 `API_PREFIX` |
| 修改 | `packages/vote/src/common/lib/voteObjectsDataSource.ts` | 同上 |
| 修改 | `packages/vote/src/vote-doujin/components/EditDoujin.vue` | 同上 |
| 修改 | `packages/vote/src/home/lib/user.ts` | 同上 |
| 修改 | `packages/vote/src/questionnaire/lib/questionnaireStateV2.ts` | 同上 |
| 修改 | `packages/vote/index.html` | 删除 polyfill.io |

---

## 关联

- 前置: B-039 问卷结构化、B-040 投票对象后端已完成
- 后续: 前端 B-041 问卷适配 plan
