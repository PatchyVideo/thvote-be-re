# 用户表与认证模块设计 (thvote-be-re)

> 创建日期：2026-04-27
> 作者：Claude（brainstorming 流程产物）
> 适用范围：`thvote-be-re`（Python/FastAPI），对齐 `thvote-be/user-manager`（Rust/Actix）
> 关联文档：[`docs/migration/user-manager.md`](../../migration/user-manager.md)

---

## 一、目标与范围

### 在范围内
- 把 `thvote-be/user-manager` 的核心用户与认证逻辑迁移到 `thvote-be-re/src/apps/user/`，**数据结构与端点契约对齐 Rust**。
- 邮件验证码：本地生成 6 位码 + Redis（`email-verify-{email}` TTL 3600s + guard `email-verify-guard-{email}` TTL 120s）+ Aliyun DirectMail SMTP 投递。
- 手机短信验证码：**全托管走阿里云号码认证服务（PNVS）**，使用 `SendSmsVerifyCode` / `CheckSmsVerifyCode`，验证码不出阿里云、不进我方 Redis、不写日志明文。
- 登录响应同时签发 `session_token` 与 `vote_token`（投票期内 + 已验证 phone 或 email）。
- 引入 Alembic 数据库迁移工具，把 `User` 与 `ActivityLog` 模型纳入版本管理。
- 用户敏感端点接入既有速率限制中间件。
- 所有写操作落 `ActivityLog` 审计表（best-effort，不阻断主请求）。

### 明确不在范围内（见 §九 Follow-up）
- `submit` 模块改用真 `vote_token` 校验
- `submit/router.py` 现有 `prefix="/v1"` 路径 bug 修复
- thbwiki / qq / patchyvideo SSO 接入
- MongoDB → PostgreSQL 历史用户数据回填脚本
- `X-Forwarded-For` / trusted proxies 处理
- 测试覆盖率硬性门禁切换（`fail_under=80`）

---

## 二、阿里云 PNVS 关键事实（设计前提）

