<!--
本文是 PR 描述草稿，用于 `feat/user-and-verify` → 主干。
开 PR 时把内容粘进 GitHub PR 描述框；本文件本身在 PR 合并后可删除。
-->

# feat(user): user table + auth module migrated from Rust user-manager

## TL;DR

把 `thvote-be/user-manager`（Rust/Actix）的核心功能迁移到 `thvote-be-re/src/apps/user/`（Python/FastAPI）：

- **12 个端点**（11 个 Rust 对齐 + 1 个新增 `GET /me`），全部位于 `/api/v1/user/*`
- **阿里云 PNVS** 全托管短信验证码（个人开发者免资质，**验证码不进我方 Redis、不入日志**）
- **阿里云 DirectMail SMTP** 邮件验证码投递（本地生成 6 位码 + Redis 存储 + guard 防刷）
- **Alembic 引入** + baseline migration 把 `user` + `activity_log` 纳入版本管理；CI test/deploy 都跑 `alembic upgrade head`
- **vote_token JWT** 主体由 `vote_id` 改为 `user_id`（对齐 Rust）
- **44 个测试**全过（unit + integration + contract）

变更规模：50 files / +4379 / −284，**17 个 commit**。

---

## 改动分类（按主题）

### 用户表与端点
- `src/apps/user/{router,service,dao,deps,schemas}.py` 重写
- 12 个端点（详见 §六 端点清单）
- 旧的半成品端点 `/login`、`/login/email`、`/register`、`/{user_id}`、`DELETE /{user_id}` 全部移除

### 外部集成
- `src/common/aliyun/pnvs_client.py`（PNVS：`SendSmsVerifyCode` + `CheckSmsVerifyCode`）
- `src/common/aliyun/dm_smtp_client.py`（DirectMail SMTP）
- `src/common/verification/{email_code,sms_code}.py`（业务封装）

### 数据库
- `alembic/versions/0001_initial_user_and_activity_log.py`（baseline）
- `src/db_model/user.py` 的 `at_least_one_identifier` CHECK 约束放宽，允许 `removed=TRUE` 行同时清空 email/phone（Rust 行为对齐）
- `src/main.py` 的 `init_db()` gate 在 `DEBUG=true` 后面，生产/CI 完全靠 Alembic

### CI/CD
- `.github/workflows/{deploy-test,deploy-prod,deploy}.yml` 部署链路加 `alembic upgrade head`，启动 backend 之前先迁移
- `Dockerfile` 的 development + production stage 都 `COPY alembic/` 与 `alembic.ini`
- `requirements.txt` 新增 `alembic`、`alibabacloud_*`、`fakeredis`、`freezegun`

### 文档（一律在 `docs/` 下，按 CLAUDE.md §2）
- `docs/README.md` — docs/ 索引
- `docs/CHANGELOG.md` — 仓库级变更记录（CLAUDE.md §4）
- `docs/superpowers/specs/2026-04-27-user-auth-design.md` — 设计稿
- `docs/superpowers/specs/2026-04-27-user-auth-implementation-report.md` — 实施事后记录
- `docs/superpowers/specs/2026-04-27-user-auth-open-issues.md` — 已知问题清单（U-1..U-19 + 祖传 L-1..L-3）
- `docs/operations/aliyun-onboarding.md` — 阿里云接入手册
- `docs/operations/cicd-pipeline.md` — CI/CD 流水线说明（含触发约定）
- `docs/architecture/database-schema-management.md` — Alembic 演进路线图
- `docs/migration/user-manager.md` — Rust→Python 迁移文档（更新进度到全部完成）

---

## 端点清单（all under `/api/v1/user/`）

| 端点 | 方法 | 鉴权 | 限流 |
|---|---|---|---|
| `send-email-code` | POST | 公开 | Redis guard 120s（已用 `SET NX EX` 原子化） |
| `send-sms-code` | POST | 公开 | 阿里云 PNVS 自带 |
| `login-email-password` | POST | 公开 | 5/60s per IP |
| `login-email` | POST | 公开 | 5/60s per IP |
| `login-phone` | POST | 公开 | 5/60s per IP |
| `update-email` | POST | body `user_token` | 30/60s per IP + 5/60s per user_id |
| `update-phone` | POST | body `user_token` | 同上 |
| `update-nickname` | POST | body `user_token` | 同上 |
| `update-password` | POST | body `user_token` | 同上 |
| `remove-voter` | POST | body `user_token` | 同上 |
| `token-status` | POST | body `user_token` | 不限 |
| `me` | GET | `Authorization: Bearer …` | 不限 |

