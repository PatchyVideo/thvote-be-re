# REFACTOR_TODO.md — 重构进度总览

> 创建日期：2026-05-12
> 最后更新：2026-05-30（与 main 对账：SSO/B-007 已落地、autocomplete 角色+音乐已实现、B-017/018/025/027/029/030 完成；详见 BACKLOG.md）
>
> **与其他文档的分工：**
> - 本文件：模块级别的"移植完成了多少"——宏观进度看板
> - [`docs/BACKLOG.md`](docs/BACKLOG.md)：具体 bug / 改进 / 技术债逐条跟踪（B-001…B-027+）
> - [`docs/CHANGELOG.md`](docs/CHANGELOG.md)：每次发布的变更记录
> - [`docs/superpowers/specs/`](docs/superpowers/specs/)：各模块设计规格与已知问题原文

---

## 状态图例

| 符号 | 含义 |
|---|---|
| ✅ | 完成且基本可用（可能仍有 BACKLOG 条目） |
| ⚠️ | 部分完成 / 骨架已有，核心逻辑待填 |
| ❌ | 未实现（仅 stub / NotImplementedError / 空返回） |
| 🔴 | 高优先级阻塞项 |
| 🟡 | 中优先级，依赖其他模块 merge 后做 |
| 🟢 | 可立即并行开工 |

---

## 快速状态总览

| 模块 | 对应 Rust 服务 | Python 路由 | 状态 | 备注 |
|---|---|---|---|---|
| 用户与认证 | `user-manager` | `apps/user` | ✅ | 12 端点 + SSO（QQ/THBWiki，B-007 已落地），有测试 |
| 投票提交（原始）| `submit-handler` | `apps/submit` | ✅ | 11 端点 + vote_token 鉴权 + 测试（2026-05-13）|
| 投票数据（处理后）| `vote-data`（Rust 存根）| `apps/vote_data` | ✅ | Python 新增，非 Rust 移植 |
| 查询结果 | `result-query` | `apps/result` | ✅ | 9 端点 + ComputeService + Redis 缓存（2026-05-13）|
| 自动补全 | `autocomplete`（Rust 存根）| `apps/autocomplete` | ⚠️ | 角色/音乐 candidate 表 ILIKE 已实现；**CP 搜索 `search_cps()` 仍 `return []`** |
| 爬虫 | `scraper`（Python）| `apps/scraper` | ✅ | 16/18 站点（全部旧后端站点已移植，2026-05-14）|
| GraphQL | `gateway` | `api/graphql` | ✅ | submit + ResultQuery 8 个字段，JSON scalar（2026-05-13）|
| 数据库迁移 | — | `alembic/versions/` | ✅ | 0001+0002+0003+0004（0004=SSO 列）已覆盖所有表 |
| 基础设施公共层 | — | `common/` | ✅ | config/db/redis/jwt/rate_limit 已就绪 |

---

## 一、基础设施 / 公共层 ✅

**对应 Rust：** 各服务的 `common.rs / context.rs`，Python 侧全部统一在 `src/common/`。

| 组件 | 文件 | 状态 |
|---|---|---|
| 配置（Nacos + env；Apollo 已移除）| `common/config.py` | ✅（B-030 lazy load 已修）|
| 数据库引擎（async，多方言）| `common/database.py` | ✅ |
| Redis 客户端 | `common/redis.py` | ✅ |
| JWT 签发/校验 | `common/security/jwt.py` | ✅ |
| 密码哈希（argon2/bcrypt 升级）| `common/security/password.py` | ✅ |
| 限流中间件（原子 INCR+EXPIRE）| `common/middleware/rate_limit.py` | ✅（B-005 已修） |
| 阿里云 PNVS 客户端 | `common/aliyun/pnvs_client.py` | ✅ |
| 阿里云 DirectMail SMTP | `common/aliyun/dm_smtp_client.py` | ✅ |
| 邮件验证码服务 | `common/verification/email_code.py` | ✅ |
| 短信验证码服务（全托管）| `common/verification/sms_code.py` | ✅ |
| 异常体系 | `common/exceptions.py` | ✅ |
| 请求日志中间件 | `common/middleware/logging.py` | ✅ |
| CORS（可配置域名列表）| `src/main.py` | ✅（B-004 已修，env CORS_ALLOWED_ORIGINS）|
| trusted proxies / X-Forwarded-For | `apps/user/deps.py` | ✅（B-009 已修，env TRUSTED_PROXY_IPS）|
| 热更新（`/admin/reload-config`）| `src/main.py` | ✅ |
| 服务器时间端点（`GET /server-time`）| — | ❌ 旧 gateway 有，未移植 |
| mypy CI 硬门禁 | `mypy.ini` / CI | 🟢 [B-020] |
| Pydantic V2 迁移 | 全 `common/` | 🟢 [B-021] |

