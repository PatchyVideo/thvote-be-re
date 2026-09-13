# 生产上线待办清单

> 创建日期：2026-09-13（来源：B-065 修复后的全站权限扫描，见 CHANGELOG 2026-09-13）
> 性质：**上线前必须逐条勾掉**的硬性项。每项写明"现状 / 要做什么 / 怎么验证"。测试机（154.37.215.62）可以保持现状；公网生产环境不允许带着任何未勾项上线。
> 维护规则：新增上线前硬性项时，同时在这里加一行；做完打 ✅ 并写日期。

## 一、必须做（未做即不允许公开）

| # | 项 | 现状（2026-09-13） | 要做什么 | 怎么验证 |
|---|---|---|---|---|
| P-1 | **关闭 `/docs`、`/redoc`、`/openapi.json` 和 GraphiQL** | `src/main.py` 创建 `FastAPI(...)` 时没传 `docs_url=None` 等；`AppGraphQLRouter(graphql_schema)` 没传 `graphql_ide=None`，Strawberry 默认开 GraphiQL。测试机实测四个地址都 200，`openapi.json` 110KB 含全部 admin 端点定义，经 nginx `/v12-be/` 公网可达 | 加一个配置开关（建议 `EXPOSE_API_DOCS`，默认 `false`），生产关、测试机可开。改 `src/main.py` 两处 | `curl -o /dev/null -w '%{http_code}' https://<prod>/v12-be/docs` 与 `/openapi.json`、`GET /graphql`（`Accept: text/html`）都应为 404 |
| P-2 | **admin IP 白名单必须配置** | `require_admin` 的 IP 检查在 `ADMIN_ALLOWED_IPS` 为空时**放行任意 IP**（`src/apps/admin/deps.py` `_ip_allowed`，设计上的逃生舱）。测试机当前为空，只靠 `X-Admin-Secret` 一道门 | Nacos `thvote_be` 配 `ADMIN_ALLOWED_IPS`（运营出口 IP / VPN 网段，CIDR 可用）。同时 `TRUSTED_PROXY_IPS` 必须填 nginx 容器/主机地址，否则后端看到的永远是代理 IP，白名单形同虚设 | 白名单外 IP 带正确密钥访问 `/api/v1/admin/users` 应 403；白名单内 200 |
| P-3 | **`ADMIN_SECRET` 换强值** | 测试机为弱值 `abc123`（B-042） | 生成 ≥32 字节随机串写入 Nacos；admin-ui 登录框重新输入 | 旧值 403 |
| P-4 | **移除测试登录旁路** | `TEST_LOGIN_BYPASS_*` 代码与配置仍在（`grep -r TEST_LOGIN_BYPASS src`）。默认配置为空时不生效，但公开前应整体删除，不留"配错即开门"的可能 | 删代码 + Nacos 删键；见 `docs/superpowers/specs/2026-08-14-test-login-bypass-design.md` 移除条件 | `grep -r TEST_LOGIN_BYPASS src` 为空；假号 19900000001 + 888888 登录失败 |
| P-5 | **CORS 收紧** | `CORS_ALLOWED_ORIGINS` 默认 `["*"]` 且 `allow_credentials=True`。当前无 cookie 所以无害；一旦引入 cookie 会变成任意源带凭据 | 生产填前端真实域名列表 | 预检请求带陌生 `Origin` 不应返回 `Access-Control-Allow-Origin` |
| P-6 | **前端截止时间改回** | Touhou-Vote `shared/data/time.ts` 的 `deadline` 临时改成 2099（见 `docs/migration/api-contract-audit-2026-07-14.md`） | 改回真实截止时间，或切到后端 `/voting-status/`（现需 `vote_token`） | 前端在截止后拒绝提交 |

## 二、建议做（影响面较小，但属于同一批扫描结论）

| # | 项 | 现状 | 建议 |
|---|---|---|---|
| S-1 | OAuth `state` 不校验、SSO `sid` 不绑定发起会话 | `src/apps/user/router.py` 的 qq/thbwiki 回调收 `state` 但从不比对；`sid` 谁拿到谁都能在登录体里带上并入自己账号。**当前前端未接 SSO、GraphQL 登录不传 `sid`，路径不可达** | 接 SSO 之前：`state` 落 Redis 一次性校验；`sid` 绑定到发起端（cookie 或 state 派生） |
| S-2 | 密码登录用户枚举计时侧信道 | 邮箱不存在时不跑 Argon2 直接返回 | 对不存在的账号也跑一次 dummy 验证 |
| S-3 | `REQUIRE_BROWSER_ORIGIN` 默认关 | 打开后若 CORS 仍为 `*`，退化为"有 Origin 就放行" | 与 P-5 一起：先收紧 CORS 再开此项 |
| S-4 | 自动补全 `limit`、提名列表 `page_size` 无上限 | 性能面，非泄露 | 服务端 cap 到 50/100 |
| S-5 | 验证码人机门控切公家账户 | 见 `docs/operations/captcha-onboarding.md` §六（B-043 尾项） | 等上游 |
| S-6 | Pixiv 凭据 | 未配（B-042②），且可能不再需要 | 拍板要不要 Pixiv 源 |

## 三、已经关掉的（留档，防止回退）

- 6 个 REST 回读接口按 `vote_token` 鉴权，提交接口 `vote_id` 绑定 token（B-065，PR #34，2026-09-13）。
- `POST /scraper/scrape` per-IP 限流 10 次/分钟（2026-09-13）。
- 邮箱验证码错 5 次作废（2026-09-13）。
- `main.py` 的 `/admin/reload-config`、`/admin/discover*` 已挂 `require_admin`（B-042①）。
- admin 三个路由器都在路由器级挂 `require_admin`，密钥为空 fail-closed，常量时间比较；回归测试 `tests/integration/test_admin_auth.py`。
- session/vote token 用 `aud` 隔离，算法固定，缺密钥启动失败；投票窗口在签发与每次解码时都生效。
