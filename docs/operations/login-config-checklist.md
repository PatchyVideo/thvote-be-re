# 登录模块 Nacos 配置清单(待填)

> 创建日期：2026-05-30
> 最后更新：2026-05-30
>
> 用途：列出登录模块各登录方式所需的 Nacos 配置项,作为运维/接入方"照着填"的清单。
> 关联：登录方式实现见 `src/apps/user/`,GraphQL 桥接见设计稿 `docs/superpowers/specs/2026-05-30-graphql-login-bridge-design.md`;Nacos 接入机制见 `nacos-config-center.md`。

---

## 0. 当前状态 / 阻塞

- **填写位置**:测试环境 R-NACOS,dataId **`thvote_be`**(下划线)、Group `DEFAULT_GROUP`、命名空间 ID `dfacd6e1-b442-476c-bffe-ff5504651c39`。
- **访问入口**:鉴权控制台 **`http://154.37.215.62:10848/rnacos/`**(不是 8848;详见 `nacos-config-center.md` §四"R-NACOS 控制台")。
- **🔴 阻塞中(2026-05-30)**:等环境所有者提供 **R-NACOS 控制台管理员账号**。拿到后按下方清单逐项填。

---

## 1. 登录方式总览

| 方式 | 端点(REST / GraphQL) | 依赖外部服务 | 需要的配置组 |
|---|---|---|---|
| 邮箱验证码 | `login-email` / `loginEmail` (+ send/request code) | 阿里云 DirectMail(SMTP) | A + C |
| 手机短信验证码 | `login-phone` / `loginPhone` (+ send/request code) | 阿里云 PNVS(短信) | A + B |
| 邮箱+密码("旧版账号") | `login-email-password` / `loginEmailPassword` | 无(仅 DB) | A(+ 老用户数据需 B-008 回填) |
| OAuth:QQ | `/sso/qq/*` | QQ 互联 | A + D(QQ) |
| OAuth:THBWiki | `/sso/thbwiki/*` | THBWiki OAuth2 | A + D(THBWiki) |

> OAuth 当前是**绑定**机制,非独立登录入口:授权 callback 返回 `sid`,仍用邮箱/手机/密码登录(带 `sid`)时把 SSO 身份合并到账号。PatchyVideo SSO **未实现**。

---

## 2. 配置清单(按组,勾选填写进度)

> 所有 value 在 Nacos JSON 里都用**字符串**(外层带引号)。

### A. 通用必填(所有登录都依赖)

- [ ] `JWT_SECRET_KEY` —— 签 session_token / vote_token;缺了登录直接失败。改成强随机串。
- [ ] `DATABASE_URL` —— 如 `postgresql+asyncpg://USER:PASS@RDS_HOST:5432/thvote`
- [ ] `REDIS_URL` —— 邮箱验证码存 Redis + 限流,如 `redis://:PASS@HOST:6379/0`
- [ ] `CORS_ALLOWED_ORIGINS` —— 前端域名 JSON 数组,如 `["https://vote.thwiki.cc"]`
- [ ] `VOTE_YEAR` / `VOTE_START_ISO` / `VOTE_END_ISO` —— 决定 vote_token 签发窗口(建议填)
- [ ] `TRUSTED_PROXY_IPS` —— 代理后取真实 IP(影响限流准确),如 `["<nginx内网IP>"]`(建议填)

### B. 短信登录(阿里云 PNVS)

- [ ] `ALIYUN_PNVS_ACCESS_KEY_ID` ✅必填
- [ ] `ALIYUN_PNVS_ACCESS_KEY_SECRET` ✅必填
- [ ] `ALIYUN_PNVS_ENDPOINT` ✅必填 —— `dypnsapi.aliyuncs.com`
- [ ] `ALIYUN_PNVS_SMS_SIGN_NAME` ✅必填 —— 短信签名
- [ ] `ALIYUN_PNVS_SMS_TEMPLATE_CODE` ✅必填 —— `SMS_xxxxxxxx`
- [ ] `ALIYUN_PNVS_REGION_ID` —— 可选,`cn-hangzhou`
- [ ] `ALIYUN_PNVS_SCHEME_NAME` —— 可选
- [ ] `ALIYUN_PNVS_CODE_LENGTH` / `_VALID_TIME` / `_INTERVAL` —— 可选,`6` / `300` / `120`
- [ ] `ALIYUN_PNVS_TEMPLATE_PARAM` —— 可选,默认 `{"code":"##code##"}`。**若模板有除 code 外的变量(如有效期 min),必须填匹配的 JSON**,否则报「模板内容与模板参数不匹配」(SMS_SEND_FAILED)。例:模板 `100001` 需 `{"code":"##code##","min":"5"}`,在 Nacos 里写 `"ALIYUN_PNVS_TEMPLATE_PARAM": "{\"code\":\"##code##\",\"min\":\"5\"}"`