---

## 与 Rust 的刻意保留差异

| 项 | Rust | 我们 | 原因 |
|---|---|---|---|
| 数据库 | MongoDB | PostgreSQL | 架构升级 |
| 短信验证码生成 | 本地 + Redis | **阿里云 PNVS 全托管** | 个人开发者免资质，验证码不出阿里云 |
| 验证码明文入审计 | 是 | **否** | CLAUDE.md §5 安全要求 |
| `additional_fingureprint` 拼写 | 错 | **保留错** | 前端契约兼容 |
| 路径前缀 | `/v1/*` | `/api/v1/user/*` | 与现有领域子前缀风格一致 |
| `GET /me` 端点 | 无 | **新增** | 替代 `GET /{user_id}` 半成品；唯一用 `Authorization` header |

完整列表见 `docs/superpowers/specs/2026-04-27-user-auth-design.md` §十一。

---

## Test plan

- [ ] CI lint 通过（flake8）
- [ ] CI test job 通过（44 测试，需要 PG + Redis service container；`alembic upgrade head` 在 pytest 之前跑通）
- [ ] 本地 `python -m pytest tests/` 通过
- [ ] CI 镜像构建通过（`Dockerfile` `production` target 含 `alembic/` + `alembic.ini`）
- [ ] **上线前手动 smoke**（自动化里全 mock 阿里云）：按 `docs/operations/aliyun-onboarding.md` §五跑真接口
  - [ ] `send-sms-code` → 收到真短信
  - [ ] `login-phone` → 拿到 `{user, session_token, vote_token}`
  - [ ] `send-email-code` → 收到真邮件（含垃圾箱）
  - [ ] `login-email` → 拿到 `{user, session_token, vote_token}`
  - [ ] 重复发码 → 120s 内 `429 REQUEST_TOO_FREQUENT`
  - [ ] 错码 / 过期码 / 重用码 → `400 INCORRECT_VERIFY_CODE`
- [ ] **上线前 ops 检查**：
  - [ ] Apollo `application` namespace 配齐 `ALIYUN_PNVS_*`（10 项）+ `ALIYUN_DM_*`（7 项），见 `docs/operations/cicd-pipeline.md` §四
  - [ ] 测试服 / 生产服上跑过 `alembic upgrade head`（CI 已自动跑）
  - [ ] 验证 `vote_token` 在投票期内能被签发（依赖 `VOTE_START_ISO` / `VOTE_END_ISO` 配置）

---

## Reviewer focus

> 全 17 个 commit、4000+ 行改动；如果时间紧，建议按以下优先级 review：

1. **`src/apps/user/service.py`** —— 业务编排核心，所有错误处理、token 签发、审计日志都在这里
2. **`alembic/versions/0001_initial_user_and_activity_log.py`** —— DDL 变更，确认与 `src/db_model/{user,activity_log}.py` 完全对齐
3. **`src/common/aliyun/pnvs_client.py`** —— PNVS 错误码到我方业务异常的映射
4. **`src/common/verification/email_code.py`** —— Redis guard 原子化、SMTP 失败回滚
5. **`src/apps/user/router.py`** —— 12 个端点的限流策略 + IP 预限流（U-17 修复）
6. **`tests/integration/test_login_flows.py`** + **`test_update_and_remove.py`** —— 集成场景覆盖

> 已知问题都登记在 `docs/superpowers/specs/2026-04-27-user-auth-open-issues.md`，把注意力放在表外的事即可。

---

## 已知问题（不阻塞合并）