**BACKLOG 关联：** ~~B-004~~✅ ~~B-009~~✅ ~~B-017~~✅ ~~B-025~~✅ ~~B-027~~✅ ~~B-030~~✅；仍开放：B-020（mypy 硬门禁）, B-021（Pydantic V2）, B-026（DB 治理纪律，阻塞已解除）, B-031（Nacos JSON 容错分支）

---

## 二、用户与认证 ✅

**对应 Rust：** `user-manager/src/`（handlers.rs / jwt.rs / new_login.rs / email_service.rs / sms_service.rs 等）

**设计规格：** [`docs/superpowers/specs/2026-04-27-user-auth-design.md`](docs/superpowers/specs/2026-04-27-user-auth-design.md)

所有 12 个端点已实现并有基础测试：

| 端点 | 状态 | 测试 |
|---|---|---|
| `POST /user/send-email-code` | ✅ | 单元 ✅ |
| `POST /user/send-sms-code` | ✅ | 单元 ✅ |
| `POST /user/login-email-password` | ✅ | 集成 ✅ |
| `POST /user/login-email` | ✅ | 集成 ✅ |
| `POST /user/login-phone` | ✅ | 集成 ✅ |
| `POST /user/update-email` | ✅ | 集成 ✅ |
| `POST /user/update-phone` | ✅ | 集成 ✅ |
| `POST /user/update-nickname` | ✅ | 集成 ✅ |
| `POST /user/update-password` | ✅ | 集成 ✅ |
| `POST /user/remove-voter` | ✅ | 集成 ✅ |
| `POST /user/token-status` | ✅ | 契约 ✅ |
| `GET /user/me` | ✅ | 契约 ✅（集成 ❌ [B-015]）|

**SSO（B-007 已落地，2026-05-17）：**
- Rust 的 `thbwiki_login.rs / qq_binding.rs` → 已迁移：`sso_clients.py` + `sso_session.py`，6 个 SSO 端点（QQ / THBWiki authorize/callback/bind）+ Redis LoginSession + migration 0004（`thbwiki_uid` / `qq_openid` 列）
- **未含**：PatchyVideo SSO、Rust `legacy_login.rs`（旧账号体系，归入 B-008 历史数据回填范畴）

**BACKLOG 关联：**
- ✅ [B-003] submit 端点 vote_token JWT 校验（2026-05-13）
- ✅ [B-007] SSO 接入（2026-05-17）
- ✅ [B-012] `update-password` 单独限流（2026-05-15）
- ✅ [B-014/015/016] vote_token / GET me / bcrypt 升级集成测试（2026-05-15）
- ✅ [B-018] `_safe_log` 失败可见性（2026-05-17）
- ✅ GraphQL 登录 mutation 桥接（2026-05-30）：5 个登录 mutation 包装 UserService，前端 LoginBox 契约打通
- 仍开放：[B-024] `UserDAO.save()` 加 `session.merge()` 防 detached instance；[B-011] 移除 `at_least_one_identifier` 约束（SSO 已落地，阻塞解除）

---

## 三、投票提交（原始层）✅

**对应 Rust：** `submit-handler/src/`（handlers.rs / validator.rs / paper_validator.rs）

**数据表：** `raw_character / raw_music / raw_cp / raw_paper / raw_dojin`（存储原始 JSON payload）

