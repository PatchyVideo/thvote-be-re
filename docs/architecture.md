# THVote-be-re Architecture

本文档描述 `thvote-be-re` 当前采用的正式代码结构，以及后续继续迁移时必须遵守的边界。

## 目标

Python 重写的目标不是照搬 Rust 服务拆分，而是先建立一个稳定、模块化、可维护的单体后端，在迁移期逐步承接原有能力。

核心原则：

- 对外以 GraphQL 为主，REST 保留健康检查、内部调试和迁移过渡端点。
- 正式代码统一放在 `src/app/`。
- 历史草稿统一放在 `deprecated/`，只作参考。
- 基础设施、模型、业务模块、接口适配必须分层。

## 正式目录结构

```text
thvote-be-re/
  src/
    app/
      main.py                          # FastAPI 应用工厂，挂载 REST / GraphQL
      api/
        graphql/
          schema.py                    # Strawberry schema 定义
          types.py                     # GraphQL 类型定义
          resolvers/
            submit.py                  # submit query / mutation
        rest/
          router.py                    # REST 路由总线，聚合所有子路由
          health.py                    # 健康检查
          internal.py                  # 内部调试端点
          scraper.py                   # scraper 内部 REST 入口
          submit.py                    # submit 兼容 REST 入口 (/v1/*)
      common/
        config.py                      # Pydantic Settings 配置管理
        errors.py                      # 统一错误模型与异常处理
        deps.py                        # 共享依赖
        logging.py                     # 日志配置
        lifespan.py                    # 应用启动 / 关闭生命周期
        constants.py                   # 全局常量
        database/
          base.py                      # SQLAlchemy Base
          session.py                   # 异步引擎、SessionLocal、get_db_session
        middleware/
          rate_limit.py                # 通用限流（固定窗口 token bucket）
          logging.py                   # 请求日志中间件
          request_id.py                # 请求 ID 中间件
        security/
          jwt.py                       # JWT 签发与校验
          password.py                  # Argon2 密码哈希 + bcrypt 兼容校验
        cache/
          redis.py                     # 全局 Redis 客户端（lru_cache 单例）
        utils/
          pagination.py                # 分页工具
          text.py                      # 文本处理工具
          time.py                      # 时间处理工具
      models/
        orm/
          raw_submit.py                # 5 张提交快照表的 ORM 定义
        dto/
          submit.py                    # 提交相关 Pydantic DTO
          auth.py                      # 认证相关 Pydantic DTO
      modules/
        auth/                          # 认证模块（占位，尚未完成）
          provider.py
          repository.py
          service.py
        submit/                        # 投票提交模块（已完成）
          repository.py                # 数据访问层
          service.py                   # 业务逻辑 + 校验
          guards.py                    # 限流 + 提交锁保护
        scraper_client/                # 外部站点信息解析模块（已完成）
          schemas.py                   # 请求/响应模型
          process.py                   # URL 解析 + 站点分发
          service.py                   # 业务入口
          dao.py                       # Redis 缓存 DAO（URL/UDID 级别）
          sites/
            bilibili.py                # B站视频/专栏解析
            pixiv.py                   # Pixiv 插画/小说解析
            twitter.py                 # Twitter/X 推文解析
          utils/
            biliutils.py               # BV/AV 转换、HTTP Headers/Cookies
            cache.py                   # Redis pickle 缓存 + 限流时间戳
            network.py                 # HTTP 请求、重定向解析、速率限制
        result_query/                  # 结果查询模块（占位，尚未开始）
        vote_data/                     # 投票对象资料模块（占位，尚未开始）
  deprecated/
  docs/
  tests/
  scripts/
```

## 分层职责

### `src/app/api`

职责：

- 暴露 GraphQL / REST 接口。
- 做参数转换和响应组装。
- 调用 service。

不要放：

- SQLAlchemy 查询。
- Redis 操作。
- 复杂统计逻辑。
- token 签发实现。

### `src/app/common`

职责：

- 配置管理（`config.py`，基于 `pydantic-settings`，自动加载 `.env`）。
- 统一错误模型（`errors.py`，`AppError` / `ValidationError` / `NotFoundError`）。
- 日志与生命周期。
- 中间件（限流、请求日志、请求 ID）。
- 安全能力（JWT、密码哈希）。
- 数据库基础设施（异步 SQLAlchemy 引擎 + session）。
- Redis 缓存基础设施（`cache/redis.py` 提供全局共享的 `get_redis_client()`）。
- 通用工具。

约束：

- `common` 只放跨模块复用的基础设施。
- 不放单个业务模块专属规则。

### `src/app/models`

职责：

- `models/orm` 放持久化模型（SQLAlchemy ORM）。
- `models/dto` 放跨接口层共享的输入输出模型（Pydantic）。

约束：

- ORM、DTO、GraphQL type 不能混用。
- 业务仓储统一放在 `modules/*/repository.py`。

### `src/app/modules`

每个模块的内部文件约定：

