# ============================================================
# THVote Docker 环境配置
#
# 配置体系：
# - 环境变量: 基础连接信息和显式覆盖项
# - .env 文件: 本地开发配置
# - Apollo: 业务配置中心
# ============================================================

## 目录结构

```
thvote-be-re/
├── docker/                          # Docker 相关配置
│   ├── docker-compose.test.yml      # 测试环境配置
│   ├── docker-compose.prod.yml      # 生产环境配置
│   ├── .env.example                 # 环境变量示例
│   ├── test-env.sh                  # 测试环境管理脚本
│   └── DOCKER_README.md
├── Dockerfile                       # 后端多阶段构建
├── frontend/                        # 前端代码
└── .github/workflows/               # CI/CD 配置
    ├── deploy-test.yml              # 测试环境部署
    └── deploy-prod.yml              # 生产环境部署
```

## 快速开始

### 测试环境

```bash
# 1. 复制环境配置模板
cp .env.test.example .env.test
# 编辑 .env.test 填入实际密码

# 2. 启动服务
cd docker
./test-env.sh start

# 3. 查看状态
./test-env.sh status
```

### 生产环境

```bash
# 1. 配置 GitHub Secrets
# - TEST_SERVER_HOST, TEST_SERVER_USER, TEST_SERVER_SSH_KEY
# - TEST_DB_PASSWORD

# 2. 推送到 main 或 zfq_dev 分支触发部署
git push origin zfq_dev
```

## 增量部署

CI/CD 会根据代码变更自动判断需要部署的服务：

| 变更路径 | 部署行为 |
|---------|---------|
| `src/`, `requirements.txt`, `Dockerfile` | 只重启后端 |
| `frontend/` | 只重启前端 |
| 其他文件 | 仅运行检查，不部署 |

基础服务（PostgreSQL、Redis）始终保持运行。Apollo 独立部署在 `/opt/apollo`，不由 THVote 流水线启动或重启。

## 常用命令

### 测试环境

```bash
cd docker
./test-env.sh start      # 启动
./test-env.sh stop       # 停止
./test-env.sh restart    # 重启
./test-env.sh status     # 查看状态
./test-env.sh logs       # 查看日志
./test-env.sh logs backend-test  # 查看后端日志
./test-env.sh health     # 健康检查
./test-env.sh clean      # 完全清理（删除数据）
./test-env.sh backup     # 备份数据库
```

### 服务访问地址

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:8082 |
| 后端 API | http://localhost:8000 |
| 健康检查 | http://localhost:8000/health |
| Apollo Portal | 独立部署，默认 http://localhost:18080 |
