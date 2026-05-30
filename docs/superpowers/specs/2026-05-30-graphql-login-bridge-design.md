# GraphQL 登录桥接设计稿

> 创建日期：2026-05-30
> 最后更新：2026-05-30
> 状态：设计已定稿，待进入 writing-plans

## 一、目标与背景

前端 `Touhou-Vote/packages/vote` 的登录页 `LoginBox.vue` **全部通过 GraphQL mutation** 调后端登录；但 Python 后端 `thvote-be-re` 的 GraphQL schema 当前只有提交（submit）与结果（result），**没有任何登录 mutation**——登录逻辑只存在于 REST 路由 `/user/login-*`。因此前端登录在联调第一步就会断（前端打 `loginPhone` 等字段 → 后端报"字段不存在"）。

实测验证（2026-05-30）：公网 `vote.thwiki.cc/v11-be/graphql` 当前是**老 Rust 系统**，它的 GraphQL 有完整登录 mutation，错误信息放在 `extensions` 里。我们要让 Python 后端对齐这套既定契约。

**决策**：改后端，给 Python 补一层 GraphQL `UserMutation` 包装现有 `UserService`（前端零改动，契约沿用旧 Rust gateway 命名）。

## 二、范围

**本次只做登录页用到的 5 个 mutation**：

| GraphQL mutation | 入参 | 复用的 service 方法 | 返回 |
|---|---|---|---|
| `requestPhoneCode(phone)` | phone | `send_sms_code(SendSmsCodeRequest)` | `Boolean!` |
| `requestEmailCode(email)` | email | `send_email_code(SendEmailCodeRequest)` | `Boolean!` |
| `loginPhone(phone, nickname, verifyCode)` | phone / nickname? / verifyCode | `login_with_phone_code(LoginPhoneRequest)` | `LoginResult!` |
| `loginEmail(email, nickname, verifyCode)` | email / nickname? / verifyCode | `login_with_email_code(LoginEmailRequest)` | `LoginResult!` |
| `loginEmailPassword(email, password)` | email / password | `login_with_email_password(LoginEmailPasswordRequest)` | `LoginResult!` |

**不在本次范围**（留待后续单独做）：
- UserSettings 用的 `updateEmail/updatePhone/updateNickname/updatePassword`、`removeVoter`、`tokenStatus`、`GET /me` 的 GraphQL 化
- PatchyVideo SSO；老用户密码登录依赖的 MongoDB→PG 历史数据回填（B-008，未做——见 §九）

## 三、架构与文件改动

| 文件 | 改动 |
|---|---|
| `src/api/graphql/types.py` | 新增 `VoterFEType`、`LoginResult`，以及 `login_result_from_pydantic()` 转换函数 |
| `src/api/graphql/resolvers/user.py` | **新建**：`UserMutation`（5 个 resolver）+ `map_app_errors()` 错误映射 helper + `_client_ip_from_info()` |
| `src/api/graphql/schema.py` | `class Mutation(SubmitMutation, UserMutation)` |
| `src/common/exceptions.py` | `AppException` 增加可选字段 `error_message`、`upstream_response_string`（向后兼容，默认 None） |
| `src/common/aliyun/pnvs_client.py` | 失败路径把阿里云 `code`/`message` 填进异常的 `upstream_response_string`/`error_message`（目前只 log，没挂到异常上） |

REST 端点 `/user/login-*` **保留不动**（双传输）。业务逻辑 100% 复用 `UserService`，GraphQL 层只做「参数组装 + 限流 + 错误翻译 + 类型转换」，与现有 `resolvers/submit.py` 的薄封装风格一致。

### 数据流（以 `loginPhone` 为例）

```
前端 mutation loginPhone(phone, nickname, verifyCode)
  → UserMutation.login_phone(info, phone, nickname, verifyCode)
      ├─ client_ip = _client_ip_from_info(info)          # 复用 B-009 trusted-proxy 逻辑
      ├─ rate_limit(f"login-{client_ip}", window=60, max_requests=5)
      ├─ req = LoginPhoneRequest(phone=..., nickname=..., verify_code=...,
      │                          meta=Meta(user_ip=client_ip), sid=None)
      ├─ async with map_app_errors(service="user-manager"):
      │     async for db in get_db_session():
      │         service = UserService(UserDAO(db), ActivityLogDAO(db), redis=...)
      │         resp = await service.login_with_phone_code(req)   # LoginResponse(Pydantic)
      └─ return login_result_from_pydantic(resp)         # → LoginResult（Strawberry 自动 camelCase）
```