| 文件 | 职责 |
|---|---|
| `service.py` | 业务入口，编排规则和事务 |
| `repository.py` | 数据访问（SQLAlchemy 查询） |
| `guards.py` | 限流、锁等请求保护（如有需要） |
| `dao.py` | 非关系型数据访问，如 Redis 缓存（如有需要） |
| `provider.py` / `client.py` | 外部服务接入封装（如有需要） |
| `schemas.py` | 模块专属的数据模型（不跨模块共享的模型） |

#### `auth`（未完成）

- 手机号/邮箱 + 密码登录
- 邮箱/手机验证码注册登录
- token 签发与校验
- 用户信息维护

当前状态：最小占位实现，尚未接数据库和 token 签发。

#### `submit`（已完成）

- 5 类提交（角色/音乐/CP/问卷/同人）的创建与回查
- 投票完成状态查询
- 投票统计
- 输入校验（数量限制、长度限制、唯一性校验）
- 请求保护（限流 + 分布式提交锁，基于 Redis）

数据流：

```
REST /v1/* 或 GraphQL
  → guards.guarded_submit()        # 限流 + Redis 分布式锁
    → SubmitService                 # 校验 + 组装
      → SubmitRepository            # SQLAlchemy 异步写入/查询
```

REST 端点（12 个，挂载在 `/v1/` 前缀下）：

- `POST /v1/{category}/` — 提交（character, music, cp, paper, dojin）
- `POST /v1/get-{category}/` — 回查
- `POST /v1/voting-status/` — 投票完成状态
- `POST /v1/voting-statistics/` — 全局统计

#### `scraper_client`（已完成）

- URL 解析与站点分发（支持短链接跳转解析）
- 站点解析器：Bilibili（视频+专栏）、Pixiv（插画+小说）、Twitter/X
- Redis 缓存（pickle 序列化，URL 级别和 UDID 级别）
- 站点级速率限制（Redis 时间戳）
- BV/AV ID 双向转换

数据流：

```
REST /internal/scraper/scrape
  → ScraperService.scrape_url()
    → process.get_data()            # URL 匹配 + 分发
      → sites/*.py                  # 调用第三方 API
        → utils/cache.py            # Redis 缓存读写
        → utils/network.py          # HTTP 请求 + 速率限制
```

#### `result_query`（未开始）

投票结束后的统计查询模块：排名、趋势、理由、共投、完成率、全局统计。

#### `vote_data`（未开始）

可投票对象基础资料模块：角色、音乐、作品的名称、别名、封面、出处等。

## 基础设施关键实现

### Redis

- 全局客户端：`common/cache/redis.py` 的 `get_redis_client()` 返回 `@lru_cache` 缓存的 `redis.asyncio.Redis` 单例。
- 通用限流：`common/middleware/rate_limit.py` 的 `rate_limit()` 实现固定窗口 token bucket。
- 提交锁：`modules/submit/guards.py` 的 `guarded_submit()` 基于 `SET NX PX` 实现分布式锁。
- Scraper 缓存：`modules/scraper_client/utils/cache.py` 使用 pickle hex 序列化存储到 Redis。

### 数据库

- 引擎：`common/database/session.py` 根据 `DATABASE_URL` 自动适配 asyncpg / asyncmy / aiosqlite 驱动。
- Session：通过 `get_db_session()` 依赖注入到路由处理器。
- 建表：`lifespan.py` 启动时调用 `init_db()` 自动建表（开发模式，后续切换到 Alembic）。

## 历史代码处理

以下目录已经进入废弃流程：

- `deprecated/app_router/`
- `deprecated/dao/`
- `deprecated/db_model/`

不可继续承接新功能。仅作字段盘点、迁移核对参考。

## 运行入口

```bash
uvicorn src.app.main:app
```

不再保留根目录兼容入口。

## 当前实现状态

截至 2026-04-08：

| 模块 | 状态 | 说明 |
|---|---|---|
| `common` | 已完成骨架 | config / database / errors / lifespan / cache / security / middleware |
| `submit` | **已完成** | DTO / ORM / repository / service / guards / REST 12 端点 / GraphQL 主链路 |
| `scraper_client` | **已完成** | schemas / process / service / dao / 3 站点解析器 / utils / REST 内部入口 |
| `auth` | 占位 | 最小 provider/repository/service，尚未接数据库和 token |
| `result_query` | 未开始 | 仅 `__init__.py` 占位 |
| `vote_data` | 未开始 | 仅 `__init__.py` 占位 |

## 当前阶段优先级

1. 完成 `auth` 最小闭环。
2. 稳定当前 submit 和 scraper 代码，补最小测试。
3. 补齐数据库迁移策略（Alembic）。
4. 迁移 `vote_data`。
5. 最后承接最复杂的 `result_query`。

## 已知遗留问题

- ORM 列名 `additional_fingerprint`（正确拼写）与旧数据库可能存在的 `additional_fingreprint`（拼写错误）之间需要确认是否需要数据库迁移或 ORM 列名映射。
- Scraper API 路径已从旧的 `/scraper` 迁移到 `/internal/scraper`，前端如有直接调用需同步更新。
