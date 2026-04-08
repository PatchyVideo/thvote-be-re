# THVote Backend Rewrite

`thvote-be-re` 是 `thvote-be` 的 Python 重写工程，目的是把原本人气投票的核心功能迁移到 Python 生态，并尽可能提高其可维护性。

当前仓库仍处于迁移早期阶段，历史草稿目录已经收拢到 `deprecated/`。正式实现应优先收敛到新的 `src/app/` 结构。

当前真实进度：

- `common` 已有配置、异步数据库 session、基础错误处理和生命周期骨架。
- `auth` 仍只有最小占位 service，尚未形成可用登录闭环。
- `submit` 已有 DTO、ORM、repository、service 和校验逻辑，但还没有接入正式 REST / GraphQL API。
- GraphQL 目前仍是占位文件，应用实际只挂载了最小 REST 端点。

项目文档已经收敛到 `docs/`，当前只保留：

- `docs/architecture.md`
- `docs/migration-plan.md`
- `docs/CHANGELOG.md`

## 核心技术栈

- Python 3.12+
- FastAPI (核心框架)
- Strawberry GraphQL (主要对外接口)
- SQLAlchemy (ORM)
- Alembic (数据库迁移)
- PostgreSQL (生产数据库)
- Redis (用于验证码、限流、缓存等短生命周期状态)
- pytest (测试框架)

技术选型原则：

- `FastAPI` 负责应用承载、依赖注入和 REST/GraphQL 集成。
- `Strawberry` 负责 GraphQL schema。
- `Pydantic` 用于输入输出数据类型定义。
- `SQLAlchemy` 用于 ORM 和数据库访问基础设施。
- `Redis` 用于验证码、限流、缓存等短生命周期状态。
- `PostgreSQL` 是正式行为对齐环境。
- `SQLite` 只作为最小本地启动环境，不作为迁移行为一致性的验证基准。

## 模块构成和开发要点

### `auth` 模块

登录和验证模块，主要负责：

- 手机号/邮箱 + 密码登录
- 邮箱验证码注册/登录
- 手机验证码注册/登录
- token 签发与校验
- 用户基本信息维护更新


当前计划采用阿里云短信服务和阿里云邮件推送，具体配置要求见：

- `docs/auth/implementation-plan.md`

### `submit` 模块

投票进行阶段用户投票时的后端，负责：

- 角色投票提交
- 音乐投票提交
- CP 投票提交
- 问卷提交
- 同人作品提交
- 用户的提交回查
- 投票完成状态查询

这些提交都和用户本身状态相关，需要权限校验，并保留原始提交快照。

### `result_query` 模块

投票结束之后的统计阶段的后端，主要负责：

- 排名查询
- 理由查询
- 趋势查询
- 单项查询
- 共投分析
- 问卷统计
- 完成率
- 全局统计

这个模块负责投票结束后的数据分析和统计，查询性能要求较高，需要单独设计缓存和聚合策略。

### `vote_data` 模块

负责：

- 可投票角色、音乐、作品等基础资料
- 别名、封面、出处、发售时间等辅助查询

开发约束：

- 资料查询和提交逻辑分离。
- 不要把 ORM 模型直接暴露给 API。

### `scraper_client` 模块

一个单独的功能性模块，用来解析url背后网站里面的“东方同人作品”基础信息

核心难点在于需要适配多种不同的平台(如B站、A站、微博等)，并且需要处理各种不同的页面结构和反爬机制。

## 目录结构

正式目录结构应收敛到：

```text
thvote-be-re/
  src/
    app/
      main.py
      api/
      common/
      models/
      modules/
  deprecated/
  tests/
  scripts/
```

各目录职责：

- `src/app/main.py`
  - 创建 FastAPI 应用，注册路由、生命周期和异常处理。
- `src/app/api`
  - 只放 GraphQL / REST 适配层。
- `src/app/common`
  - 放配置、错误、中间件、安全、数据库基础设施、缓存、通用工具等跨模块复用能力。
- `src/app/models`
  - 放 DTO 和 ORM 模型，避免业务模块和基础设施混放模型定义。
- `src/app/modules`
  - 放业务模块，是主要开发区域。
- `deprecated`
  - 放历史草稿目录，仅作迁移参考。
- `tests`
  - 放单元测试、集成测试、契约测试。
- `scripts`
  - 放可复用的开发脚本，不要把一次性脚本丢到根目录。

启动时应直接指向 `src/app/main.py`，例如使用 `uvicorn src.app.main:app`。

## 历史目录处理规则

- `deprecated/app_router/`
  - 历史 FastAPI 草稿目录，不再扩展。
- `deprecated/dao/`
  - 已进入废弃流程，只保留短期参考价值，不再承接新功能。
- `deprecated/db_model/`
  - 仅保留早期建模参考价值，后续应把有价值的约束和字段迁入正式 `src/app/models/orm/`。

## 命名规范

通用原则：

- 优先使用清晰的业务语义命名，不要使用 `tmp`、`new_handler`、`data2` 这类名字。
- 文件名使用 `snake_case`。
- 类名使用 `PascalCase`。
- 函数、变量、模块名使用 `snake_case`。
- 常量使用 `UPPER_SNAKE_CASE`。

分层命名建议：

- API 路由文件使用资源或能力命名，例如 `health.py`、`internal.py`、`auth.py`。
- `common` 下的文件使用基础设施语义命名，例如 `config.py`、`errors.py`、`session.py`、`jwt.py`。
- service 使用 `<Domain>Service` 命名，例如 `AuthService`、`SubmitService`。
- repository 使用 `<Domain>Repository` 命名，例如 `AuthRepository`、`SubmitRepository`。
- Pydantic 输入输出模型使用业务语义命名，例如 `EmailLoginRequest`、`VotingStatusResponse`。
- ORM 模型使用持久化实体命名，例如 `UserModel`、`VoteSubmissionModel`，避免与 Pydantic schema 重名。
- GraphQL 类型使用显式后缀区分，例如 `UserType`、`RankingEntryType`。

## 分层约束

必须遵守以下边界：

- API 层只做参数解析、调用 service、返回响应。
- service 层负责业务编排、事务和规则。
- repository 层只负责数据访问。
- ORM 模型、Pydantic schema、GraphQL type 不要混用。
- 外部服务调用统一通过 provider 或 client 封装。
- GraphQL 是主要对外业务接口，REST 只保留健康检查和迁移过渡端点。
- `common` 只放跨模块复用的基础设施，不放单个模块专属业务逻辑。

禁止事项：

- 不要在路由层直接写 SQLAlchemy 查询。
- 不要在 resolver 里直接操作 Redis。
- 不要让 repository 负责拼装 GraphQL 返回结构。
- 不要在业务代码中直接读取环境变量。

## 开发顺序建议

推荐按以下顺序推进：

1. 完成 `auth` 最小闭环。
2. 把 `submit` 接入正式 REST / GraphQL API。
3. 迁移 `vote_data`。
4. 最后迁移 `result_query`。

## 当前阶段注意事项

- 不要继续往 `deprecated/app_router/` 和 `deprecated/dao/` 里写新代码。
- 不要把 `deprecated/db_model/` 直接当成正式 ORM 主目录。
- 正式骨架已经建立，但接口层仍未完成；后续重点应转向把 `auth` 和 `submit` 接成真实可调用链路。
