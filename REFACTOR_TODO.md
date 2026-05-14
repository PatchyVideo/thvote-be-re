# REFACTOR_TODO.md — 重构进度总览

> 创建日期：2026-05-12
> 最后更新：2026-05-13
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
| 用户与认证 | `user-manager` | `apps/user` | ✅ | 12 端点完整，有测试 |
| 投票提交（原始）| `submit-handler` | `apps/submit` | ✅ | 11 端点 + vote_token 鉴权 + 测试（2026-05-13）|
| 投票数据（处理后）| `vote-data`（Rust 存根）| `apps/vote_data` | ✅ | Python 新增，非 Rust 移植 |
| 查询结果 | `result-query` | `apps/result` | ✅ | 9 端点 + ComputeService + Redis 缓存（2026-05-13）|
| 自动补全 | `autocomplete`（Rust 存根）| `apps/autocomplete` | ✅ | candidate 表 ILIKE 查询，4 单元+8 集成测试（2026-05-13）|
| 爬虫 | `scraper`（Python）| `apps/scraper` | ✅ | 16/18 站点（全部旧后端站点已移植，2026-05-14）|
| GraphQL | `gateway` | `api/graphql` | ✅ | submit + ResultQuery 8 个字段，JSON scalar（2026-05-13）|
| 数据库迁移 | — | `alembic/versions/` | ✅ | 0001+0002+0003 已覆盖所有表 |
| 基础设施公共层 | — | `common/` | ✅ | config/db/redis/jwt/rate_limit 已就绪 |

---

## 一、基础设施 / 公共层 ✅

**对应 Rust：** 各服务的 `common.rs / context.rs`，Python 侧全部统一在 `src/common/`。

| 组件 | 文件 | 状态 |
|---|---|---|
| 配置（Nacos + Apollo + env）| `common/config.py` | ✅ |
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
| CORS（⚠️ 当前 `allow_origins=["*"]`）| `src/main.py` | 🟢 [B-004] |
| 热更新（`/admin/reload-config`）| `src/main.py` | ✅ |
| 服务器时间端点（`GET /server-time`）| — | ❌ 旧 gateway 有，未移植 |
| mypy CI 硬门禁 | `mypy.ini` / CI | 🟢 [B-020] |
| Pydantic V2 迁移 | 全 `common/` | 🟢 [B-021] |

**BACKLOG 关联：** B-004, B-009（trusted proxies）, B-017（Apollo+lru_cache）, B-020, B-021, B-025（移除 init_db 后门）, B-026, B-027

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

**未移植（超出当前范围）：**
- Rust 的 `thbwiki_login.rs / qq_binding.rs / legacy_login.rs` → [B-007] SSO 接入，计划中

**BACKLOG 关联（高优先级）：**
- ✅ [B-003] submit 端点 vote_token JWT 校验（2026-05-13 完成）
- 🟡 [B-012] `update-password` 单独限流（5 req/300s）
- 🟡 [B-014] `vote_token` 签发集成测试（3 场景）
- 🟡 [B-015] `GET /me` 集成测试
- 🟡 [B-016] bcrypt → argon2 升级端到端测试
- 🟡 [B-018] `_safe_log` 失败无可见性
- 🟡 [B-024] `UserDAO.save()` 加 `session.merge()` 防 detached instance

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
- 🔴 [B-003] submit 端点当前只靠 `meta.vote_id` 加分布锁，未做 `vote_token` JWT 校验

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

## 六、自动补全 ❌

**对应 Rust：** `autocomplete/`（Rust 原版是空存根，Python 侧为新实现）

**现状：** 路由 + 服务骨架存在，DAO 三个方法全部返回空列表 `[]`。

| 端点 | 状态 |
|---|---|
| `POST /autocomplete/search` | ❌（调用链通，返回空结果） |

### 待实现

现在 `candidate_character` / `candidate_music` 表已存在（migration 0003），可直接用作数据源：

- `AutocompleteDAO.search_characters(query, limit)` — 在 `candidate_character.name` / `name_jp` 做模糊匹配（`ILIKE %query%`）
- `AutocompleteDAO.search_music(query, limit)` — 同上，查 `candidate_music`
- `AutocompleteDAO.search_cps(query, limit)` — 可从已提交的 `cp.cp_list` JSON 中提取唯一 CP 名称

---

## 七、爬虫 ⚠️

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

**BACKLOG 关联：**
- 🟡 [B-025] 移除 `init_db()` / `DEBUG` 后门
- 🟡 [B-026] DB 治理纪律（PR 模板 + `alembic check` CI 门禁）

