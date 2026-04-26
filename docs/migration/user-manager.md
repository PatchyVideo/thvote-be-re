# 用户管理模块迁移文档

> 创建日期: 2026-04-15
> 基准: thvote-be/user-manager (Rust/Actix-web + MongoDB)
> 目标: thvote-be-re/src/apps/user (Python/FastAPI + PostgreSQL)

---

## 一、数据模型对比

### 1.1 User 表字段对比

| 字段 | Rust (MongoDB Voter) | Python (SQLAlchemy User) | 状态 |
|------|---------------------|--------------------------|------|
| `_id` / `id` | ObjectId (自动) | String (UUID4) | 已有，类型不同 |
| `phone` / `phone_number` | `Option<String>` | `String, nullable` | 已有 |
| `phone_verified` | `bool` (默认 false) | -- | **缺失** |
| `email` | `Option<String>` | `String, nullable` | 已有 |
| `email_verified` | `bool` (默认 false) | -- | **缺失** |
| `password_hashed` | `Option<String>` | `String, nullable` | 已有 |
| `salt` / `legacy_salt` | `Option<String>` | `String, nullable` | 已有 |
| `created_at` / `register_date` | `DateTime` | `DateTime` | 已有 |
| `signup_ip` / `register_ip_address` | `Option<String>` | `String` | 已有 |
| `nickname` | `Option<String>` | -- | **缺失** |
| `pfp` | `Option<String>` | -- | **缺失** |
| `qq_openid` | `Option<String>` | -- | 暂缓 (Rust 中也是 WIP) |
| `thbwiki_uid` | `Option<String>` | -- | 暂缓 (Rust 中也是 WIP) |
| `removed` | `Option<bool>` | -- | **缺失** |

**需新增字段:** `nickname`, `phone_verified`, `email_verified`, `pfp`, `removed`

### 1.2 活动日志表 (缺失，需新建)

Rust 在 MongoDB `thvote_users.voter_logs` 中记录以下 9 类事件：

| 事件类型 | 说明 | 附带字段 |
|---------|------|---------|
| `SendEmail` | 发送邮箱验证码 | target_email, code |
| `SendSMS` | 发送短信验证码 | target_phone, code |
| `VoterCreation` | 用户注册 | uid, email, phone, nickname |
| `VoterLogin` | 用户登录 | uid, email, phone |
| `UpdateEmail` | 更新邮箱 | uid, old_email, new_email |
| `UpdatePhone` | 更新手机号 | uid, old_phone, new_phone |
| `UpdateNickname` | 更新昵称 | uid, old_nickname, new_nickname |
| `UpdatePassword` | 更新密码 | uid |
| `RemoveVoter` | 删除账户 | uid |

所有事件均包含公共字段: `created_at`, `requester_ip`, `additional_fingerprint`

---

## 二、API 端点对比

### 2.1 Rust 端点列表 (共 11 个)

| # | 端点 | 方法 | Python 状态 | 说明 |
|---|------|------|------------|------|
| 1 | `/v1/login-email-password` | POST | **已有** (路径: `/user/login/email`) | 邮箱+密码登录 |
| 2 | `/v1/login-email` | POST | **缺失** | 邮箱+验证码登录/注册 |
| 3 | `/v1/login-phone` | POST | **缺失** | 手机号+验证码登录/注册 |
| 4 | `/v1/send-email-code` | POST | **缺失** | 发送邮箱验证码 |
| 5 | `/v1/send-sms-code` | POST | **缺失** | 发送短信验证码 |
| 6 | `/v1/update-email` | POST | **缺失** | 更新邮箱 (需验证码) |
| 7 | `/v1/update-phone` | POST | **缺失** | 更新手机号 (需验证码) |
| 8 | `/v1/update-nickname` | POST | **缺失** | 更新昵称 |
| 9 | `/v1/update-password` | POST | **缺失** | 修改/首次设置密码 |
| 10 | `/v1/user-token-status` | POST | **缺失** | 校验 JWT 有效性 |
| 11 | `/v1/remove-voter` | POST | **缺失** | 软删除账户 |

### 2.2 各端点请求/响应结构

所有 Rust 端点的请求体都包含 `meta` 字段:
```json
{
  "meta": {
    "user_ip": "string",
    "additional_fingureprint": "string (optional)"
  }
}
```

#### 登录类

**POST /v1/login-email-password**
```
请求: { email, password, meta }
响应: { user: VoterFE, vote_token, session_token }
```

