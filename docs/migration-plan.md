# THVote-be-re Migration Plan

本文档回答两个问题：

1. Rust 旧后端能力在 Python 里如何映射。
2. 当前迁移应该先做什么，后做什么。

## Rust 模块映射

| Rust 模块 | 现有职责 | Python 目标模块 |
|---|---|---|
| `gateway` | GraphQL 网关、少量 REST | `api/graphql` + `api/rest` |
| `user-manager` | 登录、验证码、token、资料管理 | `modules/auth` |
| `submit-handler` | 投票提交、回查、状态查询 | `modules/submit` |
| `result-query` | 排名、趋势、理由、问卷、共投、缓存 | `modules/result_query` |
| `vote-data` | 可投票对象数据 | `modules/vote_data` |
| `scraper` | 外部作品信息抓取 | `modules/scraper_client` |
| `pvrustlib` | 公共错误与 HTTP JSON 封装 | `common/errors` + `models/dto` |

## 当前状态

截至 2026-04-08：

- 正式骨架已经建立在 `src/app/`。
- 历史草稿已经收拢到 `deprecated/`。
- `common` 已有配置、异步数据库 session、基础错误处理和生命周期骨架。
- `auth` 仍只有最小占位代码。
- `submit` 已迁入 DTO、原始提交快照 ORM、repository、service 和基本校验逻辑。
- GraphQL 仍是占位文件，正式业务接口尚未接入应用。

## 遗留草稿结论

### `deprecated/dao`

定位：

- 只保留短期参考价值。

用途：

- 名词表。
- 字段草图。
- 查询名称盘点。

限制：

- 不再新增功能。
- 不再作为正式 schema / DTO 落点。

### `deprecated/db_model`

定位：

- 只保留早期建模参考价值。

可参考：

- PostgreSQL 类型选择。
- 少量字段约束思路。

限制：

- 不直接作为正式 ORM 目录继续扩展。
- 最终 ORM 应落在 `src/app/models/orm/`。

## 迁移顺序

推荐顺序：

1. `auth`
2. `submit`
3. `vote_data`
4. `result_query`

这样安排的原因：

- `auth` 是所有写操作和状态校验的前提。
- `submit` 主体逻辑已经开始落地，当前优先级是把它接入正式 API。
- `result_query` 复杂度最高，应该最后迁入。

## 关键约束

- 新代码只写进 `src/app/`。
- 不继续扩展 `deprecated/`。
- GraphQL 是主要对外接口。
- 提交相关能力必须保留原始提交快照，不做覆盖式单行存储。
- token、安全、配置、数据库会话必须收敛到 `common`。

## 下一阶段建议

下一阶段建议直接推进：

1. 补齐 `modules/auth` 的最小登录闭环。
2. 将 `modules/submit` 接入正式 REST / GraphQL API。
3. 定义 `models/orm` 里的用户、验证码、缓存、审计模型。
4. 明确 Alembic 与 `init_db()` 的边界，避免开发期初始化方式固化为长期方案。