### PR 后再做（用户与认证模块本身的）
- **U-5/6/7**：vote_token 签发集成测试、`GET /me` 测试、bcrypt→argon2 端到端测试
- **U-8**：`Settings` / Aliyun client 的 `lru_cache` 阻碍 Apollo 热更新（运行时改 Aliyun 配置须重启容器，已文档化）
- **U-9**：`_safe_log` 失败无可见性（无计数器、不影响 `/health`）
- **U-10**：`update-password` 与其他 update-* 共享限流桶
- **U-11**：错误响应结构与 Rust 不一致（前端不投诉就先不改）
- **U-12**：mypy 没在 CI 跑
- **U-13**：Pydantic V1 弃用 API 残留
- **U-14/15**：测试覆盖盲区
- **U-18**：`UserDAO.save()` 未用 `merge()`

### 祖传问题（**不在本 PR 范围**，单独 PR 处理）
- **L-1**：CORS `allow_origins=["*"]` + `allow_credentials=True`（pre-existing）
- **L-2**：`rate_limit.py` 非原子，登录限流可被并发绕过（pre-existing，但**新增登录端点放大了它的安全影响**）
- **L-3**：`logging.basicConfig` 重复调用（merge 残留）

> ⚠️ **L-2 应被视为已知安全 backlog**：合并后建议立即开 `chore/legacy-cleanup` PR 处理，特别是 L-2 必须有专项并发测试。

### 模块外的 follow-up
- **F1**：`submit/router.py` 的 `prefix="/v1"` 路径 bug（导致 `/api/v1/v1/...`）
- **F2**：submit 端点改用真 `vote_token` 校验（当前仅按 `meta.vote_id` 加锁，存在鉴权空洞——本 PR 把 vote_token 签发就位了，下一步等 submit 接入）
- **F3**：thbwiki / qq / patchyvideo SSO 接入
- **F4**：MongoDB → PostgreSQL 历史用户数据回填

完整 follow-up 见 `docs/superpowers/specs/2026-04-27-user-auth-{design,implementation-report,open-issues}.md` 与 `docs/operations/cicd-pipeline.md`。

---

## 兼容性说明（重要）

- **首次部署到全新数据库：** CI 部署链路自动 `alembic upgrade head`；本地开发需要 `DEBUG=true` 启动一次让其余表（raw_*/character/music/cp/questionnaire）由 `init_db()` create_all 建出来。完整流程见 `docs/architecture/database-schema-management.md` §四
- **首次部署到已有数据库（线上现有部署）：** `user` / `activity_log` 表已存在，需要先 `alembic stamp 0001` 把现状标记为已迁移到 0001，再 `alembic upgrade head`
- **配置变更：**
  - 必须新增 `ALIYUN_PNVS_*` + `ALIYUN_DM_*` 全套配置（Apollo 推荐）
  - 调用 `send-sms-code` / `send-email-code` 时若配置缺失会得 `500 ALIYUN_NOT_CONFIGURED`
- **CHECK 约束变更：** `user.at_least_one_identifier` 从 `phone OR email IS NOT NULL` 放宽为 `removed = TRUE OR phone OR email IS NOT NULL`，需要 `alembic upgrade head` 应用

---

## Commit history

按 CLAUDE.md §10「小而完整」原则拆分：

```
469dfd3 docs: standardize date metadata and add docs/README.md index
c75f552 fix(user): address 4 review-driven issues introduced by this PR
7f71518 docs(architecture): add database-schema-management roadmap
b7b0ff5 docs(cicd): clarify trigger conventions; YAML vs team workflow
fd459fa fix(user): gate init_db behind DEBUG; wipe credentials on remove-voter
9bd2b02 feat(ci): wire alembic upgrade head into test and deploy stages
913ceab docs(ops): add Aliyun onboarding guide for production launch
bec66fb docs: add user-auth implementation report
8eba215 chore: remove unused Redis import from email_code
4e6822e docs(user): mark migration phases done; record CHECK relaxation; add fakeredis dep
1d1869d test(user): add unit, integration, and contract test suites
365517d feat(user): rewrite schemas, service, dao, deps, and router
f6f6787 feat(common): add EmailCodeService and SmsCodeService
b1a0206 feat(common): add Aliyun PNVS and DM SMTP clients
f62a533 feat(db): introduce Alembic with baseline migration for user and activity_log
2b62414 refactor(security): change vote_token subject from vote_id to user_id
45d75b7 chore: clean legacy folders and consolidate docs into docs/
```

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
