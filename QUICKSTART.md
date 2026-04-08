# ============================================================
# THVote Docker 环境快速入门
#
# 本文档帮助你快速启动和管理 Docker 测试/生产环境
# ============================================================

## 一、环境准备

### 1.1 安装 Docker

- Windows: 下载 [Docker Desktop](https://www.docker.com/products/docker-desktop)
- 启动 Docker Desktop，确保 Docker daemon 正常运行

### 1.2 验证安装

```bash
docker --version
docker-compose --version
```

## 二、快速开始

### 2.1 启动测试环境

```bash
# 1. 进入项目目录
cd thvote-be-re

# 2. 启动所有服务
docker-compose -f docker-compose.test.yml up -d

# 3. 查看服务状态
docker-compose -f docker-compose.test.yml ps

# 4. 查看日志
docker-compose -f docker-compose.test.yml logs -f
```

### 2.2 访问服务

| 服务 | 地址 |
|------|------|
| 前端界面 | http://localhost:8082 |
| 后端 API | http://localhost:8000 |
| 健康检查 | http://localhost:8000/health |
| Apollo Config | http://localhost:18080 |

### 2.3 常用命令

```bash
# 启动
docker-compose -f docker-compose.test.yml up -d

# 停止
docker-compose -f docker-compose.test.yml down

# 查看日志
docker-compose -f docker-compose.test.yml logs -f backend-test

# 重启服务
docker-compose -f docker-compose.test.yml restart backend-test

# 完全重置（删除所有数据）
docker-compose -f docker-compose.test.yml down -v
```

## 三、使用管理脚本

### 3.1 测试环境脚本

```bash
# 启动测试环境
./scripts/test-env.sh start

# 查看状态
./scripts/test-env.sh status

# 查看日志
./scripts/test-env.sh logs backend-test

# 健康检查
./scripts/test-env.sh health

# 备份数据库
./scripts/test-env.sh backup

# 完全清理
./scripts/test-env.sh clean
```

### 3.2 生产环境脚本

```bash
# 首次使用需要创建配置文件
cp .env.prod.example .env.prod
# 编辑 .env.prod 填入实际密码

# 启动生产环境
./scripts/prod-env.sh start

# 查看状态
./scripts/prod-env.sh status

# 备份
./scripts/prod-env.sh backup

# 回滚
./scripts/prod-env.sh rollback
```

## 四、Nginx 配置说明

### 4.1 前端静态文件

```bash
# 将前端构建产物放入对应目录
frontend/test/dist/      # 测试环境
frontend/prod/dist/     # 生产环境
```

### 4.2 SSL 证书（生产环境）

```bash
# 创建证书目录
mkdir -p frontend/nginx/ssl

# 放入证书文件
# server.crt - 服务器证书
# server.key - 私钥
```

### 4.3 API 代理

Nginx 会自动将请求转发到后端：
- `/api/*` → `backend:8000/api/*`
- `/graphql/*` → `backend:8000/graphql/*`

## 五、数据库操作

### 5.1 连接数据库

```bash
# 测试环境
docker exec -it thvote-postgres-test psql -U thvote_test -d thvote_test

# 生产环境
docker exec -it thvote-postgres-prod psql -U thvote_prod -d thvote_prod
```

### 5.2 备份数据库

```bash
# 测试环境
docker exec thvote-postgres-test pg_dump -U thvote_test thvote_test > backup.sql

# 生产环境（压缩）
docker exec thvote-postgres-prod pg_dump -U thvote_prod thvote_prod | gzip > backup.sql.gz
```

### 5.3 恢复数据库

```bash
# 停止服务
docker-compose -f docker-compose.test.yml stop backend-test

# 恢复
cat backup.sql | docker exec -i thvote-postgres-test psql -U thvote_test thvote_test

# 重启服务
docker-compose -f docker-compose.test.yml start backend-test
```

## 六、常见问题

### Q1: 端口被占用

如果端口 8082、8000 等被占用，可以修改 `docker-compose.test.yml` 中的端口映射：

```yaml
services:
  frontend-test:
    ports:
      - "8083:80"  # 改为 8083
```

### Q2: 数据库连接失败

检查网络连通性：
```bash
docker network ls
docker network inspect thvote-test-network
```

### Q3: 前端无法访问后端

检查 Nginx 配置是否正确：
```bash
docker exec thvote-frontend-test cat /etc/nginx/conf.d/default.conf
```

### Q4: 清理所有 Docker 资源

```bash
# 停止并删除所有容器
docker-compose -f docker-compose.test.yml down -v
docker-compose -f docker-compose.prod.yml down -v

# 清理未使用的镜像
docker image prune -a

# 清理构建缓存
docker builder prune -af
```

## 七、生产环境部署清单

1. ✅ 创建 `.env.prod` 文件
2. ✅ 配置 SSL 证书
3. ✅ 部署前端构建产物
4. ✅ 执行初始数据库迁移
5. ✅ 配置备份策略
6. ✅ 配置监控告警

## 八、灾备切换

当需要切换到物理机中间件时：

```bash
# 编辑 .env.prod，配置灾备地址
FALLBACK_DATABASE_URL=postgresql://user:pass@物理机IP:5432/thvote_prod
FALLBACK_REDIS_URL=redis://物理机IP:6379/0

# 重启后端
./scripts/prod-env.sh restart backend-prod
```

---

如有问题，请查看详细日志或联系开发团队。