来源：阿里云官方文档（[SendSmsVerifyCode](https://help.aliyun.com/zh/pnvs/developer-reference/api-dypnsapi-2017-05-25-sendsmsverifycode), [CheckSmsVerifyCode](https://help.aliyun.com/zh/pnvs/developer-reference/api-dypnsapi-2017-05-25-checksmsverifycode), [个人开发者免资质接入](https://help.aliyun.com/zh/pnvs/use-cases/sms-verify-for-individual-developers)）。

| 维度 | 行为 |
|---|---|
| 资质 | 个人实名即可，无需短信签名/模板申请，使用阿里云**赠送签名 + 赠送模板** |
| 验证码生命周期 | 阿里云侧生成、存储、过期、防刷，TTL 由 `ValidTime` 控制（默认 300s，本项目按配置 `ALIYUN_PNVS_VALID_TIME`） |
| 防刷 | `Interval` 参数控制同号码重发间隔（默认 60s，本项目按 `ALIYUN_PNVS_INTERVAL`） |
| 校验 | `CheckSmsVerifyCode` 返回 `Code` + `Model.VerifyResult`：**`Code=="OK"` 仅代表 API 调用成功**，真正结果以 `VerifyResult == "PASS"` 为准；`UNKNOWN` 包含输错/过期/已用过 |
| `SchemeName` | 发送与校验**必须一致**，本项目固定取 `ALIYUN_PNVS_SCHEME_NAME` |
| `ReturnVerifyCode` | 我方设为 `False`，避免明文码进入 Python 内存与日志 |
| Python SDK | `alibabacloud_dypnsapi20170525` + `alibabacloud_tea_openapi` |

`config.py` 中已有的全部 PNVS 字段（`aliyun_pnvs_access_key_id/secret/endpoint/region_id/scheme_name/sms_sign_name/sms_template_code/code_length/valid_time/interval`）一一对应 PNVS API 入参，无需新增配置。

---

## 三、模块结构

```
src/
├─ apps/user/
│   ├─ router.py              # 12 个端点（11 个对齐 Rust + 1 个 GET /me）
│   ├─ service.py             # UserService：业务编排
│   ├─ dao.py                 # UserDAO + ActivityLogDAO
│   ├─ schemas.py             # 请求/响应 Pydantic 模型 + Meta + VoterFE
│   └─ deps.py                # FastAPI 依赖：session_token → User
│
├─ common/
│   ├─ verification/          # 新增
│   │   ├─ __init__.py
│   │   ├─ email_code.py      # EmailCodeService（本地生成 + Redis）
│   │   └─ sms_code.py        # SmsCodeService（薄封装 PNVS）
│   ├─ aliyun/                # 新增
│   │   ├─ __init__.py
│   │   ├─ pnvs_client.py     # AliyunPnvsClient
│   │   └─ dm_smtp_client.py  # AliyunDmSmtpClient
│   └─ security/jwt.py        # 修改：create_vote_token 主体改为 user_id
│
└─ alembic/                   # 新建
    ├─ alembic.ini
    ├─ env.py
    └─ versions/
        └─ 0001_initial_user_and_activity_log.py
```

### 职责边界（呼应 CLAUDE.md §5/§6）
- **router.py** 不写业务逻辑，只做参数解析、依赖解 token、调 service、转响应。
- **service.py** 业务流程编排，所有事务边界在这层。
- **dao.py** 纯 ORM 操作。
- **verification/** + **aliyun/** 通过依赖注入持有，方便单测 mock。
- **deps.py** 把"从 `user_token`/请求体里解出 User"统一为 FastAPI dependency。

---

## 四、路由

总前缀 `/api/v1/user/` 已由 `src/api/rest/v1/__init__.py` 注册。所有动作名扁平、与 Rust 一一对应。

| Rust 端点 | thvote-be-re 端点 | 鉴权 |
|---|---|---|
| `POST /v1/login-email-password` | `POST /api/v1/user/login-email-password` | 公开 |
| `POST /v1/login-email` | `POST /api/v1/user/login-email` | 公开 |
| `POST /v1/login-phone` | `POST /api/v1/user/login-phone` | 公开 |
| `POST /v1/send-email-code` | `POST /api/v1/user/send-email-code` | 公开 |
| `POST /v1/send-sms-code` | `POST /api/v1/user/send-sms-code` | 公开 |
| `POST /v1/update-email` | `POST /api/v1/user/update-email` | user_token |
| `POST /v1/update-phone` | `POST /api/v1/user/update-phone` | user_token |
| `POST /v1/update-nickname` | `POST /api/v1/user/update-nickname` | user_token |
| `POST /v1/update-password` | `POST /api/v1/user/update-password` | user_token |
| `POST /v1/user-token-status` | `POST /api/v1/user/token-status` | user_token |
| `POST /v1/remove-voter` | `POST /api/v1/user/remove-voter` | user_token |
| —（无 Rust 对应） | `GET /api/v1/user/me` | session_token（`Authorization: Bearer …`） |

`GET /me` 是本期**唯一非 Rust 对齐的端点**，作为 `GET /{user_id}` 半成品的安全替代。响应体直接是 `VoterFE`（不返回任何 token）。鉴权方式用 `Authorization: Bearer <session_token>` header（这是只读、幂等接口，按 REST 习惯放 header 比放请求体更合适，**刻意偏离** Rust 风格）。

### 旧端点处置（本期同步移除）
- `POST /api/v1/user/login`（半成品 `LoginRequest{username,password}`）→ **删除**
- `POST /api/v1/user/login/email` → **替换**为 `login-email-password`
- `POST /api/v1/user/register` → **删除**（Rust 无独立注册，注册通过 `login-email`/`login-phone` 验证码登录的副作用完成）
- `GET /api/v1/user/{user_id}` → **改造**为 `GET /api/v1/user/me`，从 session_token 解出 user_id
- `DELETE /api/v1/user/{user_id}` → **删除**（由 `remove-voter` 软删除取代）

---

## 五、数据模型

### 5.1 表结构（无 DDL 变更）
`db_model/user.py` 与 `db_model/activity_log.py` 字段已完整对齐 Rust `Voter` / `voter_logs`，本期不改 DDL。

### 5.2 Alembic baseline migration（`0001_initial_user_and_activity_log.py`）
- `create_table('user')` 含全字段
- `create_table('activity_log')` 含全字段
- 索引：
  - `user.email` partial UNIQUE `WHERE email IS NOT NULL`
  - `user.phone_number` partial UNIQUE `WHERE phone_number IS NOT NULL`
  - `activity_log.user_id`
  - `activity_log.event_type`
  - `activity_log.created_at`
- CheckConstraint `at_least_one_identifier`（`phone_number IS NOT NULL OR email IS NOT NULL`）随表创建。**这条与 Rust 不一致**——Rust 允许两者都为空（thbwiki/qq SSO 注册）；本期保留约束，SSO 落地时再 migration 移除。记入"刻意保留的差异"。

### 5.3 Pydantic Schema（重写 `apps/user/schemas.py`）

```python
class Meta(BaseModel):
    user_ip: str
    additional_fingureprint: str | None = None    # 故意保留 Rust 的拼写错误，前端兼容

class VoterFE(BaseModel):
    username: str | None       # 来自 nickname
    pfp: str | None
    password: bool             # 是否已设密码
    phone: str | None
    email: str | None
    thbwiki: bool = False      # 永远 false，SSO 落地再切真值
    patchyvideo: bool = False  # 同上
    created_at: datetime

class LoginResponse(BaseModel):
    user: VoterFE
    session_token: str
    vote_token: str            # 不在投票期或未验证时为空字符串

# 请求 schema：LoginEmailPassword/Email/Phone, SendEmailCode/SmsCode,
#   UpdateEmail/Phone/Nickname/Password, TokenStatus, RemoveVoter
# 详见 §6 各端点流程
```

**两点决策：**
1. `user_token` 放在请求体（对齐 Rust），不走 `Authorization` header。
2. `additional_fingureprint` 拼写错误故意保留——Rust 已暴露，前端字段名不能不打招呼就改。

### 5.4 ActivityLog 写入映射

| 触发端点 | event_type | 关键字段 |
|---|---|---|
| `send-email-code` 成功 | `send_email` | `target_email`, `requester_ip`, `additional_fingerprint`，**不存验证码明文** |
| `send-sms-code` 成功 | `send_sms` | `target_phone`, `detail = "BizId={...}"`（PNVS 返回值），**不存码** |
| `login-email`/`login-phone` 注册分支 | `voter_creation` | `user_id`, `target_email`/`target_phone`, `new_value=nickname` |
| `login-*` 登录分支 | `voter_login` | `user_id`, `target_email`/`target_phone` |
| `update-email` | `update_email` | `user_id`, `old_value=旧 email`, `new_value=新 email` |
| `update-phone` | `update_phone` | `user_id`, `old_value`, `new_value` |
| `update-nickname` | `update_nickname` | `user_id`, `old_value`, `new_value` |
| `update-password` | `update_password` | `user_id`（不记密码任何信息） |
| `remove-voter` | `remove_voter` | `user_id` |

`token-status` 不写日志（高频调用会爆量）。

---

## 六、关键端点流程

### 6.1 `POST /api/v1/user/send-sms-code`
```
1. router → service.send_sms_code(phone, meta)
2. service:
   a. AliyunPnvsClient.send_sms_verify_code(
          phone_number=phone,
          sign_name=settings.aliyun_pnvs_sms_sign_name,
          template_code=settings.aliyun_pnvs_sms_template_code,
          template_param='{"code":"##code##"}',
          scheme_name=settings.aliyun_pnvs_scheme_name,
          code_length=settings.aliyun_pnvs_code_length,
          valid_time=settings.aliyun_pnvs_valid_time,
          interval=settings.aliyun_pnvs_interval,
          return_verify_code=False,
      )
   b. resp.code == "OK" 检查，错误码映射见 §七
   c. ActivityLog: send_sms（best-effort，独立事务，失败不阻断）
   d. 返回 EmptyResponse
```
**短信全程不接 Redis**；防刷、TTL、码生成/校验全在阿里云侧。

### 6.2 `POST /api/v1/user/login-email`
对齐 Rust `new_login.rs::login_email`：
```
1. EmailCodeService.consume(email, verify_code):
   - redis.GET email-verify-{email}
   - 不存在或不等 → INCORRECT_VERIFY_CODE
   - redis.DEL email-verify-{email}（一次性消费）

2. user = UserDAO.get_by_email(email)

3. 分支：
   [c1] user 存在 → 登录路径：
       user.email_verified = True；UserDAO.update；ActivityLog: voter_login
   [c2] user 不存在 → 注册路径：
       创建 User(id=uuid4, email, email_verified=True, nickname,
                  register_ip=meta.user_ip, ...)
       UserDAO.create；ActivityLog: voter_creation

4. session_token = create_session_token(user.id)

5. vote_token 签发判定：
   if (user.email_verified or user.phone_verified)
      and now in [vote_start, vote_end]:
       vote_token = create_vote_token(user_id=user.id, vote_start, vote_end)
   else:
       vote_token = ""

6. 返回 LoginResponse(user=VoterFE.from_orm(user), session_token, vote_token)
```

### 6.3 `POST /api/v1/user/update-password`
```
1. payload = decode_session_token(user_token) | INVALID_TOKEN
2. user = UserDAO.get_by_id(payload.user_id) | USER_NOT_FOUND（含 removed=True）
3. 分支：
   [c1] user.password_hash IS NULL（首次设密码）：忽略 old_password，直接 hash new
   [c2] 已有密码：
        old_password 为空 → OLD_PASSWORD_REQUIRED
        verify_any_password 失败 → INCORRECT_PASSWORD
        通过 → hash new
4. user.password_hash = new_hash; user.legacy_salt = None; UserDAO.update
5. ActivityLog: update_password（不记密码任何信息）
6. 返回 EmptyResponse
```

### 6.4 其他端点速览
| 端点 | 主要差异 |
|---|---|
| `login-email-password` | 跳过验证码，直接 `verify_any_password` + 登录路径，账号必须已存在 |
| `login-phone` | 同 6.2，`SmsCodeService.consume` 内部调 `AliyunPnvsClient.check_sms_verify_code`，看 `VerifyResult == "PASS"` |
| `send-email-code` | 同 6.1 模式但本地 6 位码 + Redis（key `email-verify-{email}` TTL 3600s, guard TTL 120s）+ Aliyun DM SMTP 发送 |
| `update-email`/`update-phone` | 解 token + 消费验证码 + 唯一性 + 更新 + 日志 |
| `update-nickname` | 解 token + 长度校验 + 更新 + 日志 |
| `token-status` | 解 token，有效返回 `{}`，无效 401 |
| `remove-voter` | 解 token + 可选验旧密码 + 软删（`removed=True`，清 email/phone）+ 日志 |

---

## 七、错误处理与外部依赖失败策略

### 7.1 业务错误字符串契约

| 错误字符串 | HTTP | 触发场景 |
|---|---|---|
| `INCORRECT_VERIFY_CODE` | 400 | 邮件码不匹配/不存在；PNVS `VerifyResult != "PASS"` |
| `REQUEST_TOO_FREQUENT` | 429 | 邮件 guard key 命中；PNVS 频率类业务码 |
| `USER_ALREADY_EXIST` | 409 | `update-email`/`update-phone` 唯一性冲突 |
| `INVALID_TOKEN` | 401 | session_token 解码失败/过期 |
| `INCORRECT_PASSWORD` | 400 | 密码校验失败 |
| `OLD_PASSWORD_REQUIRED` | 400 | 已设密码用户没传 old_password |
| `INVALID_PHONE` | 400 | PNVS `isv.MOBILE_NUMBER_ILLEGAL` |
| `INVALID_EMAIL` | 400 | Pydantic `EmailStr` 校验已覆盖；SMTP 拒收用户名段非法 |
| `USER_NOT_FOUND` | 404 | token 有效但 user 已 removed/不存在 |
| `SMS_SEND_FAILED` | 502 | PNVS 非业务类错误 |
| `EMAIL_SEND_FAILED` | 502 | SMTP 投递失败 |

错误字符串保持全大写下划线，对齐 Rust `ServiceError::new_error_kind`。所有 `except` 必须转成上述错误或 `logger.exception` 重抛。

### 7.2 外部依赖失败策略

| 依赖 | 失败类型 | 处理 |
|---|---|---|
| Aliyun PNVS (send) 网络/超时（5s） | 重试 1 次，仍失败 → `SMS_SEND_FAILED` 502，**不写 ActivityLog** |
| Aliyun PNVS (send) 业务错误 | `BUSINESS_LIMIT_CONTROL` → `REQUEST_TOO_FREQUENT`；`MOBILE_NUMBER_ILLEGAL` → `INVALID_PHONE`，不重试 |
| Aliyun PNVS (check) 网络/鉴权 | `SMS_SEND_FAILED` 502，用户可重试 |
| Aliyun PNVS (check) `VerifyResult == "UNKNOWN"` | `INCORRECT_VERIFY_CODE` 400 |
| Aliyun DM SMTP 失败 | 重试 1 次，仍失败 → `EMAIL_SEND_FAILED` 502，**Redis 已写 code 主动 DEL** |
| Redis 不可用 | `AppException("REDIS_UNAVAILABLE", 503)`，登录链路不降级 |
| PostgreSQL 唯一约束 | `update-email`/`update-phone` → `USER_ALREADY_EXIST` 409；其他场景重抛 |
| PostgreSQL 连接断/超时 | 全局异常 → 500，触发 docker healthcheck |
| ActivityLog 写入 | 任何失败 → `logger.error(exc_info=True)`，不阻断主请求 |

### 7.3 Aliyun 客户端封装关键决策
1. **客户端单例化**：`AliyunPnvsClient` / `AliyunDmSmtpClient` 用 `lru_cache` 单例，FastAPI startup 时构造。避免每请求重建 TCP/TLS。
2. **不在 startup 探活**：配置缺失只在第一次实际调用时报 `AppException("ALIYUN_NOT_CONFIGURED", 500)`。**CI 单测必须 mock，绝不打真阿里云。**

### 7.4 速率限制（per-endpoint）

复用 `src/common/middleware/rate_limit.py`，本期新增 per-user-id 模式（解 token 后做 key）。

| 端点 | 策略 | 说明 |
|---|---|---|
| `send-email-code` | 不在我方限流 | 已由 Redis guard `email-verify-guard-{email}` TTL 120s 防刷 |
| `send-sms-code` | 不在我方限流 | 已由阿里云 PNVS 自带 `Interval` 防刷 |
| `login-email` / `login-phone` / `login-email-password` | 5 req/60s **per IP** | 对齐 Rust |
| `update-email` / `update-phone` / `update-nickname` / `update-password` / `remove-voter` | 5 req/60s **per user_id** | 解 token 后限流 |
| `token-status` | 不限流 | 心跳轻量校验，加锁反而成瓶颈 |
| `GET /me` | 不限流 | 只读幂等 |

`update-password` 是否需要更严策略见 §九 F8。

### 7.5 安全 / 隐私（呼应 CLAUDE.md §5）
- 日志脱敏：邮箱中段打码（`u***r@example.com`），手机中段打码（`138****1234`）。密码/验证码/token 一律不入日志。
- 邮件 6 位码生成后只进 Redis，不写 ActivityLog（**与 Rust 刻意偏离**，记入迁移文档）。
- `requester_ip` 取 `request.client.host`，**不信任** `X-Forwarded-For`（trusted proxies 处理见 §九 Follow-up）。

---

## 八、测试策略

### 8.1 测试分层
```
tests/
├─ unit/                              # 隔离单元，全 mock 外部依赖
│   ├─ test_email_code_service.py     # 6 位码生成、guard 防刷、消费一次性
│   ├─ test_pnvs_client.py            # mock SDK，验响应解析
│   ├─ test_dm_smtp_client.py         # mock smtplib，验 MIME 拼装
│   ├─ test_jwt.py                    # session/vote token 签发与解码
│   ├─ test_password.py               # bcrypt → argon2 升级
│   └─ test_voter_fe_serialization.py # VoterFE 字段对齐
│
├─ integration/                       # 真 PG + 真 Redis（CI 已就位），mock Aliyun
│   ├─ conftest.py                    # async engine + Redis fixture + alembic upgrade head
│   ├─ test_send_email_code.py
│   ├─ test_send_sms_code.py
│   ├─ test_login_email_flow.py       # 发码→消费→登录/注册→token
│   ├─ test_login_phone_flow.py
│   ├─ test_login_email_password.py   # bcrypt 历史哈希用户能登录并升级
│   ├─ test_update_endpoints.py
│   ├─ test_token_status.py
│   ├─ test_remove_voter.py
│   └─ test_activity_log.py           # 9 类事件落库 + 失败不阻断
│
└─ contract/                          # API 契约：响应 JSON 形状对齐 Rust
    ├─ test_voter_fe_contract.py      # 8 个字段一字不差，含 additional_fingureprint
    ├─ test_login_response_contract.py
    └─ test_error_response_contract.py # 11 个错误字符串都能从对应输入触发
```

### 8.2 关键 fixture 约定
- **`async_session`**：每测试一个独立事务，结束 rollback。
- **`redis_client`**：用 db=15 隔离，每测试 setUp `FLUSHDB`。
- **`mock_pnvs_client`**：autouse，所有 SMS 测试都 mock，**绝不打真阿里云**。
- **`mock_dm_smtp_client`**：autouse 同上。
- **`override_settings`**：临时改 `vote_start_iso`/`vote_end_iso` 验 vote_token 窗口。
- **`freeze_time`**：vote_token `nbf`/`exp` 边界用 `freezegun`。

### 8.3 覆盖率目标 / CI 门禁
- 新增模块行覆盖 **≥ 85%**。
- CI 现有 `pytest --cov=src` + codecov 已就位，本期**不引入硬性门禁**（`fail_ci_if_error: false` 保持），靠 PR 评论把关。
- CI workflow 不改，仅 `tests/integration/conftest.py` 在 fixture setUp 跑 `alembic upgrade head` 替代 `init_db()` 的 `create_all`。
- `requirements.txt` 新增：`alembic`、`alibabacloud_dypnsapi20170525`、`alibabacloud_tea_openapi`、`freezegun`（dev）。

### 8.4 不做的测试
- Aliyun 真接口 smoke：不在自动化里，手工/staging 验证。
- 压测、性能：超出范围。
- MongoDB → PostgreSQL 历史数据迁移：独立任务。
- submit 模块改用真 vote_token：明确不在本期。

---

## 九、Follow-up（不在本期，但**必须记下来不能忘**）

| # | 项目 | 触发条件 / 依赖 | 备注 |
|---|---|---|---|
| F1 | `submit/router.py` 把 `prefix="/v1"` 改回领域前缀（如 `/submit`） | 任何与 submit 端点相关的 PR | 当前会产生 `/api/v1/v1/character/` 这种异常路径 |
| F2 | submit 端点改用 `vote_token` 真实校验（而非仅 `body.meta.vote_id` 加 Redis 锁） | 本期 vote_token 签发就位后即可启动 | 现有提交链路存在鉴权空洞 |
| F3 | thbwiki / qq / patchyvideo SSO 接入 | 业务方需求 | 落地后 `VoterFE.thbwiki`/`patchyvideo` 切真值；同时移除 `User.at_least_one_identifier` CheckConstraint |
| F4 | MongoDB → PostgreSQL 历史用户数据回填 | 切流前 | 处理 ObjectId → UUID 映射，密码哈希直接复用（bcrypt → argon2 升级链路已就位） |
| F5 | trusted proxies / `X-Forwarded-For` 处理 | gateway 层确认后 | `requester_ip` 当前取 `request.client.host` |
| F6 | 测试覆盖率门禁切到 `fail_under=80` | 模块稳定运行 1-2 个 sprint 后 | 现 codecov 是软提示 |
| F7 | SSO 落地后移除 `User.at_least_one_identifier` CheckConstraint | F3 落地时 | 单独 alembic migration |
| F8 | `update-password` 是否限流（per user_id 5/60s）| 上线观察刷接口情况后 | 当前已计划接入限流，若仍被滥用再加专项策略 |
| F9 | 邮件 / 短信发送的"已发送"幂等性（避免阿里云调用成功但写日志失败导致用户看到"未发送"） | 出现客诉时 | 当前策略是先发后写日志，发成功视为已发 |

> **维护规则**：本表新增/移除项目必须同步更新 `docs/CHANGELOG.md`（CLAUDE.md §4）。Follow-up 落地后不要直接删行，改成 `~~划掉~~ + 已完成日期 + PR #编号` 保留追溯。

---

## 十、提交清单（实施时按 CLAUDE.md §10 拆分）

建议拆为以下小而完整的提交：

1. `chore: remove legacy src/app and src/models leftovers`（已经完成清理）
2. `feat(user): add Alembic migration baseline for User and ActivityLog`
3. `feat(common): add AliyunPnvsClient skeleton + unit tests`
4. `feat(common): add AliyunDmSmtpClient skeleton + unit tests`
5. `feat(common): add EmailCodeService + Redis guard + unit tests`
6. `feat(common): add SmsCodeService thin wrapper over PNVS + unit tests`
7. `refactor(security): change vote_token subject from vote_id to user_id`
8. `feat(user): rewrite schemas.py with VoterFE / Meta / 11 endpoint requests`
9. `feat(user): implement send-email-code + send-sms-code endpoints`
10. `feat(user): implement login-email + login-phone + login-email-password`
11. `feat(user): implement update-email/phone/nickname/password`
12. `feat(user): implement token-status + remove-voter`
13. `feat(user): wire ActivityLog writes (best-effort) into all mutation paths`
14. `feat(user): wire rate limiting on user endpoints`
15. `chore(user): remove legacy /login /register /{id} half-baked endpoints`
16. `test(user): contract tests for VoterFE / LoginResponse / error strings`
17. `docs: update migration/user-manager.md to reflect implementation status`
18. `docs(changelog): add entries for user-auth implementation`

每提交都需更新 `docs/CHANGELOG.md`（CLAUDE.md §4 强制）。

---

## 十一、与 Rust 的刻意保留差异

| 项目 | Rust | thvote-be-re | 原因 |
|---|---|---|---|
| 数据库 | MongoDB | PostgreSQL | 架构升级 |
| ID | ObjectId | UUID4 | PG 原生支持 |
| JWT 算法 | ES256k | HS256 / RS256 可配 | 简化部署 |
| 短信验证码生成与防刷 | 本地 + Redis | **阿里云 PNVS 全托管** | 个人开发者免资质，阿里云方案稳定 |
| 短信明文码入审计日志 | 是 | **否** | CLAUDE.md §5 安全要求 + PNVS 无法获取明文 |
| 邮件明文码入审计日志 | 是 | **否** | CLAUDE.md §5 安全要求 |
| `additional_fingureprint` 拼写 | （拼错） | **保留拼错** | 前端契约兼容 |
| `User.at_least_one_identifier` 约束 | 无 | **本期保留** | SSO 暂缓，落地时 F7 移除 |
| qq_openid / thbwiki_uid 字段 | WIP（已定义） | **本期不加列** | Rust 也是 WIP，避免空跑 schema |
| 路径前缀 | `/v1/*` | `/api/v1/user/*` | 总前缀 `/api/v1` 已存在；保持领域子前缀对齐其他模块 |
| `GET /me` 端点 | 无 | **新增** | 替代 `GET /{user_id}` 半成品，鉴权用 `Authorization` header（只读幂等用 header 更符合 REST） |
| `update-password` 限流 | 与其他变更同级 | **per user_id 5/60s** | 见 §九 F8 |
