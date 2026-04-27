# 阿里云上线接入手册

> 创建日期：2026-04-27
> 最后更新：2026-04-27
>
> 用途：把用户与认证模块所依赖的两个阿里云服务（**PNVS 号码认证服务** + **DirectMail 邮件推送**）从零接通到生产，一次过完所有步骤。
> 关联代码：`src/common/aliyun/{pnvs_client,dm_smtp_client}.py`、`src/common/verification/{sms_code,email_code}.py`
> 关联设计：[`docs/superpowers/specs/2026-04-27-user-auth-design.md`](../superpowers/specs/2026-04-27-user-auth-design.md) §二、§七.3

---

## 总览

| 服务 | 用途 | 个人开发者 | 关键配置前缀 |
|---|---|---|---|
| PNVS（号码认证） | 短信验证码全托管 | 免资质，使用系统赠送签名+模板 | `ALIYUN_PNVS_*` |
| DirectMail（邮件推送） | 邮件验证码 SMTP 投递 | 需要自有域名做 DNS 验证 | `ALIYUN_DM_*` |

**核心原则：**
- 验证码本身永远不进我方日志（PNVS 全托管短信码；邮件 6 位码只进 Redis）
- 写入 ActivityLog 的只有发送动作 + PNVS BizId / 收件人脱敏地址
- AccessKey 只放在 GitHub Secrets / Apollo 加密命名空间，绝不进 git（CLAUDE.md §5）

---

## 一、阿里云账号基础

1. **注册主账号** + **完成个人实名认证**（PNVS 个人开发者免资质 SMS 的硬性前提）
2. **充值少量余额**（PNVS 短信约 ¥0.045/条；DM 邮件约 ¥0.5/千封）
3. **创建 RAM 子账号**（强烈建议，不要用主账号 AccessKey）
   - RAM 控制台 → 用户 → 创建用户 → 启用「OpenAPI 调用」
   - 给子账号挂权限策略：
     - `AliyunDypnsFullAccess`（PNVS）
     - `AliyunDirectMailFullAccess`（DM）
   - 拿到 **AccessKey ID + AccessKey Secret**（同一对密钥同时给 PNVS 和 DM 用）

> ⚠️ AccessKey Secret 只在创建时显示一次，**立刻保存到 secret 管理器**。

---

## 二、PNVS（号码认证服务）

控制台入口：<https://dypns.console.aliyun.com/>

### 2.1 开通服务

1. 第一次进控制台勾选服务协议 → 开通（开通本身免费，只在调用时计费）

### 2.2 创建认证方案

1. 控制台左侧「**认证方案管理**」→ 创建认证方案
2. 方案类型选「**短信认证**」
3. 起一个名字（≤20 字符），即 **SchemeName**
4. 系统自动绑定**赠送签名 + 赠送模板**（个人无需另外申请）
5. 记下三个值：
   - 方案名 → `ALIYUN_PNVS_SCHEME_NAME`
   - 赠送签名（控制台显示「短信签名」一栏）→ `ALIYUN_PNVS_SMS_SIGN_NAME`
   - 赠送模板的 TemplateCode（如 `SMS_xxxxxxxx`）→ `ALIYUN_PNVS_SMS_TEMPLATE_CODE`

### 2.3 行为参数

> 这些可以在控制台调，也可以走环境变量传给我们的 client。代码里完全透传给 PNVS。

| 环境变量 | 默认 | 我们采用 | 说明 |
|---|---|---|---|
| `ALIYUN_PNVS_CODE_LENGTH` | 4 | **6** | 与 Rust 历史行为对齐 |
| `ALIYUN_PNVS_VALID_TIME` | 300 | 300 | 验证码 TTL（秒） |
| `ALIYUN_PNVS_INTERVAL` | 60 | **120** | 同号码重发最小间隔，对齐 Rust |

### 2.4 接入端点

| 环境变量 | 取值 |
|---|---|
| `ALIYUN_PNVS_ENDPOINT` | `dypnsapi.aliyuncs.com` |
| `ALIYUN_PNVS_REGION_ID` | `cn-hangzhou`（PNVS 实际只支持杭州，写其他 region 会报错） |
| `ALIYUN_PNVS_ACCESS_KEY_ID` | 来自 §一.3 |
| `ALIYUN_PNVS_ACCESS_KEY_SECRET` | 来自 §一.3 |

---

## 三、DirectMail（邮件推送 SMTP）

控制台入口：<https://dm.console.aliyun.com/>

### 3.1 开通服务

1. 控制台勾选协议 → 开通

### 3.2 域名验证（**最容易卡住的一步**）

1. 你需要**自己拥有一个域名**（如 `thvote.example.com`，可用根域或子域）
2. 控制台「**域名管理 → 添加新域名**」
3. 控制台会给出 **4 条 DNS 记录**，去你的 DNS 服务商加：
   - **SPF**（TXT 记录）：阻止伪造
   - **MX**（MX 记录）：接收退信
   - **DKIM**（TXT 记录）：邮件签名
   - **域名所有权**（TXT 记录）：证明你拥有这个域名
