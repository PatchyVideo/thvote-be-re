# THVote-be-re Auth Implementation Plan

本文档用于约定 `modules/auth` 的实现计划，目标是在 Python 重写中尽量保持 Rust `user-manager` 的核心语义，同时把代码结构收敛到当前 `src/app/` 骨架。

## 目标

`auth` 模块需要承接 Rust 旧实现中的这些能力：

- 邮箱 + 密码登录
- 邮箱 + 验证码登录/注册
- 手机号 + 验证码登录/注册
- 用户空间 `session_token`
- 投票期 `vote_token`
- 用户信息修改
- 密码修改
- 账号软删除
- 活动审计日志

本阶段不追求一次性全部完成，优先保证边界清晰、语义稳定、后续可扩展。

## Rust 旧实现结论

Rust `user-manager` 当前不是单一登录模型，而是多入口认证系统：

- `login-email-password`
- `login-email`
- `login-phone`
- `update-email`
- `update-phone`
- `update-nickname`
- `update-password`
- `send-sms-code`
- `send-email-code`
- `user-token-status`
- `remove-voter`

关键语义：

- 邮箱验证码登录和手机验证码登录都带“未注册则自动创建用户”行为。
- 系统同时返回 `vote_token` 和 `session_token`。
- `vote_token` 有投票开始/结束时间窗口限制。
- `session_token` 用于用户空间。
- 验证码、发送频控和部分限流依赖 Redis。
- 历史密码体系存在 `bcrypt + salt`，新密码体系为 `argon2`。
- 用户事件会写活动日志。

## Python 目标结构

`auth` 正式代码应收敛到：

```text
src/app/
  common/
    security/
      jwt.py
      password.py
    cache/
      redis.py
  models/
    dto/
      auth.py
    orm/
      user.py
      auth_log.py
  modules/
    auth/
      repository.py
      service.py
      provider.py
```

职责约定：

- `common/security/jwt.py`
  负责 token 签发、验签、claim 约定。
- `common/security/password.py`
  负责密码哈希、密码校验、旧密码兼容迁移。
- `models/orm/user.py`
  负责用户持久化模型，语义对齐 Rust `Voter`。
- `models/orm/auth_log.py`
  负责认证相关活动日志。
- `modules/auth/repository.py`
  负责用户、验证码状态、审计数据的持久化访问。
- `modules/auth/service.py`
  负责认证流程编排、规则校验、token 生成。
- `modules/auth/provider.py`
  负责短信、邮件、外部登录绑定等外部能力封装。

## 服务商选择

当前计划采用阿里云作为验证码与通知能力提供方：

- 手机验证码：阿里云号码认证服务（PNVS）下的短信认证服务
- 邮件：阿里云邮件推送（Direct Mail）

这样选择的原因：

- Rust 旧实现本来就依赖独立短信/邮件服务，迁到 Python 后继续保留 provider 边界最稳。
- 手机验证码和事务邮件都属于成熟场景，阿里云现成能力足够，不需要自建发送通道。
- 短信认证服务适合个人开发者场景，不要求企业短信资质，和本项目当前条件更匹配。
- 邮件推送适合承接邮箱验证码、通知邮件、找回密码邮件等事务邮件场景。

实现约束：

- `modules/auth/provider.py` 只封装阿里云发送能力，不承载业务校验。
- 验证码生成、发送冷却、验证码校验仍由 `modules/auth/service.py` 控制。
- API 层不直接调用阿里云 SDK。

重要区分：

- 本项目要用的是“短信认证服务”，不是“短信服务”。
- “短信服务”适合通用短信发送，但通常需要企业资质、签名和模板申请，不适合作为本项目当前首选方案。
- “短信认证服务”属于 PNVS 体系，定位就是手机号验证码和核验，接入门槛更低。

## 服务商配置

### 阿里云短信认证服务

建议按下面顺序配置：

1. 开通阿里云号码认证服务（PNVS）。
2. 完成阿里云账号实名认证。
3. 创建具备号码认证调用权限的 RAM 用户或 AccessKey。
4. 在控制台确认短信认证功能已可用。
5. 在项目环境变量中配置认证服务相关参数。

这条产品线和普通短信服务的区别：

