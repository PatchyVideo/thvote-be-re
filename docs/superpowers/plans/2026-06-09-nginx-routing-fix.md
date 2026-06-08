# Nginx 路由修复 & API 版本升级 Implementation Plan

> **For agentic workers:** 本 plan 为 Docker/nginx 配置改动。改完后需重新构建 `thvote-vote` 镜像并部署。

**Goal:** 修复 `thvote-vote` 容器内 nginx 将所有 `/v11-be/*` 请求反代到 Python 后端根路径（缺 `/api/v1/` 前缀）导致新增端点 404 的问题，同时版本号升到 v12。

**Architecture:** 在 `Dockerfile.vote.template` 的内联 nginx 配置中，将单一 `location /v11-be/` 拆为 4 个 location 块——3 个精确前缀块加 `/api/v1/` 后转发 Python 后端，1 个兜底块保持不变。

**Tech Stack:** nginx (alpine), Dockerfile heredoc

---

### Task 1: 拆分 nginx location + 升级 v12

**Files:**
- 修改: `D:\personal\thvote-fe\Dockerfile.vote.template:45-59`

- [ ] **Step 1: 修改 nginx 内联配置**

将当前第 45-59 行：
```dockerfile
RUN echo 'server { \
    listen 8082; \
    location / { \
        root /usr/share/nginx/html; \
        try_files $uri /index.html; \
    } \
    location /v11-be/ { \
        proxy_pass http://thvote-backend:8000/; \
        proxy_http_version 1.1; \
        proxy_set_header Host $host; \
        proxy_set_header X-Real-IP $remote_addr; \
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; \
        proxy_set_header X-Forwarded-Proto $scheme; \
    } \
}' > /etc/nginx/conf.d/default.conf
```

改为：
```dockerfile
RUN echo 'server { \
    listen 8082; \
    location / { \
        root /usr/share/nginx/html; \
        try_files $uri /index.html; \
    } \
    location /v12-be/vote-objects/ { \
        proxy_pass http://thvote-backend:8000/api/v1/vote-objects/; \
        proxy_http_version 1.1; \
        proxy_set_header Host $host; \
        proxy_set_header X-Real-IP $remote_addr; \
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; \
        proxy_set_header X-Forwarded-Proto $scheme; \
    } \
    location /v12-be/questionnaire/ { \
        proxy_pass http://thvote-backend:8000/api/v1/questionnaire/; \
        proxy_http_version 1.1; \
        proxy_set_header Host $host; \
        proxy_set_header X-Real-IP $remote_addr; \
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; \
        proxy_set_header X-Forwarded-Proto $scheme; \
    } \
    location /v12-be/doujin/ { \
        proxy_pass http://thvote-backend:8000/api/v1/submit/dojin; \
        proxy_http_version 1.1; \
        proxy_set_header Host $host; \
        proxy_set_header X-Real-IP $remote_addr; \
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; \
        proxy_set_header X-Forwarded-Proto $scheme; \
    } \
    location /v12-be/ { \
        proxy_pass http://thvote-backend:8000/; \
        proxy_http_version 1.1; \
        proxy_set_header Host $host; \
        proxy_set_header X-Real-IP $remote_addr; \
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; \
        proxy_set_header X-Forwarded-Proto $scheme; \
    } \
}' > /etc/nginx/conf.d/default.conf
```

**关键点：**
- 精确匹配块在前面，nginx 优先匹配最长前缀
- `/v12-be/vote-objects/` 转发到 `/api/v1/vote-objects/`（需带尾斜杠以保持路径）
- `/v12-be/questionnaire/` 转发到 `/api/v1/questionnaire/`
- `/v12-be/doujin/` 转发到 `/api/v1/submit/dojin`（不带尾斜杠，因为前端路径是 `/doujin/api`）
- 兜底 `/v12-be/` 不变，继续处理 graphql、user-token-status 等根路径端点
- 版本号 v11 → v12

- [ ] **Step 2: 手工语法检查**

打开 `Dockerfile.vote.template`，确认：
- `proxy_pass` 的 upstream 地址 `thvote-backend` 能找到（docker-compose 里容器名叫 `thvote-backend`）
- 所有 `{` `}` 配对正确
- `$` 符号在 heredoc 中不会被 shell 解释（此模板由 CI 用 `cat` 方式传入，无变量替换风险）

- [ ] **Step 3: Commit**

```bash
git add Dockerfile.vote.template
git commit -m "fix(nginx): split /v12-be/ proxy with /api/v1/ prefix for new endpoints

vote-objects, questionnaire, doujin endpoints need /api/v1/ prefix
on the Python backend. Add precise location blocks before the
catch-all so exact prefixes get the right target path.

Also upgrade API version prefix from v11 to v12.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### 手工验收清单（部署后）

- [ ] `curl http://154.37.215.62:18000/api/v1/vote-objects/characters?vote_year=12` → 200
- [ ] `curl http://154.37.215.62:8082/v12-be/vote-objects/characters?vote_year=12` → 200（经 nginx 反代）
- [ ] `curl http://154.37.215.62:8082/v12-be/questionnaire/structure` → 200
- [ ] `curl http://154.37.215.62:8082/v12-be/graphql -X POST -H 'Content-Type: application/json' -d '{"query":"{ __typename }"}'` → 200
- [ ] `curl http://154.37.215.62:8082/v12-be/user-token-status -X POST -H 'Content-Type: application/json' -d '{"token":"x"}'` → 非 404

---

### 依赖与顺序
- 本 plan **独立于**前端 API_PREFIX plan —— nginx 先改可以先部署，前端后续改 URL 也进入 v12
- 部署后前端仍用 v11 → 全部 404（旧路径不再匹配），**必须**前端同步升级 v12
