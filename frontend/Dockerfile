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

WORKDIR /app

# ---- 构建阶段：投票页面 ----
FROM base AS vote-builder

# 克隆前端仓库（只获取必要部分）
ARG FRONTEND_REPO=https://github.com/PatchyVideo/Touhou-Vote.git
ARG FRONTEND_BRANCH=dev

RUN apk add --no-cache git && \
    git clone --depth 1 --branch $FRONTEND_BRANCH $FRONTEND_REPO /tmp/frontend && \
    cd /tmp/frontend && \
    cp -r packages/vote/. /app/vote/ && \
    cp -r packages/shared/. /app/shared/ && \
    cp package.json pnpm-lock.yaml /app/

# 安装依赖并构建
WORKDIR /app
RUN pnpm install && \
    cd vote && pnpm install && \
    pnpm build

# ---- 构建阶段：结果页面 ----
FROM base AS result-builder

# 克隆前端仓库
ARG FRONTEND_REPO=https://github.com/PatchyVideo/Touhou-Vote.git
ARG FRONTEND_BRANCH=dev

RUN apk add --no-cache git && \
    git clone --depth 1 --branch $FRONTEND_BRANCH $FRONTEND_REPO /tmp/frontend && \
    cd /tmp/frontend && \
    cp -r packages/result/. /app/result/ && \
    cp -r packages/shared/. /app/shared/ && \
    cp package.json pnpm-lock.yaml /app/

# 安装依赖并构建
WORKDIR /app
RUN pnpm install && \
    cd result && pnpm install && \
    pnpm build

# ---- 构建阶段：导航页（可选）----
FROM base AS nav-builder

ARG FRONTEND_REPO=https://github.com/PatchyVideo/Touhou-Vote.git
ARG FRONTEND_BRANCH=dev

RUN apk add --no-cache git && \
    git clone --depth 1 --branch $FRONTEND_BRANCH $FRONTEND_REPO /tmp/frontend && \
    cd /tmp/frontend && \
    cp -r packages/navigator/. /app/navigator/ && \
    cp package.json pnpm-lock.yaml /app/

WORKDIR /app
RUN pnpm install && \
    cd navigator && pnpm install && \
    pnpm build

# ---- 最终阶段：Nginx + 静态文件 ----
FROM nginx:alpine AS production

# 复制构建产物
COPY --from=vote-builder /app/vote/dist /usr/share/nginx/html
COPY --from=result-builder /app/result/dist /usr/share/nginx/html/result
COPY --from=nav-builder /app/navigator/dist /usr/share/nginx/html/navigator

# 复制 Nginx 配置（通过 volume 挂载，使用环境变量动态选择）
# 此处只提供默认配置，实际配置通过 docker-compose 的 volume 挂载

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost/ || exit 1

# 默认端口
EXPOSE 80 443

# 默认启动命令
CMD ["nginx", "-g", "daemon off;"]