4. DNS 生效后（5~30 分钟），回控制台点「**验证**」直到 4 项全部变绿
5. 域名状态变绿前，发送会被阿里云拒绝

### 3.3 创建发信地址

1. 控制台「**发信地址 → 创建发信地址**」
2. 邮箱：`noreply@thvote.example.com`（必须是你刚才验证过的域名）
3. 类型选「**触发邮件**」（验证码属于触发类，不是营销类）
4. 点击「**设置 SMTP 密码**」 → 设一个 SMTP 密码并保存
   - ⚠️ 这个密码与阿里云账户密码无关，是该发信地址独立的 SMTP 凭据

| 环境变量 | 取值 |
|---|---|
| `ALIYUN_DM_ACCOUNT_NAME` | `noreply@thvote.example.com` |
| `ALIYUN_DM_SMTP_USERNAME` | `noreply@thvote.example.com`（与 ACCOUNT_NAME 相同） |
| `ALIYUN_DM_SMTP_PASSWORD` | 上一步设置的 SMTP 密码 |

### 3.4 SMTP 接入端点

| 环境变量 | 推荐取值 |
|---|---|
| `ALIYUN_DM_SMTP_HOST` | `smtpdm.aliyun.com`（公网）<br>或 `smtpdm-app.aliyun.com`（阿里云 ECS 内网，仅同地域 ECS 可用） |
| `ALIYUN_DM_SMTP_PORT` | **`465`（SSL，推荐）** |

> 端口选择：
> - 465（SSL）— 推荐，我们的 `AliyunDmSmtpClient._send_sync` 默认按 SSL 连接
> - 80 / 25（明文/STARTTLS）— 端口 25 国内云常被封；80 不安全
> 如果你必须用 STARTTLS（如端口 587），需要修改 `dm_smtp_client.py` 改用 `smtp.starttls()` 流程

### 3.5 可选配置

| 环境变量 | 用途 |
|---|---|
| `ALIYUN_DM_FROM_ALIAS` | 邮件 From 头里显示的友好名（如 `THVote`） |
| `ALIYUN_DM_TAG_NAME` | 控制台分类统计标签（先在「标签管理」创建后填这里） |
| `ALIYUN_DM_ENDPOINT` | OpenAPI 端点（当前我们走 SMTP，可不填；留作 follow-up） |
| `ALIYUN_DM_REGION_ID` | 同上 |

---

## 四、把配置注入部署

参考 `.github/workflows/deploy-test.yml` 中现有 `cat > .env << 'ENVEOF'` 写法，把下面这段加进去：

```env
# ── PNVS 号码认证（短信验证码） ────────────────────────────────────
ALIYUN_PNVS_ACCESS_KEY_ID=LTAI...
ALIYUN_PNVS_ACCESS_KEY_SECRET=...
ALIYUN_PNVS_ENDPOINT=dypnsapi.aliyuncs.com
ALIYUN_PNVS_REGION_ID=cn-hangzhou
ALIYUN_PNVS_SCHEME_NAME=thvote-sms-verify
ALIYUN_PNVS_SMS_SIGN_NAME=【阿里云短信测试】
ALIYUN_PNVS_SMS_TEMPLATE_CODE=SMS_xxxxxxxx
ALIYUN_PNVS_CODE_LENGTH=6
ALIYUN_PNVS_VALID_TIME=300
ALIYUN_PNVS_INTERVAL=120

# ── DirectMail SMTP（邮件验证码） ──────────────────────────────────
ALIYUN_DM_ACCESS_KEY_ID=LTAI...                # 与 PNVS 同一对子账号 KEY 即可
ALIYUN_DM_ACCESS_KEY_SECRET=...
ALIYUN_DM_ACCOUNT_NAME=noreply@thvote.example.com
ALIYUN_DM_FROM_ALIAS=THVote
ALIYUN_DM_TAG_NAME=verify-code
ALIYUN_DM_SMTP_HOST=smtpdm.aliyun.com
ALIYUN_DM_SMTP_PORT=465
ALIYUN_DM_SMTP_USERNAME=noreply@thvote.example.com
ALIYUN_DM_SMTP_PASSWORD=...
```

**机密值的归属：**
- `*_ACCESS_KEY_SECRET` / `*_SMTP_PASSWORD` → **GitHub Actions Secrets**（CI 注入）或 **Apollo 加密命名空间**（运行时注入）
- 非机密值（endpoint / region_id / scheme_name / sign_name / template_code / SMTP host/port）可以直接写在仓库内的 `.env.test.example` / `.env.prod.example`

---

## 五、上线前 smoke 验证

> 这一步**不能跳过**，自动化测试都 mock 了 Aliyun，真接口的连通性必须手动确认一次。

### 5.1 短信链路