## 四、GraphQL 类型

> Python 类名用 `VoterFEType` / `LoginResult`（避免与 Pydantic `VoterFE` 撞名）；GraphQL 暴露名见下方 SDL（`VoterFE` 经 Strawberry `name=` 指定）。

```
type VoterFE {            # Strawberry 自动 snake→camel
  username: String
  pfp: String
  password: Boolean!      # 是否设了密码（VoterFE.password 是 bool）
  phone: String
  email: String
  thbwiki: Boolean!
  patchyvideo: Boolean!
  createdAt: DateTime!    # 由 created_at 映射
}

type LoginResult {
  user: VoterFE!
  sessionToken: String!   # 由 session_token
  voteToken: String!      # 由 vote_token；未验证/非投票期为 ""（沿用现有语义）
}
```

字段与前端 `LoginBox.vue` 请求的 `user { username pfp password phone email thbwiki patchyvideo createdAt }` + `sessionToken` + `voteToken` 逐字段对齐。前端不传 `meta`/`sid`，由 resolver 填 `meta.user_ip` 并置 `sid=None`。

## 五、错误映射（方案 B：对齐 Rust extension shape）

实测老 Rust 的错误结构是：
```json
{"message":"Error","extensions":{
  "service":"sms-service","url":null,"error_kind":"SMS_FAILED",
  "error_message":null,"human_readable_message":null,
  "upstream_response_string":"101110"}}
```

为迁移期字节级兼容（并尽量多透传诊断信息），`map_app_errors()` 复刻这套结构：

```python
# resolvers/user.py 伪代码
@asynccontextmanager
async def map_app_errors(service: str):
    try:
        yield
    except AppException as exc:
        raise GraphQLError("Error", extensions={
            "service": service,
            "url": None,
            "error_kind": exc.message,                       # message 本身即 code
            "error_message": getattr(exc, "error_message", None),
            "human_readable_message": None,
            "upstream_response_string": getattr(exc, "upstream_response_string", None),
        })
    except Exception:
        raise GraphQLError("Error", extensions={
            "service": service, "url": None, "error_kind": "INTERNAL_ERROR",
            "error_message": None, "human_readable_message": None,
            "upstream_response_string": None,
        })
```

- `error_kind` 直接取 `exc.message`——后端异常 message 本就是 `INCORRECT_PASSWORD`/`INCORRECT_VERIFY_CODE`/`REQUEST_TOO_FREQUENT` 等 code，零查表。
- `service` 按域填：`requestPhoneCode`→`"sms-service"`，`requestEmailCode`→`"mail-service"`，登录三个→`"user-manager"`（模仿 Rust 微服务名；前端不读它，纯为兼容）。
- 意外异常 → `INTERNAL_ERROR`，不泄露内部细节。
- `human_readable_message` 暂固定 null（Rust 实测也是 null）。

### 5.1 上游码透传（复刻 Rust `upstream_response_string`）

当前 `pnvs_client.py` 在失败时把阿里云 `code`/`message` **只写进了 log**，没挂到异常上。本次：

1. `AppException.__init__` 增加 `error_message: str | None = None`、`upstream_response_string: str | None = None` 两个可选参数（默认 None，**不影响**现有 `details`-as-status 用法与所有现存调用点）。
2. `pnvs_client._parse_send_response` 与 transport except 块，在 raise 时带上：
   - `upstream_response_string` = 阿里云返回的 `code`（如 `isv.BUSINESS_LIMIT_CONTROL`）
   - `error_message` = 阿里云 `message`
3. 同理可给邮件 `dm_smtp_client` 失败路径补（best-effort；SMTP 错误不一定有结构化 code）。
4. GraphQL `map_app_errors` 自动把这俩字段透传到 extensions。

这样前端/排障方看到的诊断信息与 Rust 对齐（拿到上游真实失败码），而前端登录 UI 对短信失败仍只显示"网络错误"（它只 switch `error_kind`，见 §六）。

## 六、错误码 ↔ 前端行为对照

前端 `LoginBox.vue` 只读 `extensions.error_kind`，并 switch 这些值：

