# 2026-04-08

## Changed

- 同步修正文档中的迁移现状描述，明确 `thvote-be-re` 当前仍处于迁移早期，正式代码骨架位于 `src/app/`。
- 明确 `dao/` 进入废弃流程，只保留短期参考价值，不再作为正式 schema 层扩展。
- 明确 `db_model/` 仅保留早期建模参考价值，后续需经审阅后再迁入正式 ORM 设计。
- 修正配置文档中把目标结构写成现状的问题，避免后续协作基于不存在的代码路径推进。
- 新增并收敛 FastAPI 应用骨架设计说明，明确目录结构、分层职责和迁移优先级。
- 新增 `thvote-be-re/README.md`，约定核心技术栈、模块开发要点、目录规范和命名规范。
- 将 `thvote-be-re` 的历史草稿目录集中迁入 `deprecated/`，并建立 `src/app/` 作为正式代码骨架。
- 删除根目录兼容 `main.py`，将应用入口统一收敛到 `src/app/main.py`。
- 将项目文档整体迁入 `thvote-be-re/docs/`，并合并为更精简的文档结构。
- 在合并远端壳子代码时保留 `src/app` 作为唯一正式结构，并将可复用的配置、异步数据库和 `submit` 原始提交快照能力迁入正式目录。
- 将 `.env` 和本地 SQLite 数据文件移出版本控制，补强忽略规则以避免敏感信息和本地产物再次进入提交。
- 同步更新 README / 架构文档 / 迁移计划，明确当前真实进度是 `submit` 已部分迁入、GraphQL 仍未接入、正式 API 仍待补齐。
- 新增 `docs/auth/implementation-plan.md`，单独约定 Rust `user-manager` 到 Python `modules/auth` 的实现计划、数据模型、双 token 语义和分阶段落地顺序。
- 在 `docs/auth/implementation-plan.md` 中补充阿里云短信服务与阿里云邮件推送的服务商选择、配置项、环境变量和 provider 接入约定。
- 重写 `auth` 文档中的服务商方案，明确本项目应接入阿里云短信认证服务（PNVS）而不是普通短信服务，并同步更新配置项命名和 provider 设计。
- 补齐 `common/security/password.py` 和 `common/security/jwt.py`，新增 Argon2 密码哈希、旧 `bcrypt + salt` 兼容校验，以及 `session_token` / `vote_token` 的基础 JWT 工具。
- 从历史提交恢复 `api/graphql` 的 submit query / mutation 主链路，并重新在 `src/app/main.py` 中挂载 GraphQL 路由。
- 从历史提交恢复 `scraper_client` 的基础 URL 解析、Bilibili / Pixiv / Twitter 站点处理和内部 REST 入口，避免结构重排后功能整体丢失。
- 为 `submit` 恢复旧版限流与提交锁保护，恢复 `/v1/*` 过渡 REST 接口，并把 GraphQL `additional_fingreprint` 字段兼容回旧拼写。

## Compatibility

- 无外部接口兼容性变更。

## Migration / Config

- 无数据迁移执行。
- 后续需要继续完善 `src/app/` 骨架，并开始承接 `auth / submit / result_query` 的正式迁移实现。