**POST /v1/login-email**
```
请求: { email, nickname?, verify_code, meta }
响应: { user: VoterFE, vote_token, session_token }
逻辑: 验证码正确 → 查找/创建用户 → 标记 email_verified=true → 返回 token
```

**POST /v1/login-phone**
```
请求: { phone, nickname?, verify_code, meta }
响应: { user: VoterFE, vote_token, session_token }
逻辑: 同上，标记 phone_verified=true
```

#### 验证码类

**POST /v1/send-email-code**
```
请求: { email, meta }
响应: {}
逻辑:
  1. 检查 guard key `email-verify-guard-{email}` → 存在则拒绝 (REQUEST_TOO_FREQUENT, 120s 间隔)
  2. 生成 6 位随机数字验证码
  3. Redis SET `email-verify-{email}` = code, TTL 3600s
  4. Redis SET `email-verify-guard-{email}` = "guard", TTL 120s
  5. 调用邮件服务发送验证码
  6. 记录 SendEmail 活动日志
```

**POST /v1/send-sms-code**
```
请求: { phone, meta }
响应: {}
逻辑: 同上，key 前缀为 `phone-verify-`，调用 SMS 服务
```

#### 账户管理类 (均需 user_token)

**POST /v1/update-email**
```
请求: { user_token, email, verify_code, meta }
响应: {}
逻辑: 解码 token → 验证码校验 → 检查邮箱唯一性 → 更新 → 日志
```

**POST /v1/update-phone**
```
请求: { user_token, phone, verify_code, meta }
响应: {}
逻辑: 同上
```

**POST /v1/update-nickname**
```
请求: { user_token, nickname, meta }
响应: {}
逻辑: 解码 token → 更新 nickname → 日志
```

**POST /v1/update-password**
```
请求: { user_token, old_password?, new_password, meta }
响应: {}
逻辑:
  - 有旧密码 → 验证后更新 (支持 bcrypt→Argon2 升级)
  - 无旧密码 → 直接设置 (首次设密码，适用于验证码注册的用户)
```

**POST /v1/user-token-status**
```
请求: { user_token }
响应: {}
逻辑: 验证 JWT 签名和有效期，有效返回 200，无效返回错误
```

**POST /v1/remove-voter**
```
请求: { user_token, old_password?, meta }
响应: {}
逻辑: 软删除 → 设 removed=true, 清空 email/phone → 日志
```

### 2.3 前端用户响应结构 (VoterFE)

Rust 返回给前端的用户结构:
```json
{
  "username": "string?",       // 来自 nickname
  "pfp": "string?",           // 头像
  "password": true,           // 是否已设密码 (bool)
  "phone": "string?",
  "email": "string?",
  "thbwiki": false,           // 固定 false (遗留字段)
  "patchyvideo": false,       // 固定 false (遗留字段)
  "created_at": "ISO8601"
}
```

---

## 三、基础设施差异

### 3.1 验证码服务 (完全缺失)

需要实现:
- Redis 验证码存取 (key: `{type}-verify-{target}`, TTL 3600s)
- Guard 防刷机制 (key: `{type}-verify-guard-{target}`, TTL 120s)
- 外部 SMS/Email 服务调用 (当前 config.py 已有阿里云配置项，未实现调用)

### 3.2 速率限制

- Rust: 5 req/60s token bucket，应用于所有用户端点
- Python: 30 req/60s，仅用于 submit 端点，用户端点未接入

### 3.3 Token 生成

- Rust: 登录成功后同时返回 `session_token` + `vote_token`
- Python: 仅返回 `session_token`，**缺少 vote_token 生成**
- vote_token 生成条件: 用户必须 phone_verified 或 email_verified

### 3.4 JWT 算法

- Rust: ES256k (ECDSA secp256k1)
- Python: HS256 或 RSA (可配置)
- 迁移决策: Python 版保持当前方案即可，无需对齐 ES256k

---

## 四、迁移计划（已完成 ✅）

> 实施完成日期：2026-04-27
> 实施分支：`feat/user-and-verify`
> 设计文档：`docs/superpowers/specs/2026-04-27-user-auth-design.md`

### 阶段 1: 数据模型补全 ✅

- [x] User 表字段已对齐 Rust Voter（`nickname`, `phone_verified`, `email_verified`, `pfp`, `removed` 全部到位）
- [x] ActivityLog 表已建立
- [x] **新增**：Alembic baseline migration `0001_initial_user_and_activity_log` 把两张表正式纳入版本管理
- [x] schemas.py 重写为 Rust 对齐的 11 个请求模型 + `VoterFE` + `LoginResponse`

