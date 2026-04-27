# 用户与认证模块 — 已知问题与待办

> 创建日期：2026-04-27
> 主体范围：`feat/user-and-verify` 分支上线前的代码级问题
> 关联：[设计文档](./2026-04-27-user-auth-design.md) / [实施报告](./2026-04-27-user-auth-implementation-report.md) / [运维文档](../../operations/cicd-pipeline.md)

本文用于在 PR 前/后跟踪本次用户与认证模块**还没做完**或**做完了但需要持续关注**的问题。每条带：编号、严重度、状态、修复方案、关联代码/文档。落地一条，划掉一条；新发现的问题随时往里加。

---

## 一、PR 前已修复（本次 ✅）

| 编号 | 问题 | 修复 commit |
|---|---|---|
| **U-1** | `init_db()` 与 Alembic 并存导致 schema 漂移：lifespan 启动时 `Base.metadata.create_all` 与 `alembic upgrade head` 互相覆盖，已有部署可能出现「字段在 model 里有、表里没有、alembic_version 也漂着」的不一致 | `chore(boot): gate init_db() behind DEBUG mode` —— 默认部署不再调用，仅 `DEBUG=true` 时为本地开发提供 create_all 能力 |
| **U-4** | `remove-voter` 软删除**没清密码哈希**：`password_hash` 与 `legacy_salt` 在 removed=True 行里永久残留，DB 泄露后可与第三方撞库表交叉破解，违反 GDPR / 个保法 §47 | `fix(user): wipe password_hash and legacy_salt on remove-voter` —— 同步加 `tests/integration/test_remove_voter_wipes_password_hash_and_legacy_salt` 守护 |

---

## 二、PR 前待修（建议在 review 前做完）

| 编号 | 问题 | 严重度 | 估时 | 状态 |
|---|---|---|---|---|
| **U-5** | `vote_token` 签发逻辑没有集成测试覆盖。当前只测了 JWT 底层 round-trip，没断言「`(email_verified or phone_verified) and now in [start, end]`」三组分支在登录响应里的实际表现 | 中 | 20 min | 未做 |
| **U-6** | `GET /me` 端点零测试覆盖。它是本次唯一非 Rust 对齐的端点，反而最值得契约测试 | 中 | 10 min | 未做 |
| **U-7** | bcrypt → argon2 升级路径只有单测，没有「带 legacy_salt 的用户走 `login-email-password` 后 hash 真的被升级、salt 被清空」的集成测试 | 中 | 15 min | 未做 |

---

## 三、PR 后再做（不阻塞合并，但要进 backlog）

| 编号 | 问题 | 严重度 | 修复思路 |
|---|---|---|---|
| **U-8** | `Settings`、`get_pnvs_client`、`get_dm_smtp_client`、`get_email_code_service`、`get_sms_code_service` 全是 `lru_cache(maxsize=1)`，**任何 Apollo 热更新都不会传播到这些客户端**。当前 Apollo 实现也只 startup 拉一次，所以现状一致；但未来给 Apollo 加 long-poll 时就会暴露 | 中 | 文档化为「改 Aliyun 配置必须重启容器」（已在 `cicd-pipeline.md` 体现）；或给客户端加 `reload()` |
| **U-9** | `_safe_log` 在审计写入失败时**只 `logger.exception`**，没有进程级计数器、没有降级状态暴露给 `/health`。审计长时间静默失败时事后追溯会变盲 | 中 | 加 `audit_log_failures_total` 计数；持续失败 N 分钟后 `/health` 返回 degraded |
| **U-10** | `update-password` 与其他 update-* 共享 5 req/60s per user_id 限流。攻击者拿到 session_token 后一天 7200 次旧密码尝试，足以爆破弱密码 | 中 | 给 `update-password` 单独加 `pw-mut-{user_id}` 5 req/300s（spec §九 F8 已记录） |
| **U-11** | 错误响应结构 `{"detail":"INCORRECT_VERIFY_CODE"}` 与 Rust 的 `{"error":"...","service":"user-manager"}` 不一致 | 低 | 上 `add_exception_handler(HTTPException, ...)` 统一形态；前端没投诉前可不做 |
| **U-12** | `mypy` 从未在 CI 跑过；当前 lint job 仅 `flake8 src/ \|\| true` 软门禁 | 低 | 在 deploy-test.yml lint job 加 `mypy src/`；先把现存告警清零，再去掉 `\|\| true` |
| **U-13** | `Settings` 大量使用 Pydantic V1 的 `Field(..., env="X")`，pytest 输出有 20 条 `PydanticDeprecatedSince20` 告警 | 低 | 切到 V2 的 `model_config = SettingsConfigDict(...)` + `validation_alias`；属于先前代码的清理工作 |
| **U-14** | 测试里用 in-memory sqlite + fakeredis；sqlite 不强制 `postgresql_where` 表达式，partial unique index 行为没被实际验证。CI 现在会跑 `alembic upgrade head` 在真 PG 上做 DDL 烟测，但**唯一索引的运行时行为**仍然没有专门测试 | 低 | 给 CI 加一个 PG-only 的契约测试：插两行同 email 的 user，断言第二个 INSERT 抛 IntegrityError |
| **U-15** | `tests/integration/conftest.py` 用 `pytest.importorskip("fakeredis")`，万一 `fakeredis` 漏装，所有集成测试**静默 skip**，CI 也不会报错 | 低 | 改为 `import fakeredis` 硬依赖；`fakeredis` 已经进 `requirements.txt`，没理由再可选 |

---

## 四、与设计/实施文档的对照

下表把本文编号映射到已有 follow-up 列表，避免重复跟踪：

| 本文编号 | spec §九 / 实施报告 | cicd-pipeline.md §五 |
|---|---|---|
| U-1 | F-impl-10 | F-cicd-3 |
| U-4 | （新发现） | — |
| U-5..U-7 | （新发现） | — |
| U-8 | （新发现） | — |
| U-9 | （新发现） | — |
| U-10 | F8 / spec §九 | — |
| U-12 | F-impl-8 | F-cicd-1 / F-cicd-4 |
| U-13 | （新发现） | — |
| U-14 | （新发现） | — |
| U-15 | （新发现） | — |

**维护规则：**
- 修复一条 U-N 时，把"状态"列改为「已修复 + commit hash + 日期」**而不是删除**——保留追溯
- 新发现问题随时往 §三 加（编号顺延 U-16, U-17 …）；如果是 PR 前发现的就放 §二
- 大类（CI/CD、文档、操作）的问题分别放各自文档；本文只收录**用户与认证模块代码层面**的问题
