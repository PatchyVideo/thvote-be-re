# THVote-be-re Architecture

本文档描述 `thvote-be-re` 当前采用的正式代码结构，以及后续继续迁移时必须遵守的边界。

## 目标

Python 重写的目标不是照搬 Rust 服务拆分，而是先建立一个稳定、模块化、可维护的单体后端，在迁移期逐步承接原有能力。

核心原则：

- 对外仍以 GraphQL 为主，REST 只保留健康检查和迁移过渡端点。
- 正式代码统一放在 `src/app/`。
- 历史草稿统一放在 `deprecated/`，只作参考。
- 基础设施、模型、业务模块、接口适配必须分层。

## 正式目录结构

```text
thvote-be-re/
  src/
    app/
      main.py
      api/
        graphql/
        rest/
      common/
        config.py
        errors.py
        deps.py
        logging.py
        lifespan.py
        constants.py
        database/
        middleware/
        security/
        cache/
        utils/
      models/
        orm/
        dto/
      modules/
        auth/
        submit/
        result_query/
        vote_data/
        scraper_client/
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

- 配置管理。
- 统一错误模型。
- 日志与生命周期。
- 中间件。
- 安全能力。
- 数据库与缓存基础设施。
- 通用工具。

约束：

- `common` 只放跨模块复用的基础设施。
- 不放单个业务模块专属规则。

### `src/app/models`

职责：

- `models/orm` 放持久化模型。
- `models/dto` 放跨接口层共享的输入输出模型。

约束：

- ORM、DTO、GraphQL type 不能混用。
- 业务仓储统一放在 `modules/*/repository.py`。

### `src/app/modules`

职责：

- `auth`: 登录、验证码、token、资料更新、审计。
- `submit`: 角色/音乐/CP/问卷/同人提交与回查。
- `result_query`: 排名、趋势、理由、共投、完成率、全局统计。
- `vote_data`: 可投票对象资料。
- `scraper_client`: 外部站点信息解析。

约束：

- 每个模块内的 `service.py` 是业务入口。
- `repository.py` 只负责数据访问。
- 外部服务接入统一通过 `provider.py` 或 `client.py`。

## 历史代码处理

以下目录已经进入废弃流程：

- `deprecated/app_router/`
- `deprecated/dao/`
- `deprecated/db_model/`

这些内容只可用于：

- 字段盘点
- Rust / Python 对照
- 迁移核对

不可继续承接新功能。

## 运行入口

应用入口统一为：

- `uvicorn src.app.main:app`

不再保留根目录兼容入口。

## 当前阶段优先级

当前最重要的工作顺序：

1. 完善 `common` 下的配置、数据库、安全和日志。
2. 先完成 `auth` 最小闭环。
3. 再完成 `submit` 最小闭环。
4. 最后承接最复杂的 `result_query`。