| 前端分支 | error_kind | 后端来源 |
|---|---|---|
| "请输入正确的验证码！" | `INCORRECT_VERIFY_CODE` | `email_code/sms_code.consume` 抛 `ValidationError("INCORRECT_VERIFY_CODE")` |
| "密码错误！" | `INCORRECT_PASSWORD` | `login_with_email_password` 抛 `ValidationError("INCORRECT_PASSWORD")` |
| "该用户不存在！"（仅旧版登录框） | `NOT_FOUND` | **后端不会发**——见 §九 已知差异 |
| "请求过于频繁！" | `REQUEST_TOO_FREQUENT` | 登录限流 / 验证码 service 守卫 / PNVS 限流码 |
| 兜底"网络错误！请稍后重试" | 其他一切（含 `SMS_SEND_FAILED`/`INTERNAL_ERROR`） | — |

## 七、客户端 IP 与限流

- **客户端 IP**：从 `info.context["request"]`（Strawberry FastAPI 集成默认注入 request）取 FastAPI Request，复用 B-009 的 trusted-proxy 逻辑（`X-Forwarded-For` 可信代理链，回落 `request.client.host`），写进 `meta.user_ip`。需确认 GraphQLRouter 的 context 含 request（实现期 spike 验证；若默认不含则自定义 context_getter）。
- **限流**（对齐 REST）：
  - 登录三个 mutation：`rate_limit(f"login-{client_ip or 'unknown'}", window=60, max_requests=5)`。
  - `requestPhoneCode`/`requestEmailCode`：沿用验证码 service 内置发送频率守卫（已抛 `REQUEST_TOO_FREQUENT`），不额外加（与 REST send-code 端点行为一致）。

## 八、测试策略（TDD，先写失败测试）

| 层 | 覆盖 |
|---|---|
| 单元 | `map_app_errors`：各类 `AppException`→extensions 结构正确、`error_kind`/`upstream_response_string` 透传对、非 AppException→`INTERNAL_ERROR`。`pnvs_client` 失败时异常带上 `upstream_response_string`。 |
| 集成（`schema.execute`） | 5 个 mutation 各跑成功路径 + 关键错误路径（错验证码→`INCORRECT_VERIFY_CODE`、错密码→`INCORRECT_PASSWORD`、超限→`REQUEST_TOO_FREQUENT`）。复用现有 fakeredis / 测试 DB / mock 验证码 service 夹具（同 REST 集成测试）。 |
| 契约 | 内省 schema，断言 5 个字段存在、参数/返回名为 camelCase（`verifyCode`/`sessionToken`/`createdAt`）、`LoginResult`/`VoterFE` 结构——锁死前端 codegen 契约。 |

**不重测业务逻辑**（`UserService` 已有测试），GraphQL 层只测「组装 + 错误翻译 + 类型转换」。

## 九、已知差异与约束

- **`NOT_FOUND` 前端分支不会触发**：`login_with_email_password` 对"用户不存在"也返回 `INCORRECT_PASSWORD`（防用户枚举，与 Rust 安全策略一致）。前端旧版登录框的"该用户不存在！"分支因此永远不亮，统一显示"密码错误！"。**这是刻意保留的安全行为**，不修。
- **老用户密码登录需要数据**：`loginEmailPassword` 能跑通，但老用户的 email+password 必须先从 MongoDB 回填到 PG（BACKLOG **B-008**，目前仅设计稿、未实现）。在回填前，只有新注册（手机/邮箱验证码）的用户能登录；老用户密码登录会因查无此人而返回 `INCORRECT_PASSWORD`。
- **联调链路**：前端走路线 A（CI 部署 `:8082`，nginx `/v11-be/` → `thvote-backend:8000`）。本设计落地并部署到测试机 `:18000` 后，前端 `:8082` 才能真正登录。详见记忆 `frontend-deploy-pipeline` / `deployment-topology`。

## 十、回滚策略

纯增量：新增 `UserMutation` + 类型 + 异常可选字段，不改任何现有 REST/submit/result 行为。回滚只需从 root `Mutation` 摘掉 `UserMutation`（或 revert 整个 commit），现有功能不受影响。`AppException` 新增字段有默认值，旧调用点与 REST 错误映射 `_raise_http` 不受影响。

## 十一、changelog / 文档联动

- `docs/CHANGELOG.md`：落地时加 `Added: GraphQL 登录 mutation 桥接` 条目，注明 GraphQL schema 变更（CLAUDE.md §8）。
- `REFACTOR_TODO.md`：用户与认证模块补「GraphQL 登录 mutation 已桥接」。
- 若上游码透传改动 `pnvs_client` 行为，CHANGELOG 注明。
