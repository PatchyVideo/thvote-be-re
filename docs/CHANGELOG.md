# thvote-be-re CHANGELOG

> 仓库级变更记录，按 CLAUDE.md §4 维护。日期格式 `YYYY-MM-DD`。
>
> 创建日期：2026-04-27
> 最后更新：2026-04-27

## [Unreleased] — 计划合并：feat/user-and-verify 分支

> 工作期间：2026-04-27
> 包含 commits：`45d75b7` … `c75f552`（共 16 个）
> 合并到主干后请把本节 `[Unreleased]` 改为版本号 + 合并日期

### Added
- 用户与认证模块（feat/user-and-verify 分支）
  - 接入阿里云号码认证服务（PNVS）作为短信验证码全托管方案
  - 接入阿里云邮件推送 DirectMail（SMTP）作为邮件验证码投递通道
  - `EmailCodeService`：本地 6 位码生成 + Redis 存取 + guard 防刷（120s）
  - `SmsCodeService`：薄封装 PNVS 的 `SendSmsVerifyCode` / `CheckSmsVerifyCode`
  - 11 个对齐 Rust 的认证端点 + 1 个 `GET /me` 替代旧 `GET /{user_id}`
  - `ActivityLog` 9 类事件落库（best-effort，不阻断主请求）
  - 登录成功签发 `vote_token`（投票期内 + 已验证 phone 或 email）
  - Alembic 数据库迁移工具引入，baseline migration 把 User + ActivityLog 纳入版本管理
  - 设计文档 `docs/superpowers/specs/2026-04-27-user-auth-design.md`

### Changed
- `vote_token` JWT 主体由 `vote_id` 改为 `user_id`，对齐 Rust 行为；`audience` 保持 `vote`
- 用户敏感端点接入既有速率限制中间件（5 req/60s 按 IP 或 user_id 配比，详见设计文档 §7.4）

### Removed
- 半成品旧端点：`POST /api/v1/user/login`、`POST /api/v1/user/login/email`、`POST /api/v1/user/register`、`GET /api/v1/user/{user_id}`、`DELETE /api/v1/user/{user_id}`
- 历史遗留目录 `src/app/`（仅有 .pyc，无源文件）
- 历史遗留空壳 `src/models/__init__.py`（实际模型在 `src/db_model/`）

### 兼容性
- **破坏性**：上述移除的旧端点如有外部调用方需切换到新端点
- **数据库**：首次部署需运行 `alembic upgrade head`；已有部署字段已对齐，无需回填
- **配置**：要求 `ALIYUN_PNVS_*` 与 `ALIYUN_DM_*` 环境变量就位（Apollo / .env），未配置时调用对应端点会得到 `ALIYUN_NOT_CONFIGURED`
- **依赖新增**：`alembic`、`alibabacloud_dypnsapi20170525`、`alibabacloud_tea_openapi`、`alibabacloud_tea_util`；测试依赖 `freezegun`、`fakeredis`
- **DB 约束变更**：`user.at_least_one_identifier` CHECK 约束放宽为 `removed = TRUE OR phone_number IS NOT NULL OR email IS NOT NULL`，以支持 `remove-voter` 软删除时清空 email/phone（Rust 行为对齐）。已有部署执行 `alembic upgrade head` 即可。

### Operations
- 新增 `docs/operations/aliyun-onboarding.md`：从零到上线的阿里云 PNVS + DirectMail 接入手册（账号/RAM/认证方案/域名验证/SMTP/smoke 验证 + 常见坑）
- 新增 `docs/operations/cicd-pipeline.md`：CI/CD 流水线说明（4 个 workflow 拓扑、Aliyun/Apollo 配置交付路径、follow-up）
- 新增 `docs/superpowers/specs/2026-04-27-user-auth-open-issues.md`：用户与认证模块已知问题与待办（U-1..U-15），按 PR 前已修复 / PR 前待修 / PR 后再做分组
- 新增 `docs/architecture/database-schema-management.md`：数据库 schema 管理现状诊断 + 4 阶段演进路线图（阶段 1 已完成 ✅；阶段 2 把投票相关表纳入 Alembic；阶段 3 移除 init_db 后门；阶段 4 持续纪律）

### Fixed
- **U-1**：`init_db()` 与 Alembic 并存导致 schema 漂移 — 默认部署不再调用 `Base.metadata.create_all`，仅 `DEBUG=true` 时为本地开发保留。生产/测试环境必须靠 `alembic upgrade head`（CI 已就位）
- **U-4**：`remove-voter` 软删除现在同步清除 `password_hash` 与 `legacy_salt`，避免被删用户的密码哈希残留在 DB 里成为撞库素材
- **U-V1**：`_maybe_sign_vote_token` 配置错误从 `logger.warning` 升到 `logger.error`，避免 `VOTE_*_ISO` 打错时所有用户静默拿空 vote_token、submit 全挂但运维无信号
- **U-16**：`EmailCodeService.send` 用 `SET NX EX` 原子化 guard，并发同邮箱不再发两封邮件
- **U-17**：mutation 端点（`update-*` / `remove-voter`）在 token 解码前先做 IP 级限流（30 req/60s），堵住"刷 garbage token 拿快速 401"绕过 per-user 限流的路径
- **U-19**：`pnvs_client` check 失败的错误码从 `SMS_SEND_FAILED` 改为 `SMS_VERIFY_FAILED`，语义对齐

### CI/CD
- `deploy-test.yml` test job 在 `pytest` 之前新增 `alembic upgrade head` 步骤，把 0001 baseline 用真 Postgres service 烟测
- `deploy-test.yml` / `deploy-prod.yml` / `deploy.yml` 三处部署步骤都加 `docker-compose run --rm backend alembic upgrade head`，并在执行前等待 Postgres 健康
- `Dockerfile` 的 development + production stage 都 `COPY alembic/` 与 `alembic.ini`，使容器内可执行迁移
- `deploy-test.yml` 测试依赖加 `fakeredis`（与 requirements.txt 保持一致）

### 兼容性补充
- 首次部署到已有数据库的实例：`alembic upgrade head` 会在 `alembic_version` 表不存在时尝试 `CREATE TABLE user`，**与既有 `user` 表冲突**。需要先 `alembic stamp head` 把现有 schema 标记为最新，再走后续 migration。详见 `docs/operations/cicd-pipeline.md` §五 F-cicd-3。

### Follow-up
见 `docs/superpowers/specs/2026-04-27-user-auth-design.md` §九 F1-F9。