- 不需要企业短信资质。
- 不需要单独申请短信签名。
- 不需要单独申请短信模板。
- 使用的是 PNVS 的认证接口，不是普通短信发送接口。

项目内建议保留这些环境变量：

- `ALIYUN_PNVS_ACCESS_KEY_ID`
- `ALIYUN_PNVS_ACCESS_KEY_SECRET`
- `ALIYUN_PNVS_ENDPOINT`
- `ALIYUN_PNVS_REGION_ID`
- `ALIYUN_PNVS_SCHEME_NAME`
- `ALIYUN_PNVS_SMS_SIGN_NAME`
- `ALIYUN_PNVS_SMS_TEMPLATE_CODE`
- `ALIYUN_PNVS_CODE_LENGTH`
- `ALIYUN_PNVS_VALID_TIME`
- `ALIYUN_PNVS_INTERVAL`

说明：

- `ENDPOINT` 应对应 PNVS / `dypnsapi` 体系，而不是普通短信服务的 `dysmsapi`。
- `SCHEME_NAME` 对应短信认证方案名称。
- `SMS_SIGN_NAME` 和 `SMS_TEMPLATE_CODE` 应按短信认证服务的系统赠送签名/模板能力来配置，不按普通短信服务去申请自定义模板。
- `CODE_LENGTH`、`VALID_TIME`、`INTERVAL` 用于约束验证码长度、有效期和发送间隔。

建议的实现方式：

- 发送验证码：调用短信认证服务发送接口
- 校验验证码：优先调用短信认证服务校验接口
- 不再由本地 Redis 自己保存手机验证码明文

这样做的原因：

- 能直接复用服务商验证码校验能力。
- 可以减少本地自行保管短信验证码的实现复杂度。
- 更贴近“认证服务”而不是“消息发送服务”的产品语义。

### 阿里云邮件推送

建议按下面顺序配置：

1. 开通阿里云邮件推送。
2. 配置并验证发信域名。
3. 创建事务邮件发信地址。
4. 选择发送方式：
   - 优先 API
   - SMTP 可作为备用方案
5. 在项目环境变量中配置邮件相关参数。

项目内建议保留这些环境变量：

- `ALIYUN_DM_ACCESS_KEY_ID`
- `ALIYUN_DM_ACCESS_KEY_SECRET`
- `ALIYUN_DM_ENDPOINT`
- `ALIYUN_DM_REGION_ID`
- `ALIYUN_DM_ACCOUNT_NAME`
- `ALIYUN_DM_FROM_ALIAS`
- `ALIYUN_DM_TAG_NAME`

如果采用 SMTP 发送，再补：

- `ALIYUN_DM_SMTP_HOST`
- `ALIYUN_DM_SMTP_PORT`
- `ALIYUN_DM_SMTP_USERNAME`
- `ALIYUN_DM_SMTP_PASSWORD`

说明：

- `ACCOUNT_NAME` 对应发信地址。
- `FROM_ALIAS` 对应发件人显示名称。
- `TAG_NAME` 可用于区分验证码邮件、通知邮件等统计维度。

## Provider 设计建议

建议把外部服务能力拆成两个 provider：

- `AliyunPnvsProvider`
- `AliyunMailProvider`

职责：

- `AliyunPnvsProvider`
  - 调用短信认证服务发送验证码
  - 调用短信认证服务校验验证码
  - 屏蔽 PNVS SDK / HTTP 接口细节
  - 统一转换服务商错误为应用内异常
- `AliyunMailProvider`
  - 发送验证码和事务邮件
  - 屏蔽 API / SMTP 的底层差异
  - 统一处理请求 ID、错误码和失败重试入口

不要做：

- 在 provider 里生成验证码
- 在 provider 里做用户是否存在判断
- 在 provider 里直接写数据库

## 配置文件建议

建议在 `common/config.py` 中新增明确的 provider 配置项，而不是在业务代码里零散读取环境变量。

建议至少增加：

