# 用户与认证模块实施报告

> 实施日期：2026-04-27
> 分支：`feat/user-and-verify`
> 设计文档：[`2026-04-27-user-auth-design.md`](./2026-04-27-user-auth-design.md)

本文记录设计文档落地过程中的实际改动、实施期间发现的具体问题，以及交付时仍未做完的 Follow-up。所有改动均按 CLAUDE.md §10 的小提交粒度落在 `feat/user-and-verify` 分支。

---

## 一、交付内容

### 1.1 提交序列（9 个 commit，主线小步前进）

```
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

### 1.2 新增/修改文件清单

**新增：**
- `alembic.ini`、`alembic/env.py`、`alembic/script.py.mako`、`alembic/versions/0001_initial_user_and_activity_log.py`
- `src/common/aliyun/{__init__,pnvs_client,dm_smtp_client}.py`
- `src/common/verification/{__init__,email_code,sms_code}.py`
- `src/apps/user/deps.py`
- `tests/conftest.py` 与 `tests/{unit,integration,contract}/` 全套
- `docs/CHANGELOG.md`、`docs/superpowers/specs/2026-04-27-user-auth-design.md`、本报告

**重写：**
- `src/apps/user/{schemas,service,dao,router}.py`

**修改：**
- `src/common/security/jwt.py`（vote_token subject vote_id → user_id）
- `src/apps/user/utils/security.py`（同步签名变更）
- `src/db_model/user.py`（CHECK 约束放宽，详见 §二.1）
- `requirements.txt`（新增 alembic、alibabacloud_*、freezegun、fakeredis）
- `.gitignore`（忽略 `.claude/` 本地状态）

**移除：**
- `src/app/`（仅含 .pyc 的旧目录残留）
- `src/models/__init__.py`（空壳，实际模型在 `src/db_model/`）

### 1.3 新交付 API（`/api/v1/user/*`，全部 POST 除非另注）

| 端点 | 用途 |
|---|---|
| `send-email-code` | 本地生成 6 位码 → Redis（TTL 3600s）+ guard（120s）→ Aliyun DM SMTP |
| `send-sms-code` | 阿里云 PNVS `SendSmsVerifyCode` 全托管 |
| `login-email-password` | 邮箱+密码（含 bcrypt → argon2 升级） |
| `login-email` | 邮箱+验证码，新用户自动注册 |
| `login-phone` | 手机+PNVS 验证码，新用户自动注册 |
| `update-email` | 解 token + 消费验证码 + 唯一性 + 更新 |
| `update-phone` | 同上 |
| `update-nickname` | 解 token + 更新 |
| `update-password` | 首次设密免旧密码；已有密码必须验旧 |
| `token-status` | session_token 心跳校验 |
| `remove-voter` | 软删除 + 清空 email/phone |
| `GET /me` | 用 `Authorization: Bearer …` 取当前 VoterFE（唯一非 Rust 对齐端点） |

---

## 二、实施期间发现并就地解决的具体问题

### 2.1 `at_least_one_identifier` CHECK 约束与软删除冲突

**现象：** 集成测试 `test_remove_voter_clears_identifiers_and_blocks_lookup` 触发 sqlite `IntegrityError: CHECK constraint failed: at_least_one_identifier`。

**根因：** 设计文档原本保留 Rust 没有的约束 `phone_number IS NOT NULL OR email IS NOT NULL`。但 `remove-voter` 的语义是"清空 email/phone 释放给他人复用"——同时 NULL 必然违反约束。Rust 没有该约束所以没暴露这个矛盾；sqlite 强制执行 CHECK，问题被测试捕获。

**修复：** 约束放宽为 `removed = TRUE OR phone_number IS NOT NULL OR email IS NOT NULL`——活动用户仍必须有标识符，软删行允许同时 NULL。改动落在 `src/db_model/user.py` 与 baseline migration。

**影响：** 设计文档 §五.2 与 §十一 已对应更新。已有部署执行 `alembic upgrade head` 即可。

### 2.2 PNVS SDK 模块级 import 与单测隔离

**现象：** 单测试图覆盖 `_parse_send_response` / `_parse_check_response` 时，模块顶层若直接 `from alibabacloud_dypnsapi20170525 import ...`，未安装 SDK 的环境会在 collect 阶段失败。

**修复：** SDK import 全部下沉到 `_ensure_client()` 与 `send_*` / `check_*` 方法体内。这样：
- 模块加载不依赖 SDK
- 单测可绕过 `_ensure_client` 直接验证响应解析路径
- `tests/unit/test_pnvs_client.py` 用 `SimpleNamespace` 构造 fake response 即可

### 2.3 测试用 Redis 隔离

**问题：** 集成测试如果连真 Redis，在没有 Redis 的开发机上无法跑；但 spec 又要求测试覆盖 guard 防刷、code TTL 等行为。

**方案：** 引入 `fakeredis` 作为测试依赖，conftest 的 `patch_redis` autouse fixture 把 `src.common.redis.get_redis` 替换为 fake。CI 真实 Redis 与测试 fake 行为兼容（fakeredis 实现 redis 协议子集）。

### 2.4 `_authenticate` 双形态遗留

**问题：** 我最初写了一个 sync placeholder + async helper 的双轨结构，造成 service 里 `update_*` 方法写成 `self._authenticate(token)` 但实际是要 `await`。

**修复：** 合并为单一 `async def _authenticate`，统一在所有调用点改成 `await self._authenticate(...)`。落入 commit `365517d`。

### 2.5 `vote_id` vs `user_id` 命名冲突

**情形：** `submit/router.py` 与 `submit/dao.py` 大量使用 `vote_id` 作为**单次提交的 UUID**，与 JWT 的 `vote_token` 主体（应为用户身份）是完全不同的概念。重命名 JWT 里的字段时不能影响 submit。

**确认：** 只有 `src/apps/user/utils/security.py` 包装层引用了 JWT 的 `create_vote_token`；已同步改为 `user_id` 形参。submit 模块的 `vote_id` 完全不动。该 follow-up 由 spec §九 F2 跟踪（让 submit 端点真校验 vote_token）。

### 2.6 Python 版本/路径混乱

**情形：** 验证时 `pip install` 默认装到 `~/.local/lib/python3.10`，而 `python` 解析到 miniconda3 的 3.13——结果 `import strawberry` 在不同入口表现不一致。

**应对：** 统一用 `python -m pip install` 把依赖装到当前活动 Python 下。这是验证环境的临时工作流，不影响交付。CI 用的是固定 Python 3.12 镜像，不会复现此问题。

---

## 三、对设计的偏离 / 在实施中固化的决策

| 项 | 设计文档说法 | 实际落地 | 原因 |
|---|---|---|---|
| `at_least_one_identifier` 约束 | 保留 | **放宽**（允许 removed=TRUE 同时 NULL） | 见 §二.1 |
| Redis 测试策略 | "真 Redis（CI 已就位）" | **fakeredis** | 方便本地、CI 双跑；fakeredis 协议兼容真 Redis 子集 |
| ActivityLog 写入 | "独立事务" | **独立 session**（共享 engine） | 等价语义，更简单 |
| `_authenticate` 形态 | 未指定 | **async 单形态** | 见 §二.4 |
| SDK import 时机 | 未指定 | **方法体内 lazy** | 见 §二.2 |
| 速率限制 key 形态 | 未指定 | `login-{ip}` 与 `user-mut-{user_id}` | 复用现有 `rate_limit(uid, ...)` 接口 |

---

## 四、未做的事 / Follow-up

完整 Follow-up 见设计文档 §九 F1-F9。本期**新发现**值得记一笔的：

| 编号 | 项目 | 备注 |
|---|---|---|
| F-impl-1 | submit 模块的 `prefix="/v1"` bug | 与 spec F1 同条；本次未动 submit |
| F-impl-2 | submit 端点接 vote_token 校验 | 与 spec F2 同条；vote_token 签发已就位但 submit 还没消费 |
| F-impl-3 | 全局 AppException → HTTPException 处理器 | 当前在 router 各端点显式 try/except + `_raise_http`；可统一抽到 `app.add_exception_handler(AppException, ...)` 简化路由代码 |
| F-impl-4 | `tests/integration` 在 CI 上从 sqlite/fakeredis 切回 PG/真 Redis | 当前 conftest 用内存 sqlite + fakeredis；CI 已经起了 PG/Redis 服务，可补一个 `INTEGRATION_USE_REAL_BACKEND=1` 开关 |
| F-impl-5 | Alembic 把现有 `raw_*` / `character` / `music` / `cp` / `questionnaire` 表纳入版本管理 | 本期 baseline 只囊括 user + activity_log；其余表仍走 `init_db()` 的 `create_all` |
| F-impl-6 | 阿里云真接口 smoke 验证 | 自动化里坚决不打真阿里云；需手工/staging 跑一遍确认 PNVS / DM 配置正确 |

---

## 五、CI/CD 兼容性

- `.github/workflows/deploy-test.yml` 与 `deploy-prod.yml` 不需修改：lint→test→build→deploy 流水线沿用，新增的 `tests/{unit,integration,contract}` 会被既有的 `pytest` 命令自动捕获。
- 新增依赖（`alembic`、`alibabacloud_*`、`freezegun`、`fakeredis`）已写入 `requirements.txt`，CI 的 `pip install -r requirements.txt` 步骤会自动拉取。
- 测试在没有外部 Postgres/Redis 时仍可运行（fakeredis + in-memory sqlite），不阻塞快速本地迭代。

## 六、上线 checklist

- [ ] 在测试环境 Apollo / `.env.test` 配齐 `ALIYUN_PNVS_*` 与 `ALIYUN_DM_*` 全套变量
- [ ] 在测试环境跑 `alembic upgrade head` 把约束放宽 + baseline 应用
- [ ] 用 `curl` 触发 `send-sms-code` + `login-phone` 的真实链路（需要真手机号）
- [ ] 用 `curl` 触发 `send-email-code` + `login-email` 的真实链路（需要可达邮箱）
- [ ] 验证 `vote_token` 在配置的投票期内能被 submit 端点解码（虽然 submit 还没接，但 JWT 本身可以校验）
- [ ] 确认日志中没有验证码明文 / 密码 / token 泄露
- [ ] 跑一轮 codecov，新增模块行覆盖应 ≥ 85%