### 阶段 2: 验证码基础设施 ✅

- [x] EmailCodeService（`src/common/verification/email_code.py`）：6 位码、Redis TTL 3600s、guard TTL 120s
- [x] SmsCodeService（`src/common/verification/sms_code.py`）：薄封装阿里云 **PNVS**，验证码全程不入我方 Redis
- [x] AliyunPnvsClient（`src/common/aliyun/pnvs_client.py`）：`SendSmsVerifyCode` + `CheckSmsVerifyCode`
- [x] AliyunDmSmtpClient（`src/common/aliyun/dm_smtp_client.py`）：阿里云 DirectMail SMTP 投递

### 阶段 3: 端点实现 ✅

11 个 Rust 对齐端点 + 1 个新增 `GET /me`，全部位于 `/api/v1/user/...`，详见 `src/apps/user/router.py`。

### 阶段 4: 修正与对齐 ✅

- [x] 登录响应包含 `user: VoterFE + session_token + vote_token`，`vote_token` 受 `(email_verified or phone_verified)` 与投票期窗口约束
- [x] 用户端点接入速率限制：login-* 5 req/60s per IP，update-* / remove-voter 5 req/60s per user_id
- [x] 所有变更操作写入 ActivityLog（best-effort，独立事务，失败不阻断主流程）
- [x] 软删除：`removed=TRUE` 同时清空 email/phone；CHECK 约束已放宽允许 removed 行同时 NULL

### 阶段 5: 路径对齐 ✅

最终方案：保持 `/api/v1/user/*` 子前缀，端点动作名扁平、与 Rust 一一对应（`login-email`、`send-sms-code`、`update-password` 等）。详见设计文档 §四。

### 阶段 6: 测试 ✅

- [x] tests/unit：JWT、VoterFE、EmailCodeService、PNVS 响应解析
- [x] tests/integration：完整登录/注册/更新/软删流程（in-memory sqlite + fakeredis + 模拟 PNVS/DM）
- [x] tests/contract：路由表 + VoterFE JSON 形状

测试总数：43 通过。

---

## 五、刻意保留的差异

| 项目 | Rust | Python | 原因 |
|------|------|--------|------|
| 数据库 | MongoDB | PostgreSQL | 架构升级决策 |
| JWT 算法 | ES256k | HS256/RSA | 简化部署，无需密钥对管理 |
| ID 格式 | MongoDB ObjectId | UUID4 | PostgreSQL 原生支持 |
| qq_openid | WIP | 暂缓 | Rust 中也未完成 |
| thbwiki_uid | WIP | 暂缓 | Rust 中也未完成 |

---

## 六、风险与注意事项

1. **数据迁移**: 若需从 MongoDB 迁移历史用户数据到 PostgreSQL，需编写迁移脚本处理 ObjectId → UUID 映射 — 仍是 follow-up（spec §九 F4）
2. **密码兼容**: Python 已实现 bcrypt→Argon2 升级路径，与 Rust 一致，迁移后可正常登录 — 已落地，单测覆盖
3. **验证码服务依赖**: SMS 已迁至阿里云 PNVS（个人开发者免资质）；邮件改用阿里云 DM SMTP；不再依赖 Rust 内部 SMS / Email 微服务
4. **vote_token 时间窗口**: `VOTE_START_ISO` / `VOTE_END_ISO` 配置就位，登录响应判定窗口；submit 模块尚未真校验 vote_token，参见 spec §九 F2
5. **CHECK 约束变更**: `at_least_one_identifier` 已放宽支持软删除，需 `alembic upgrade head` 应用
6. **PNVS 配置**: 需 `ALIYUN_PNVS_*` 全套环境变量（access key/secret/endpoint/scheme_name/sms_sign_name/sms_template_code）；缺失会在首次 `send-sms-code` 调用时返回 `ALIYUN_NOT_CONFIGURED` 500

## 七、后续工作（不在本期）

完整 Follow-up 列表见 `docs/superpowers/specs/2026-04-27-user-auth-design.md` §九 F1-F9，重点：
- F1：修复 `submit/router.py` 的 `prefix="/v1"` 路径 bug
- F2：submit 端点改用真 `vote_token` 校验（当前仅用 `body.meta.vote_id` 加锁，存在鉴权空洞）
- F3：thbwiki / qq / patchyvideo SSO 接入
- F4：MongoDB → PostgreSQL 历史用户数据回填脚本
- F5：trusted proxies / `X-Forwarded-For` 处理
