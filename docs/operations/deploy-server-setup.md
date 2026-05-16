# 部署机环境配置

> 创建日期：2026-05-16
> 最后更新：2026-05-16

## 概述

生产/测试环境部署机上的 `docker-compose.yml` **由 CI workflow 自动生成**，
仓库内没有对应的源文件（`docker/` 目录已在 2026-05 从仓库删除）。

## 文件位置

```
${TEST_SERVER_DIR:-/opt/thvote/test}/
├── .env                  # CI 每次部署时写入
├── docker-compose.yml    # CI 首次部署或触发重建时写入（见下）
└── logs/                 # 后端日志挂载目录
```

## docker-compose.yml 的生命周期

CI `deploy-test` job 在每次部署时检查 compose 文件：

- 文件不存在 → 从 CI workflow heredoc 重新生成
- 文件存在但不含 `NACOS_ENABLED` 字段 → 重新生成
- 其他情况 → 仅替换 `image:` 中的 tag

**如需修改 compose 内容**，应编辑 `.github/workflows/deploy-test.yml`
中 `COMPOSEEOF` heredoc，而非直接修改部署机上的文件（下次 CI 触发
重建条件时会被覆盖）。

## 外部依赖

| 服务 | 管理方式 |
|---|---|
| PostgreSQL | 阿里云 RDS，不在 compose 中，通过 Nacos 注入 `DATABASE_URL` |
| Redis | compose 管理（`thvote-redis` 容器），部署机上持久化 |
| Backend | compose 管理（`thvote-backend` 容器） |

## Redis 启动规则

CI 只在 `thvote-redis` 容器不存在时启动它（`docker-compose up -d redis`）。
Redis 数据通过 `redis-data` volume 持久化，不随容器重启丢失。

## 网络

所有服务通过外部网络 `thvote-net` 通信。CI 在网络不存在时自动创建。

## Nacos 配置

后端敏感配置（数据库凭据、JWT 密钥、阿里云 AK 等）均通过 Nacos 下发，
不写入部署机文件系统。Nacos 地址和命名空间通过 GitHub Secrets 注入。