> 如果 `autocomplete` 需要新建候选项目表，需要第三张 migration（见第六节"数据来源待定"）。

---

## 十、测试覆盖

### 已有测试

| 文件 | 类型 | 覆盖内容 |
|---|---|---|
| `tests/unit/test_jwt.py` | 单元 | JWT 签发/校验/过期/受众 |
| `tests/unit/test_email_code_service.py` | 单元 | 邮件验证码生成/Redis 守卫/过期 |
| `tests/unit/test_pnvs_client.py` | 单元 | PNVS 客户端调用 mock |
| `tests/unit/test_compute.py` | 单元 | 计算函数（ranking/gender/covote/global-stats/completion-rates）|
| `tests/integration/test_result_compute.py` | 集成 | ComputeService + ResultDAO 端到端 |
| `tests/contract/test_result_endpoints.py` | 契约 | result 9 端点 503 行为 + admin 端点可达性 |
| `tests/integration/test_login_flows.py` | 集成 | 邮件/手机/密码三种登录流 |
| `tests/integration/test_update_and_remove.py` | 集成 | update-email/phone/nickname/password/remove-voter |
| `tests/contract/test_router_endpoints.py` | 契约 | 所有路由端点可达性 |
| `tests/contract/test_voter_fe_contract.py` | 契约 | VoterFE 响应格式契约 |

### 测试空白（待补）

| 模块 | 缺失内容 | 优先级 |
|---|---|---|
| user | `vote_token` 签发 3 个场景（已验证/未验证 × 期内/期外）| 🔴 [B-014] |
| user | `GET /me` 集成 | 🟡 [B-015] |
| user | bcrypt → argon2 升级路径端到端 | 🟡 [B-016] |
| user | partial unique index PG 行为验证 | 🟢 [B-022] |
| submit | 19 单元 + 7 集成测试 ✅ | — |
| vote_data | 无任何测试 | 🟡 |
| result | 单元/集成/契约测试已完成 ✅ | — |
| autocomplete | 无任何测试（模块本身未实现）| ❌ |
| scraper | 无任何测试 | 🟢 |
| 覆盖率门禁 | `fail_under=80` 未开启 | 🟡 [B-010] |

---

## 十一、核心遗留问题速查

> 详细描述见 [`docs/BACKLOG.md`](docs/BACKLOG.md)。下表仅列出影响功能完整性的高优项。

| 编号 | 问题 | 严重度 |
|---|---|---|
| ~~B-003~~ | ~~submit 端点未做 `vote_token` JWT 校验~~ | ✅ 已完成 2026-05-13 |
| B-004 | CORS `allow_origins=["*"]` + `allow_credentials=True` 危险组合 | 中 |
| B-007 | THBWiki / QQ / PatchyVideo SSO 接入 | 中 |
| B-008 | MongoDB → PostgreSQL 历史数据回填脚本 | 中 |
| B-009 | trusted proxies / `X-Forwarded-For` 处理 | 中 |
| B-012 | `update-password` 专用限流 | 中 |
| B-019 | 错误体 `{"detail":"..."}` 与 Rust `{"error":"..."}` 格式不一致 | 低 |
| B-020 | mypy CI 硬门禁 | 低 |

---

## 十二、建议实施顺序

### 立即可开工（独立，不依赖其他 PR）

```
1. B-004  CORS 收紧（30 分钟）
2. B-009  trusted proxies / X-Forwarded-For（1 小时）
3. B-012  update-password 专用限流（1 小时）
4. B-020+B-027  mypy 清告警 + CI lint 改硬（半天）
5. B-021  Pydantic V2 迁移（半天）
6. B-014/015/016 测试补全（1-2 天）
7. vote_data 模块测试（半天）
8. B-008  数据回填脚本（独立 scripts/ 目录）
```
5. B-021  Pydantic V2 迁移（半天）
6. B-008  数据回填脚本设计（独立 scripts/ 目录）
7. 爬虫站点补充（nicovideo / youtube / thbwiki，按本届需求排序）
```

### 下一个主要 PR（可基于 result DAO 解锁）

```
GraphQL ResultQuery — result DAO 已就绪，可直接封装 Strawberry 类型
```

### 依赖链

```
B-007 SSO 落地
  └── B-011 移除 at_least_one_identifier 约束

B-025 移除 init_db 后门
  └── B-026 DB 治理纪律 CI 门禁

result DAO ✅（已完成）
  └── GraphQL ResultQuery ← 下一步
  └── Autocomplete ← 候选表已就绪，可立即做
```
