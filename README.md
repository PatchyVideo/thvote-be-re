# THVote Backend Rewrite

`thvote-be-re` 是 `thvote-be` 的 Python 重写工程，目的是把原本人气投票的核心功能迁移到 Python 生态，并尽可能提高其可维护性。

## 核心技术栈

- Python 3.12+
- FastAPI (核心框架)
- Strawberry GraphQL (主要对外接口)
- SQLAlchemy (ORM)
- Alembic (数据库迁移，尚未接入)
- PostgreSQL (生产数据库)
- Redis (限流、缓存、分布式锁)
- pytest (测试框架)

技术选型原则：

- `FastAPI` 负责应用承载、依赖注入和 REST/GraphQL 集成。
- `Strawberry` 负责 GraphQL schema。
- `Pydantic` 用于输入输出数据类型定义，`pydantic-settings` 管理配置。
- `SQLAlchemy` 用于 ORM 和数据库访问基础设施。
- `Redis` 用于验证码、限流、缓存、分布式锁等短生命周期状态。
- `PostgreSQL` 是正式行为对齐环境。
- `SQLite` 只作为最小本地启动环境，不作为迁移行为一致性的验证基准。

## 当前进度

| 模块 | 状态 | 说明 |
|---|---|---|
| `common` | 已完成骨架 | 配置、数据库、错误处理、Redis、安全、中间件 |
| `submit` | **已完成** | 5 类提交的创建/回查/统计、限流+锁保护、REST 12 端点、GraphQL |
| `scraper_client` | **已完成** | B站/Pixiv/Twitter 解析、Redis 缓存、速率限制、内部 REST |
| `auth` | 占位 | 尚未实现登录/注册闭环 |
| `result_query` | 未开始 | 投票结果统计查询 |
| `vote_data` | 未开始 | 可投票对象资料 |

## 模块简介

### `submit` — 投票提交

投票进行阶段的用户提交后端：

- 角色 / 音乐 / CP / 问卷 / 同人 5 类提交的创建与回查
- 投票完成状态与全局统计查询
- 输入校验（数量/长度/唯一性）
- 请求保护（Redis 固定窗口限流 + 分布式提交锁）

REST 端点挂载在 `/v1/` 前缀下，共 12 个 POST 端点。

### `scraper_client` — 外部站点解析

解析 URL 背后网站里的"东方同人作品"基础信息：

- 支持 Bilibili 视频/专栏、Pixiv 插画/小说、Twitter/X 推文
- 自动识别短链接（b23.tv 等）并跟踪重定向
- BV/AV ID 双向转换
- Redis pickle 缓存 + 站点级速率限制

REST 端点：`POST /internal/scraper/scrape`

### `auth` — 认证（开发中）

计划功能：手机号/邮箱登录、验证码注册、token 签发与校验。详见 `docs/auth/implementation-plan.md`。

### `result_query` — 结果查询（未开始）

投票结束后的数据分析：排名、趋势、理由、共投、完成率、全局统计。

### `vote_data` — 投票对象资料（未开始）

可投票角色、音乐、作品的基础资料管理。

## 目录结构

```text
thvote-be-re/
  src/app/
    main.py              # FastAPI 应用工厂
    api/
      graphql/           # Strawberry GraphQL schema + resolvers
      rest/              # REST 路由（health / internal / scraper / submit）
    common/              # 跨模块基础设施
      config.py          #   pydantic-settings 配置
      database/          #   异步 SQLAlchemy 引擎 + session
      cache/             #   Redis 客户端单例
      middleware/        #   限流、日志、请求 ID
      security/          #   JWT、密码哈希
      errors.py          #   统一错误模型
    models/
      orm/               # SQLAlchemy ORM 模型
      dto/               # Pydantic 数据传输对象
    modules/
      auth/              # 认证模块
      submit/            # 投票提交模块
      scraper_client/    # 外部站点解析模块
      result_query/      # 结果查询模块
      vote_data/         # 投票对象资料模块
  deprecated/            # 历史草稿（仅供参考）
  docs/                  # 项目文档
  tests/                 # 测试
  scripts/               # 开发脚本
```

各目录职责详见 `docs/architecture.md`。

## 启动

```bash
uvicorn src.app.main:app --host 0.0.0.0 --port 8000
```

## 分层约束

- API 层只做参数解析、调用 service、返回响应。
- service 层负责业务编排、事务和规则。
- repository 层只负责数据访问。
- ORM 模型、Pydantic schema、GraphQL type 不要混用。
- 外部服务调用统一通过 provider 或 client 封装。
- `common` 只放跨模块复用的基础设施。

## 命名规范

- 文件名：`snake_case`
- 类名：`PascalCase`（`AuthService`、`SubmitRepository`）
- 函数/变量：`snake_case`
- 常量：`UPPER_SNAKE_CASE`
- DTO：业务语义命名（`CharacterSubmitRequest`、`VotingStatus`）
- ORM：实体命名（`RawCharacterSubmit`）
- GraphQL：显式后缀（`UserType`、`RankingEntryType`）

## 文档

- `docs/architecture.md` — 架构设计与分层职责
- `docs/migration-plan.md` — 迁移计划
- `docs/auth/implementation-plan.md` — 认证模块实现计划
- `docs/CHANGELOG.md` — 变更记录
