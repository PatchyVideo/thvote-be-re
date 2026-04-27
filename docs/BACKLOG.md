# 后续开发 BACKLOG（单一仪表盘）

> 创建日期：2026-04-27
> 最后更新：2026-04-27

把散落在 5 份文档里的 follow-up 收拢到这里。**这是仪表盘，不是真理来源**——每项的上下文还在原文档里，本表只给一行摘要 + 跳转。

如果新发现 follow-up，**两件事都要做**：（1）写进对应主题的源文档；（2）在本表加一行。

---

## 状态总览（B-001..B-027）

| 编号 | 主题 | 严重度 | 可并行做？ | 源文档 |
|---|---|---|---|---|
| **B-001** | 把 `raw_*` / character / music / cp / questionnaire 纳入 Alembic（baseline `0002`） | 中 | 🟢 可立即做 | [schema-mgmt §三阶段 2](./architecture/database-schema-management.md) / spec §九 F-impl-5 |
| **B-002** | submit 模块 `prefix="/v1"` 路径 bug（导致 `/api/v1/v1/...`） | 低 | 🟢 可立即做 | [design §九 F1](./superpowers/specs/2026-04-27-user-auth-design.md) |
| **B-003** | submit 端点改用真 `vote_token` 校验（当前仅靠 `meta.vote_id` 加锁，存在鉴权空洞） | 高 | 🟡 等本 PR merge | [design §九 F2](./superpowers/specs/2026-04-27-user-auth-design.md) |
| **B-004** | 祖传 L-1：CORS `allow_origins=["*"]` + `allow_credentials=True`，未来改 reflected origin 即变 CSRF 入口 | 中 | 🟢 可立即做 | [open-issues §四 L-1](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-005** | 祖传 L-2：`rate_limit.py` 非原子，登录 5/60s 限流可被并发绕过——**实际是安全 backlog** | **高** | 🟢 可立即做 | [open-issues §四 L-2](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-006** | 祖传 L-3：`logging.basicConfig` 重复调用（merge 残留） | 低 | 🟢 可立即做 | [open-issues §四 L-3](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-007** | thbwiki / qq / patchyvideo SSO 接入；落地后 VoterFE 的 `thbwiki/patchyvideo` 字段切真值 | 中 | 🟡 等本 PR merge（VoterFE 是新结构） | [design §九 F3](./superpowers/specs/2026-04-27-user-auth-design.md) |
| **B-008** | MongoDB → PostgreSQL 历史用户数据回填脚本 | 中 | 🟢 可立即做（独立 scripts/ 目录） | [design §九 F4](./superpowers/specs/2026-04-27-user-auth-design.md) |
| **B-009** | trusted proxies / `X-Forwarded-For` 处理（`get_client_ip` 当前只信 `request.client.host`） | 中 | 🟡 等本 PR merge | [design §九 F5](./superpowers/specs/2026-04-27-user-auth-design.md) |
| **B-010** | 测试覆盖率门禁切到 `fail_under=80` | 低 | 🟡 等本 PR merge + 模块稳定 1-2 sprint | [design §九 F6](./superpowers/specs/2026-04-27-user-auth-design.md) / spec §九 |
| **B-011** | SSO 落地后移除 `User.at_least_one_identifier` CHECK 约束 | 低 | 🔴 阻塞于 B-007 | [design §九 F7](./superpowers/specs/2026-04-27-user-auth-design.md) |
| **B-012** | `update-password` 单独限流（per user_id 5 req/300s）；当前与其他 update-* 共用桶，弱密码可日均 7200 次爆破 | 中 | 🟡 等本 PR merge | [open-issues §三 U-10](./superpowers/specs/2026-04-27-user-auth-open-issues.md) / design §九 F8 |
| **B-013** | 邮件/短信发送的"已发送"幂等性（避免阿里云调用成功但写日志失败造成的双发） | 低 | 🟡 等本 PR merge | [design §九 F9](./superpowers/specs/2026-04-27-user-auth-design.md) |
| **B-014** | `vote_token` 签发 3 个集成场景测试（已验证/未验证 × 投票期内/外） | 中 | 🟡 等本 PR merge | [open-issues §二 U-5](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-015** | `GET /me` 端点 TestClient 集成测试 | 中 | 🟡 等本 PR merge | [open-issues §二 U-6](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-016** | bcrypt → argon2 升级路径端到端集成测试 | 中 | 🟡 等本 PR merge | [open-issues §二 U-7](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-017** | Apollo 热更新与 `lru_cache` 客户端不兼容——文档化「改 Aliyun 配置必须重启容器」或加 `reload()` | 中 | 🟢 可立即做（仅文档变体） | [open-issues §三 U-8](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-018** | `_safe_log` 失败无可见性——加 `audit_log_failures_total` 计数器 + `/health` degraded 状态 | 中 | 🟡 等本 PR merge | [open-issues §三 U-9](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-019** | 错误响应 `{"detail":"..."}` 与 Rust 的 `{"error":"...","service":"..."}` 不一致 | 低 | 🟡 等本 PR merge / 等前端反馈 | [open-issues §三 U-11](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-020** | mypy 在 CI 不是硬门禁；先清现存告警，再去掉 `\|\| true` | 低 | 🟢 可立即做 | [open-issues §三 U-12](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-021** | Pydantic V1 弃用 API（`Field(..., env="X")`）→ V2（`SettingsConfigDict` + `validation_alias`） | 低 | 🟢 可立即做 | [open-issues §三 U-13](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-022** | 给 CI 加 PG-only 契约测试：插两行同 email 的 user，断言 partial unique index 抛 IntegrityError | 低 | 🟢 可立即做 | [open-issues §三 U-14](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-023** | `tests/integration/conftest.py` 的 `pytest.importorskip("fakeredis")` 改为硬 `import` | 低 | 🟢 可立即做 | [open-issues §三 U-15](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-024** | `UserDAO.save()` 加 `session.merge()` 防 detached instance 静默 no-op | 低 | 🟡 等本 PR merge | [open-issues §三 U-18](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-025** | 移除 `init_db()` 与 DEBUG 后门，改为 `ensure_schema_ready()` 失败立即 raise | 中 | 🔴 阻塞于 B-001（先把所有表纳入 Alembic） | [schema-mgmt §三阶段 3](./architecture/database-schema-management.md) |
| **B-026** | DB 治理纪律：PR 模板 model 改动提示 / CI `alembic check` / `db_model 改动必须有 migration` 检查 | 低 | 🔴 阻塞于 B-025 | [schema-mgmt §三阶段 4](./architecture/database-schema-management.md) |
| **B-027** | `pylint.yml` 与 `deploy-test.yml` lint 重复，删一个 + 把另一个改硬失败 | 中 | 🟢 可立即做（与 B-020 一起做最划算） | [cicd-pipeline §五 F-cicd-1+4](./operations/cicd-pipeline.md) |

---

## 🟢 可立即并行做（13 项，独立于本 PR）

按建议优先级排序，不影响当前 PR 评审：

| 编号 | 一句话 | 估时 |
|---|---|---|
| **B-005** ⚡ | 祖传 L-2：限流原子化（**阻塞了登录限流的安全保证**，是当前最高 ROI 的安全修复） | 半天（含 Lua 脚本 + 并发测试） |
| **B-001** | Alembic 第二个 baseline 把 raw_*/character/music/cp/questionnaire 纳入 | 半天（autogenerate + 手审 + 已有部署 stamp 步骤） |
| **B-002** | submit `/v1` prefix bug（一行改动 + 测试） | 30 分钟 |
| **B-008** | MongoDB → PG 数据回填脚本设计（独立 scripts/，不动主代码） | 1-3 天（看数据量与边界） |
| **B-006** | 祖传 L-3：删 `main.py` 重复 `logging.basicConfig` | 5 分钟 |
| **B-004** | 祖传 L-1：CORS 收紧到具体域名列表 | 30 分钟 + 前端域名清单 |
| **B-020** | mypy 在 CI 改硬门禁前先清告警 | 半天-1 天（看现存告警量） |
| **B-027** | 删 `pylint.yml`，把 deploy-test 的 flake8 改硬失败（与 B-020 合并一个 PR 性价比最高） | 同上 |
| **B-021** | Pydantic V1→V2 配置迁移（清 20 条 deprecation 告警） | 半天 |
| **B-022** | CI PG-only 契约测试：partial unique index 行为验证 | 1 小时 |
| **B-023** | `importorskip` → 硬 import | 5 分钟 |
| **B-017** | Apollo + `lru_cache` 限制文档化（仅 docs） | 30 分钟 |
| **B-007** | SSO 接入**设计稿**（不动代码，先写 spec） | 1 天 |

> ⚡ = 强烈建议作为本 PR 合并后的**第一个 follow-up PR**

## 🟡 等本 PR merge 后做（10 项）

这些都依赖本 PR 引入的代码（VoterFE 结构、新端点、`vote_token` 主体改动等）：

- **B-003** submit 接 vote_token 校验（依赖 vote_token 主体已改 user_id）
- **B-007** SSO 实现阶段（依赖 VoterFE 的 thbwiki/patchyvideo 字段）
- **B-009** trusted proxies（依赖 `get_client_ip`）
- **B-010** 覆盖率门禁切硬（依赖模块运行 1-2 sprint 稳定）
- **B-012** `update-password` 单独限流（依赖新端点）
- **B-013** 发送幂等性（依赖新发送链路）
- **B-014/015/016** 新测试（依赖新代码）
- **B-018** 审计可见性（依赖 `_safe_log`）
- **B-019** 错误响应统一（依赖新端点契约）
- **B-024** DAO `merge()` 加固（依赖新 DAO）

## 🔴 战略 / 阻塞链（2 项）

- **B-011** 移除 `at_least_one_identifier` 约束 ← 阻塞于 **B-007** SSO 落地
- **B-025** 移除 `init_db()` ← 阻塞于 **B-001** 把全部表纳入 Alembic
- **B-026** DB 治理纪律 ← 阻塞于 **B-025**

---

## 推荐的下一个 PR（在本 PR merge 之前可立即开工）

**首选 `B-005` 限流原子化**——理由：
- 是当前最高 ROI 的安全修复（登录限流的安全闭合）
- 完全独立于 feat/user-and-verify 的代码（只改 `src/common/middleware/rate_limit.py`）
- 可以同时给 submit / login / mutation 端点都受益
- 改动小、并发测试可写，PR 审核成本低

**次选 `B-001` Alembic baseline 0002**——理由：
- 现在 schema 治理路线图阶段 2 的入口
- 只新增 migration 文件 + 已有部署 stamp 文档，不改业务代码
- 与本 PR 完全无冲突

**B-002 submit /v1 prefix bug** 适合作为 30 分钟的暖手任务在两个大 PR 之间穿插。

---

## 维护规则

- **新发现 follow-up：** 写进对应主题的源文档；在本表加一行；编号顺延 B-028, B-029...
- **某项完成：** 不删除——把"严重度"改为 ✅ 已完成 + 完成日期 + commit hash / PR #
- **三个状态分组**（🟢🟡🔴）随完成情况调整：依赖项落地后，相关项可以从 🔴 升到 🟡 或 🟢
- 本表过 50 项时考虑分类拆文件（按主题：security backlog / schema backlog / test backlog 等），但目前规模够小不必拆
