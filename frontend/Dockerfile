# ============================================================
# THVote Frontend - 多阶段构建 Dockerfile
#
# 功能：
# 1. 构建投票页面 (packages/vote)
# 2. 构建结果页面 (packages/result)
# 3. 构建导航页 (packages/navigator)
# 4. 合并部署到同一个 Nginx 容器
# ============================================================

# ---- 基础阶段：Node.js 环境 ----
FROM node:20-alpine AS base

# 安装 pnpm
RUN corepack enable && corepack prepare pnpm@8.15.4 --activate

# ---- 克隆阶段 ----
FROM base AS cloner

# 克隆前端仓库
ARG FRONTEND_REPO=https://github.com/PatchyVideo/Touhou-Vote.git
ARG FRONTEND_BRANCH=dev

RUN apk add --no-cache git && \
    git clone --depth 1 --branch $FRONTEND_BRANCH $FRONTEND_REPO /tmp/frontend

# ---- 安装依赖阶段 ----
FROM base AS deps

COPY --from=cloner /tmp/frontend /app
WORKDIR /app
RUN pnpm install --no-frozen-lockfile

# ---- 构建 vote 页面 ----
FROM deps AS builder-vote

WORKDIR /app/packages/vote
RUN pnpm codegen && pnpm build

# ---- 构建 result 页面 ----
FROM deps AS builder-result

WORKDIR /app/packages/result
RUN pnpm codegen && pnpm build

# ---- 构建 navigator 页面 ----
FROM deps AS builder-navigator

WORKDIR /app/packages/navigator
RUN pnpm build

# ---- 最终阶段：Nginx + 静态文件 ----
FROM nginx:alpine AS production

# 复制 vote 页面（主页面）
COPY --from=builder-vote /app/packages/vote/dist /usr/share/nginx/html

# 复制 result 页面
COPY --from=builder-result /app/packages/result/dist /usr/share/nginx/html/result

# 复制 navigator 页面
COPY --from=builder-navigator /app/packages/navigator/dist /usr/share/nginx/html/navigator

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost/ || exit 1

# 默认端口
EXPOSE 80 443

# 默认启动命令
CMD ["nginx", "-g", "daemon off;"]
