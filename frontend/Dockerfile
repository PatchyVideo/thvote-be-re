# ============================================================
# THVote Frontend - 多阶段构建 Dockerfile
#
# 功能：
# 1. 构建投票页面 (packages/vote)
# 2. 构建结果页面 (packages/result)
# 3. 可选构建导航页 (packages/navigator)
# ============================================================

# ---- 基础阶段：Node.js 环境 ----
FROM node:20-alpine AS base

# 安装 pnpm
RUN corepack enable && corepack prepare pnpm@9.3.0 --activate

# ---- 构建阶段：所有包 ----
FROM base AS builder

# 克隆前端仓库
ARG FRONTEND_REPO=https://github.com/PatchyVideo/Touhou-Vote.git
ARG FRONTEND_BRANCH=dev

RUN apk add --no-cache git && \
    git clone --depth 1 --branch $FRONTEND_BRANCH $FRONTEND_REPO /tmp/frontend

WORKDIR /app

# 复制整个 workspace 结构
COPY --from=builder /tmp/frontend/pnpm-workspace.yaml /app/
COPY --from=builder /tmp/frontend/package.json /app/
COPY --from=builder /tmp/frontend/pnpm-lock.yaml /app/
COPY --from=builder /tmp/frontend/packages/vote /app/packages/vote
COPY --from=builder /tmp/frontend/packages/result /app/packages/result
COPY --from=builder /tmp/frontend/packages/shared /app/packages/shared
COPY --from=builder /tmp/frontend/packages/navigator /app/packages/navigator

# 从 workspace 根目录安装依赖并构建
WORKDIR /app
RUN pnpm install && \
    pnpm --filter @touhou-vote/vote build && \
    pnpm --filter @touhou-vote/result build && \
    pnpm --filter @touhou-vote/navigator build

# ---- 最终阶段：Nginx + 静态文件 ----
FROM nginx:alpine AS production

# 复制构建产物
COPY --from=builder /app/packages/vote/dist /usr/share/nginx/html
COPY --from=builder /app/packages/result/dist /usr/share/nginx/html/result
COPY --from=builder /app/packages/navigator/dist /usr/share/nginx/html/navigator

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost/ || exit 1

# 默认端口
EXPOSE 80 443

# 默认启动命令
CMD ["nginx", "-g", "daemon off;"]