> 前 5 个(AK ID/Secret/Endpoint/签名/模板)缺任一 → 发短信抛 `ALIYUN_NOT_CONFIGURED`。`##code##` 是 PNVS 自动填验证码的占位符,不要自己填值。

### C. 邮箱登录(阿里云 DirectMail,走 SMTP)

- [ ] `ALIYUN_DM_SMTP_HOST` ✅必填 —— `smtpdm.aliyun.com`
- [ ] `ALIYUN_DM_SMTP_USERNAME` ✅必填 —— 发信地址
- [ ] `ALIYUN_DM_SMTP_PASSWORD` ✅必填 —— DM 发信地址的 SMTP 密码
- [ ] `ALIYUN_DM_ACCOUNT_NAME` ✅必填 —— 发信地址(From),通常同 username
- [ ] `ALIYUN_DM_SMTP_PORT` —— 可选,默认 `465`
- [ ] `ALIYUN_DM_FROM_ALIAS` —— 可选,显示名,默认 `THVote`
- [ ] `ALIYUN_DM_TAG_NAME` —— 可选

> 邮件走 SMTP 路径,所以 `ALIYUN_DM_ACCESS_KEY_ID/SECRET/ENDPOINT/REGION_ID`(API 模式)**当前用不到,不必填**。

### D. OAuth(只在启用对应 SSO 时填)

- [ ] `QQ_APP_ID` / `QQ_APP_SECRET` —— QQ 登录
- [ ] `THBWIKI_CLIENT_ID` / `THBWIKI_CLIENT_SECRET` —— THBWiki 登录
- [ ] `SSO_CALLBACK_BASE_URL` —— 两者共用,OAuth 回调基地址,如 `https://vote.thwiki.cc/v11-be`

---

## 3. 可直接粘的 JSON 骨架

```json
{
  "JWT_SECRET_KEY": "<强随机串>",
  "DATABASE_URL": "postgresql+asyncpg://USER:PASS@RDS_HOST:5432/thvote",
  "REDIS_URL": "redis://:PASS@REDIS_HOST:6379/0",
  "CORS_ALLOWED_ORIGINS": "[\"https://vote.thwiki.cc\"]",
  "VOTE_YEAR": "2026",
  "VOTE_START_ISO": "2026-01-01T00:00:00+08:00",
  "VOTE_END_ISO": "2026-12-31T23:59:59+08:00",
  "TRUSTED_PROXY_IPS": "[]",

  "ALIYUN_PNVS_ACCESS_KEY_ID": "LTAI...",
  "ALIYUN_PNVS_ACCESS_KEY_SECRET": "...",
  "ALIYUN_PNVS_ENDPOINT": "dypnsapi.aliyuncs.com",
  "ALIYUN_PNVS_REGION_ID": "cn-hangzhou",
  "ALIYUN_PNVS_SMS_SIGN_NAME": "<短信签名>",
  "ALIYUN_PNVS_SMS_TEMPLATE_CODE": "SMS_xxxxxxxx",

  "ALIYUN_DM_SMTP_HOST": "smtpdm.aliyun.com",
  "ALIYUN_DM_SMTP_PORT": "465",
  "ALIYUN_DM_SMTP_USERNAME": "noreply@your-domain",
  "ALIYUN_DM_SMTP_PASSWORD": "...",
  "ALIYUN_DM_ACCOUNT_NAME": "noreply@your-domain",
  "ALIYUN_DM_FROM_ALIAS": "THVote",

  "QQ_APP_ID": "",
  "QQ_APP_SECRET": "",
  "THBWIKI_CLIENT_ID": "",
  "THBWIKI_CLIENT_SECRET": "",
  "SSO_CALLBACK_BASE_URL": "https://vote.thwiki.cc/v11-be"
}
```

---

## 4. 填完之后

1. **重启后端容器**:`docker restart thvote-backend` —— Nacos 改了不重启不生效(lru_cache 客户端,见 BACKLOG B-017)。
2. **最小可登路径**:A 组 + (B 短信 或 C 邮件)其一即可让验证码登录跑通;OAuth(D)和密码登录可后补。
3. **密码登录**:代码就绪,但老用户密码数据需 **B-008(MongoDB→PG 回填)** 才有,否则老用户登录会"密码错误"。
4. 验证:`GET http://154.37.215.62:18000/health` 看后端起没起;前端把代理指到 `:18000` 后试登录。