| 端点 | 状态 |
|---|---|
| `POST /character/` | ✅ |
| `POST /music/` | ✅ |
| `POST /cp/` | ✅ |
| `POST /paper/` | ✅ |
| `POST /dojin/` | ✅ |
| `POST /get-character/` | ✅ |
| `POST /get-music/` | ✅ |
| `POST /get-cp/` | ✅ |
| `POST /get-paper/` | ✅ |
| `POST /get-dojin/` | ✅ |
| `POST /voting-status/` | ✅ |
| `POST /voting-statistics/` | ✅ |

**校验逻辑（对应 Rust validator.rs）：**
- 角色：1-8 个，唯一，最多 1 本命，理由 ≤ 4096 字符 ✅
- 音乐：1-12 首，唯一，最多 1 本命 ✅
- CP：1-4 个，最多 1 本命，active 字段校验 ✅
- 问卷：直通 ✅
- 同人：各字段 ≤ 4096 ✅

**BACKLOG 关联：**
- ✅ [B-003] submit 端点 `vote_token` JWT 校验已落地（2026-05-13, `8724e39`）

---

## 四、投票数据（处理后）✅

**Rust 对应：** `vote-data/`（Rust 原版是空存根 `fn main() {}`，Python 侧为新实现）

**数据表：** `character / music / cp / questionnaire`（每用户一行 upsert，存结构化数据）

| 端点 | 状态 |
|---|---|
| `POST /vote-data/character/{user_id}` | ✅ |
| `POST /vote-data/music/{user_id}` | ✅ |
| `POST /vote-data/cp/{user_id}` | ✅ |
| `POST /vote-data/questionnaire/{user_id}` | ✅ |
| `GET /vote-data/summary/{user_id}` | ✅ |

> **注意：** `character / music / cp / questionnaire` 表虽标为"legacy"（在 migration 注释中），但 `vote_data` 服务仍在写入并为 `result` 查询提供数据来源。Result 模块实现时应以这四张表为主要输入。

---

## 五、查询结果 ✅（2026-05-13 完成）

**对应 Rust：** `result-query/src/`

**实现：**
- `ComputeService`：`POST /admin/compute-results` 触发全量计算，写 Redis
- `ResultDAO`：纯 Redis 读取，cache miss → 503
- 9 个端点全部可用（ranking/trends/reasons/global-stats/completion-rates/covote/single/questionnaire/questionnaire-trend）
- Admin 端点：`/admin/import-candidates`、`/admin/finalize-ranking`
- 参考数据表：`candidate_character`、`candidate_music`、`final_ranking`（migration 0003）

**测试：** 13 个单元测试 + 3 个集成测试 + 9 个契约测试

**设计规格：** [`docs/superpowers/specs/2026-05-13-result-query-design.md`](docs/superpowers/specs/2026-05-13-result-query-design.md)

---

## 六、自动补全 ⚠️（角色/音乐已实现，CP 待做）

**对应 Rust：** `autocomplete/`（Rust 原版是空存根，Python 侧为新实现）

**现状：** 路由 + 服务 + DAO 已接通；`candidate_character` / `candidate_music` 表（migration 0003）已作为数据源。

| DAO 方法 | 状态 |
|---|---|
| `search_characters(query, limit)` — `candidate_character` ILIKE | ✅ 已实现 |
| `search_music(query, limit)` — `candidate_music` ILIKE | ✅ 已实现 |
| `search_cps(query, limit)` | ❌ 仍 `return []`（`src/apps/autocomplete/dao.py:56`）|

| 端点 | 状态 |
|---|---|
| `POST /autocomplete/search` | ⚠️ 角色/音乐返回真实结果，CP 永远空 |

### 待实现

- `AutocompleteDAO.search_cps(query, limit)` — 从已提交的 `cp.cp_list` JSON 中提取唯一 CP 名称做模糊匹配（无现成 candidate 表，是唯一缺口）

---

## 七、爬虫 ✅（18 站点全部移植，唯缺测试）

**对应：** 旧 `scraper/`（Python 实现，非 Rust 移植）

**端点：** `POST /scraper/scrape` ✅（Redis 缓存 + UDID 支持）

**站点移植状态（旧版有 18 个站点，全部已移植）：**