- `aliyun_pnvs_access_key_id`
- `aliyun_pnvs_access_key_secret`
- `aliyun_pnvs_endpoint`
- `aliyun_pnvs_region_id`
- `aliyun_pnvs_scheme_name`
- `aliyun_pnvs_sms_sign_name`
- `aliyun_pnvs_sms_template_code`
- `aliyun_pnvs_code_length`
- `aliyun_pnvs_valid_time`
- `aliyun_pnvs_interval`
- `aliyun_dm_access_key_id`
- `aliyun_dm_access_key_secret`
- `aliyun_dm_endpoint`
- `aliyun_dm_region_id`
- `aliyun_dm_account_name`
- `aliyun_dm_from_alias`
- `aliyun_dm_tag_name`

如果邮件走 SMTP，再补：

- `aliyun_dm_smtp_host`
- `aliyun_dm_smtp_port`
- `aliyun_dm_smtp_username`
- `aliyun_dm_smtp_password`

这些配置应统一由 `Settings` 暴露，供 `modules/auth/provider.py` 注入使用。

## 数据模型建议

### 用户模型

建议至少包含这些字段：

- `id`
- `phone`
- `phone_verified`
- `email`
- `email_verified`
- `password_hashed`
- `password_legacy_salt`
- `nickname`
- `signup_ip`
- `qq_openid`
- `thbwiki_uid`
- `pfp`
- `removed`
- `created_at`
- `updated_at`

设计原则：

- 明确保留 `password_legacy_salt`，只用于迁移期兼容。
- `removed` 使用软删除语义，不做物理删除。
- 手机、邮箱都允许为空，但至少要有一种可用登录身份。

### 审计日志模型

建议单独建表，不混进应用普通日志。

建议事件类型至少覆盖：

- `send_email_code`
- `send_sms_code`
- `user_created`
- `user_login`
- `update_email`
- `update_phone`
- `update_nickname`
- `update_password`
- `remove_user`

## Token 设计

建议保持 Rust 的双 token 语义：

### `session_token`

用途：

- 用户空间接口
- 用户资料修改
- 用户登录状态检查

建议：

- 有效期 7 天
- claim 中包含 `user_id`
- audience 明确区分用户空间

### `vote_token`

用途：

- 投票提交和投票态相关能力

建议：

- claim 中包含 `vote_id`
- 有效期受投票开始/结束时间约束
- 由已验证邮箱或手机号的用户生成

## 密码策略

建议：

- 新密码统一使用 `argon2`
- 迁移期保留旧 `bcrypt + salt` 校验逻辑
- 老密码一旦验证成功，立即升级为 `argon2`

不建议：

- 继续扩散旧密码格式
- 新代码直接依赖历史 `salt` 方案作为长期实现

## 验证码与 Redis 设计

建议保留 Rust 的总体思路：

- 邮箱验证码：`email-verify-{email}`
- 手机验证码：`phone-verify-{phone}`
- 发送频控 guard 也放 Redis

建议的 TTL：

- 验证码：1 小时
- 发送冷却：120 秒

实现约束：

- 验证码发送和校验逻辑放在 `modules/auth/service.py`
- Redis 访问封装放在 `common/cache/redis.py`
- 不要在 API 层直接读写 Redis

## 实现阶段

### Phase 1

目标：

- 建立 `User` ORM
- 建立 `AuthLog` ORM
- 补齐 `common/security/password.py`
- 补齐 `common/security/jwt.py`
- 在 `common/config.py` 中补齐阿里云 PNVS / 邮件推送配置项
- 完成邮箱 + 密码登录最小闭环

### Phase 2

目标：

- 接入阿里云邮件推送 provider
- 实现发送邮箱验证码
- 实现邮箱验证码登录/自动注册
- 实现 `session_token` 和 `vote_token` 双 token 返回

### Phase 3

目标：

- 接入阿里云短信认证服务 provider
- 实现发送手机验证码
- 实现手机验证码登录/自动注册
- 补齐资料修改接口：邮箱、手机、昵称、密码

### Phase 4

目标：

- 实现账号删除
- 补齐活动日志
- 处理 THBWiki / QQ 绑定字段的兼容策略

## 当前不做

本阶段先不做：

- 完整第三方登录流程
- 完整 GraphQL auth schema
- 复杂风控系统
- 多设备会话管理

这些能力可以在 `auth` 基础闭环完成后再补。
