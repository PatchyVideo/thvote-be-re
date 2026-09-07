# 测试登录旁路(白名单固定验证码)设计

> **状态**：已实施 —— 已于 2026-08-14 实现并上线（`TEST_LOGIN_BYPASS_ACCOUNTS`/`TEST_LOGIN_BYPASS_CODE`，见 [CHANGELOG 2026-08-14](../../CHANGELOG.md)）。
> 本文件是**设计稿**，记录当时的设计意图与取舍；实现细节可能已演进。状态核对于 2026-08-31。

> 日期:2026-08-14
> ⚠️ **临时测试设施——公开上线前必须整体移除**,全量定位方式:`grep -r TEST_LOGIN_BYPASS`

## 一、目的

测试期需要自动化跑通"登录 → 投票"全链路(包括 Claude 起浏览器做端到端验证)。当前链路上有两道对自动化不可逾越的闸:

1. 发验证码前的阿里云 captcha 滑块(B-043,前端 widget 挡在发码按钮前);
2. 验证码本体——短信/邮件真发到手机/邮箱,自动化收不到。且 SMS 码状态在阿里云 PNVS 侧(`send_sms_verify_code`/`check_sms_verify_code`),本地无存储,无法"发码侧塞假码"。

## 二、方案(已选 A:验码侧白名单固定码)

在 `SmsCodeService.consume` / `EmailCodeService.consume` **顶部短路**:

> 若旁路已激活 且 identifier ∈ 白名单 且 submitted_code == 固定码 → 直接放行(不打 PNVS / 不查邮件码存储)。

自动化路径:填白名单假号 → 直接填固定码 → 登录成功。**全程不触发发码**,captcha widget、PNVS、发码限流都不在路径上。真人测试(真手机号)完全走原链路,不受影响。

否决的备选:B) 发码侧 bypass——SMS 码在阿里云,本地无处可塞,只对 email 有效且自动化仍要绕前端 widget;C) captcha mock 全局开关——污染所有账号的测试真实性。

## 三、配置(只配测试 Nacos `thvote_be`,生产 dataId 永不配置)

| key | 类型 | 默认 | 说明 |
|---|---|---|---|
| `TEST_LOGIN_BYPASS_ACCOUNTS` | JSON 字符串数组 | `[]` | 允许旁路的手机号/邮箱,只放假号(如 `19900000001`、`test1@example.com`) |
| `TEST_LOGIN_BYPASS_CODE` | 字符串 | `""` | 固定验证码(如 `888888`) |

**双非空才激活**;默认双空 = 功能不存在(fail-closed)。环境变量优先级同现有 Settings 规则。

## 四、实现

- 新模块 `src/common/verification/test_bypass.py`:`is_test_login_bypass(identifier: str, submitted_code: str) -> bool`。
  - 读 `get_settings()`;双非空 + identifier 命中 + 码相等(常量时间比较不必要——测试设施,直接 `==`)才返回 True。
  - 命中时打 `logger.warning("TEST LOGIN BYPASS used for %s", masked_identifier)`,identifier 脱敏(手机号留前3后2,邮箱留首字符+域名)。
- `SmsCodeService.consume` / `EmailCodeService.consume` 第一行:
  `if is_test_login_bypass(phone, submitted_code): return`。
- 不改 GraphQL/REST 契约,不改前端。

## 五、安全边界

- 激活条件是两个配置**同时**非空,生产 Nacos 不配即天然关闭;
- 白名单是显式枚举,不支持通配;
- 旁路只替代"验证码校验"这一步,后续用户创建/JWT 签发/审计日志全走正常路径;
- 每次命中都有 WARNING 日志留痕。

## 六、移除条件(CLAUDE.md §5 要求)

公开上线前删除:`test_bypass.py`、两个 `consume` 里的短路行、`config.py` 两个字段、本设计稿标记废弃、测试 Nacos 删两个 key。`grep -r TEST_LOGIN_BYPASS` 全量定位,预计 10 分钟。

## 七、测试

单测(pytest,不打外网):
1. 双配置就绪 + 白名单账号 + 固定码 → consume 放行(PNVS/存储 mock 断言**未被调用**);
2. 码错 → 走原路径(mock 被调用);
3. 账号不在白名单 → 走原路径;
4. 配置为空(默认)→ 走原路径;
5. email 侧同样覆盖命中/未命中。

## 八、实施计划(小特性,单 PR)

1. 失败测试先行(上述 5 例)→ 2. `test_bypass.py` + config 字段 + 两行短路 → 3. 全量 pytest + flake8 → 4. 文档(captcha-onboarding 附注 + CHANGELOG)→ 5. PR → main → 自动部署 → 6. 测试 Nacos 配两个 key + 重启容器(workflow_dispatch)→ 7. 浏览器实测登录。