| 站点 | 旧版 | 当前 |
|---|---|---|
| `bilibili.py` | ✅ | ✅ |
| `pixiv.py` | ✅ | ✅ |
| `twitter.py` | ✅ | ✅ |
| `nicovideo.py` | ✅ | ✅ |
| `nicoseiga.py` | ✅ | ✅ |
| `youtube.py` | ✅ | ✅（需 `YOUTUBE_API_KEY`）|
| `weibo.py` | ✅ | ✅ |
| `tieba.py` | ✅ | ✅ |
| `steam.py` | ✅ | ✅ |
| `dlsite.py` | ✅ | ✅ |
| `melon.py` | ✅ | ✅ |
| `dizzylab.py` | ✅ | ✅ |
| `acarticle.py` | ✅ | ✅ |
| `acfun.py` | ✅ | ✅ |
| `biliarticle.py` | ✅ | ✅（含于 bilibili.py）|
| `patchyvideo.py` | ✅ | ✅ |
| `pixnovel.py` | ✅ | ✅（含于 pixiv.py）|
| `thbwiki.py` | ✅ | ✅ |

**旧版工具类移植状态：**

| 工具模块 | 旧版 | 当前 |
|---|---|---|
| `biliutils.py` | ✅ | ✅ |
| `cache.py` | ✅ | ✅ |
| `network.py` | ✅ | ✅ |
| `match.py` | ✅ | ✅（逻辑已集成进 process.py）|
| `parse.py` | ✅ | ✅ |

---

## 八、GraphQL API ✅

**对应 Rust：** `gateway/src/`

**现状：**
- `POST /graphql` — Strawberry schema 已挂载 ✅
- `SubmitQuery / SubmitMutation` — 查询/提交投票 ✅
- `ResultQuery` — 8 个字段，JSON scalar，已实现 ✅（2026-05-13）
- `GET /server-time` — 旧 gateway 有，Python 侧**未实现** ❌（低优先级）

---

## 九、数据库迁移 ✅

| 版本 | 内容 | 状态 |
|---|---|---|
| `0001_initial_user_and_activity_log` | `user` + `activity_log` 表 + 索引 | ✅ |
| `0002_voting_tables` | `raw_character/music/cp/paper/dojin` + `character/music/cp/questionnaire` 遗留表 | ✅ |
| `0003_candidate_and_final_ranking` | `candidate_character`、`candidate_music`、`final_ranking` | ✅ |
| `0004_sso_columns` | `user.thbwiki_uid` / `user.qq_openid` SSO 列 | ✅（B-007）|

**BACKLOG 关联：**
- ✅ [B-025] 移除 `init_db()` / `DEBUG` 后门（2026-05-17, `76facaa`；启动改连通性检查）
- 🟢 [B-026] DB 治理纪律（PR 模板 + `alembic check` CI 门禁）——B-025 已完成，阻塞解除，可立即做

> 如果 `autocomplete` 需要新建候选项目表，需要第三张 migration（见第六节"数据来源待定"）。

---

## 十、测试覆盖

### 已有测试

| 文件 | 类型 | 覆盖内容 |
|---|---|---|
| `tests/unit/test_jwt.py` | 单元 | JWT 签发/校验/过期/受众 |
| `tests/unit/test_email_code_service.py` | 单元 | 邮件验证码生成/Redis 守卫/过期 |
| `tests/unit/test_pnvs_client.py` | 单元 | PNVS 客户端调用 mock |
| `tests/unit/test_voter_fe_serialization.py` | 单元 | VoterFE schema 序列化 |
| `tests/unit/test_compute.py` | 单元 | 计算函数（ranking/gender/covote/global-stats/completion-rates）|
| `tests/unit/test_submit_validator.py` | 单元 | SubmitValidator 全部 5 类校验 |
| `tests/unit/test_autocomplete_service.py` | 单元 | 自动补全 limit 分配逻辑 |
| `tests/integration/test_login_flows.py` | 集成 | 邮件/手机/密码三种登录流 |
| `tests/integration/test_update_and_remove.py` | 集成 | update-email/phone/nickname/password/remove-voter |
| `tests/integration/test_vote_token_and_me.py` | 集成 | vote_token 签发 4 场景 + GET /me + bcrypt 升级 |
| `tests/integration/test_submit.py` | 集成 | submit 端点鉴权 + 提交 + 统计 |
| `tests/integration/test_vote_data.py` | 集成 | character/music/cp/questionnaire CRUD + 汇总 |
| `tests/integration/test_autocomplete.py` | 集成 | AutocompleteDAO ILIKE 查询 |
| `tests/integration/test_result_compute.py` | 集成 | ComputeService + ResultDAO 端到端 |
| `tests/contract/test_router_endpoints.py` | 契约 | 所有路由端点可达性 |
| `tests/contract/test_voter_fe_contract.py` | 契约 | VoterFE 响应格式契约 |
| `tests/contract/test_result_endpoints.py` | 契约 | result 9 端点 503 行为 + admin 端点可达性 |