```bash
curl -X POST https://test-api.thvote.example.com/api/v1/user/send-sms-code \
  -H "Content-Type: application/json" \
  -d '{"phone":"<你自己的手机号>","meta":{"user_ip":"1.1.1.1"}}'
```
**预期：**
- 几秒内收到阿里云下发的短信「您的验证码是 XXXXXX」
- 服务端日志可见 `event_type=send_sms` 的 ActivityLog 一条，`detail=BizId=...`，**不应**有验证码明文

```bash
curl -X POST https://test-api.thvote.example.com/api/v1/user/login-phone \
  -H "Content-Type: application/json" \
  -d '{"phone":"<你的手机号>","verify_code":"<收到的码>","nickname":"smoke-test","meta":{"user_ip":"1.1.1.1"}}'
```
**预期：**
- 返回 `{user, session_token, vote_token}`，`vote_token` 在投票期内为非空字符串
- DB 里能查到对应的 `user` 行

### 5.2 邮件链路

```bash
curl -X POST https://test-api.thvote.example.com/api/v1/user/send-email-code \
  -H "Content-Type: application/json" \
  -d '{"email":"<你自己的邮箱>","meta":{"user_ip":"1.1.1.1"}}'
```
**预期：**
- 收件箱（含垃圾邮件夹）内能看到从 `noreply@thvote.example.com` 来的「THVote 验证码」邮件
- Redis 里 `email-verify-<email>` 与 `email-verify-guard-<email>` 都存在
- ActivityLog 有 `send_email` 一条

```bash
curl -X POST https://test-api.thvote.example.com/api/v1/user/login-email \
  -H "Content-Type: application/json" \
  -d '{"email":"<你的邮箱>","verify_code":"<收到的码>","nickname":"smoke-test","meta":{"user_ip":"1.1.1.1"}}'
```
**预期：**
- 同短信，返回 `{user, session_token, vote_token}`

### 5.3 反向验证（必须）

- 同一手机号 / 邮箱在 120 秒内连续发码 → 应得 `429 REQUEST_TOO_FREQUENT`
- 输错验证码 → 应得 `400 INCORRECT_VERIFY_CODE`
- 验证码过期后再用 → 同上
- 同一邮件验证码消费两次 → 第二次 `400 INCORRECT_VERIFY_CODE`（一次性）

---

## 六、常见坑速查

| 现象 | 根因 | 处理 |
|---|---|---|
| 短信返回 `isv.UNSUPPORTED_PRODUCT` | PNVS 服务未开通 | 控制台开通 |
| 短信返回 `isv.SCHEME_NOT_FOUND` | SchemeName 拼错 / 未创建认证方案 | 检查 §2.2 |
| 短信返回 `isv.MOBILE_NUMBER_ILLEGAL` | 号码格式错（如带 +86） | 我们 client 已映射为 `INVALID_PHONE`，前端清洗号码 |
| 短信返回 `isv.BUSINESS_LIMIT_CONTROL` | 同号码触发频控 / 个人额度耗尽 | 我们 client 已映射为 `REQUEST_TOO_FREQUENT`；额度问题需升级资质 |
| 短信能下发但 `CheckSmsVerifyCode` 总是 `UNKNOWN` | 发送和校验的 SchemeName 不一致 | 两个调用必须传相同 SchemeName |
| 邮件返回 `InvalidMailAddress.Malformed` | 发信地址不是已验证域名下的 | 检查 §3.2 域名验证状态 |
| 邮件发出去都进垃圾箱 | SPF/DKIM 未生效 / 内容被打分 | 用 [mail-tester.com](https://www.mail-tester.com/) 自查 |
| SMTP 连接超时 | 25 端口被封 | 切到 465 + SSL（我们 client 默认） |
| `EMAIL_SEND_FAILED` 但 SMTP 看似成功 | 偶发网络抖动 | client 已自动重试 1 次；持续失败需查阿里云控制台「投递日志」 |
| 个人开发者短信日上限低 | PNVS 免资质方案有日发量限制 | 上量后申请企业资质 + 自有签名（替换 SignName + TemplateCode） |

---

## 七、上量后需要做的事（不在本期）

- 升级到企业资质，申请自有短信签名 + 模板（绕开个人开发者日上限）
- DirectMail 申请「营销邮件」类型（如果未来要发活动通知）
- 监控告警：阿里云控制台「数据统计」接 Prometheus 或飞书告警
- 短信 / 邮件成本月度对账

---

## 八、相关代码位置

| 关注点 | 文件 |
|---|---|
| PNVS 客户端 | `src/common/aliyun/pnvs_client.py` |
| DM SMTP 客户端 | `src/common/aliyun/dm_smtp_client.py` |
| SMS 业务封装 | `src/common/verification/sms_code.py` |
| 邮件业务封装 | `src/common/verification/email_code.py` |
| 端点入口 | `src/apps/user/router.py`（`send-sms-code` / `send-email-code`） |
| 配置定义 | `src/common/config.py`（`aliyun_pnvs_*` / `aliyun_dm_*` 全量字段） |
| 单元测试 | `tests/unit/test_pnvs_client.py`、`tests/unit/test_email_code_service.py` |