### 测试空白（剩余）

| 模块 | 缺失内容 | 优先级 |
|---|---|---|
| user | partial unique index PG 行为验证 | 🟢 [B-022] |
| scraper | 无测试（外部 HTTP 依赖，需 mock）| 🟢 |
| 覆盖率门禁 | `fail_under=80` 未开启 | 🟡 [B-010] |

---

## 十一、核心遗留问题速查

> 详细描述见 [`docs/BACKLOG.md`](docs/BACKLOG.md)。下表仅列出影响功能完整性的高优项。

| 编号 | 问题 | 严重度 |
|---|---|---|
| ~~B-003~~ | ~~submit 端点未做 `vote_token` JWT 校验~~ | ✅ 2026-05-13 |
| ~~B-004~~ | ~~CORS `allow_origins=["*"]` 危险组合~~ | ✅ 2026-05-15 |
| ~~B-007~~ | ~~THBWiki / QQ SSO 接入~~（PatchyVideo SSO 未含）| ✅ 2026-05-17 |
| ~~B-009~~ | ~~trusted proxies / `X-Forwarded-For` 处理~~ | ✅ 2026-05-15 |
| ~~B-012~~ | ~~`update-password` 专用限流~~ | ✅ 2026-05-15 |
| **B-028** | **prod 部署通道缺失**（main push 也只到 test 环境）| **高（当前最高优先级）** |
| B-008 | MongoDB → PostgreSQL 历史数据回填脚本（设计稿已写，实现未做）| 中 |
| B-011 | 移除 `at_least_one_identifier` 约束（阻塞已解除）| 低 |
| B-019 | 错误体 `{"detail":"..."}` 与 Rust `{"error":"..."}` 格式不一致 | 低 |
| B-020 | mypy CI 硬门禁 | 低 |

---

## 十二、建议实施顺序（2026-05-30 重排）

### 优先级最高

```
1. B-028  prod 部署通道（确认现状或补 deploy-prod.yml）—— 上线硬阻塞
2. B-008  MongoDB → PG 历史数据回填脚本实现（设计稿已就绪，scripts/ 仍空）
```

### 立即可开工（独立、阻塞已解除）

```
3. autocomplete search_cps() 实现（角色/音乐已完成，唯一功能缺口）
4. B-011  移除 at_least_one_identifier 约束（需新 migration，1 小时）
5. B-026  DB 治理纪律 CI 门禁（alembic check + PR 模板）
6. B-020+B-021  mypy 清告警 + Pydantic V2 迁移（半天-1 天）
7. B-022/023  PG 契约测试 + importorskip 改硬 import
8. B-031  Nacos 配置约束标准 JSON 后删 _parse_config_content 容错分支
```

### 待条件成熟 / 低优先级

```
- B-010  覆盖率门禁 fail_under=80（模块稳定 1-2 sprint 后）
- B-013  发送幂等性
- B-019  错误响应格式与 Rust 统一（等前端反馈）
- B-024  UserDAO.save() 加 session.merge()
- scraper 18 站点测试补全（需 mock 外部 HTTP）
- GET /server-time 端点移植（低优先级）
```

### 已解除的依赖链（记录用）

```
B-007 SSO 落地 ✅ → B-011 移除 at_least_one_identifier 约束（现可做）
B-025 移除 init_db 后门 ✅ → B-026 DB 治理纪律 CI 门禁（现可做）
result DAO ✅ → GraphQL ResultQuery ✅ / Autocomplete 角色+音乐 ✅（CP 待做）
```
