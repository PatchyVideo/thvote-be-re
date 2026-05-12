# REFACTOR_TODO.md — 重构进度总览

> 创建日期：2026-05-12
> 最后更新：2026-05-12
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
| 投票提交（原始）| `submit-handler` | `apps/submit` | ✅ | 11 端点，B-002 已修 |
| 投票数据（处理后）| `vote-data`（Rust 存根）| `apps/vote_data` | ✅ | Python 新增，非 Rust 移植 |
| 查询结果 | `result-query` | `apps/result` | ❌ | DAO 全部 `NotImplementedError` |
| 自动补全 | `autocomplete`（Rust 存根）| `apps/autocomplete` | ❌ | DAO 返回空列表 |
| 爬虫 | `scraper`（Python）| `apps/scraper` | ⚠️ | 3/18+ 站点已移植 |
| GraphQL | `gateway` | `api/graphql` | ⚠️ | 仅 submit，result-query 未做 |
| 数据库迁移 | — | `alembic/versions/` | ✅ | 0001+0002 已覆盖所有表 |
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
- 🔴 [B-003] submit 端点未使用真实 `vote_token` 校验（鉴权空洞）
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

## 五、查询结果 ❌ 主要欠账

**对应 Rust：** `result-query/src/`（handlers.rs / query.rs / parser.rs / query.pest）

**现状：** 路由和服务层骨架存在，DAO 层所有方法均为 `raise NotImplementedError`。

**数据来源：** `character / music / cp / questionnaire` 表（VoteData 服务写入的处理后数据，JSON 列 `*_list`）。

### 待实现端点

| 端点 | DAO 方法 | Rust 对应 | 状态 |
|---|---|---|---|
| `POST /result/ranking/` | `get_ranking(query: RankingQuery)` | `/v1/chars-rank/` `/v1/musics-rank/` `/v1/cps-rank/` | ❌ |
| `POST /result/reasons/` | `get_reasons(query: ReasonQuery)` | `/v1/chars-reasons/` `/v1/musics-reasons/` `/v1/cps-reasons/` | ❌ |
| `POST /result/trends/` | `get_trends(query: TrendQuery)` | `/v1/chars-trend/` `/v1/musics-trend/` `/v1/cps-trend/` | ❌ |
| `POST /result/global-stats/` | `get_global_stats(query)` | `/v1/global-stats/` | ❌ |
| `POST /result/completion-rates/` | `get_completion_rates(query)` | `/v1/completion-rates/` | ❌ |
| `POST /result/questionnaire/` | `get_questionnaire(query)` | `/v1/papers/` | ❌ |
| `POST /result/questionnaire-trend/` | `get_questionnaire_trend(query)` | `/v1/papers-trend/` | ❌ |
| `POST /result/covote/` | `get_covote(query: CovoteQuery)` | `/v1/chars-covote/` `/v1/musics-covote/` | ❌ |
| `POST /result/single/` | `get_single_entity(query: SingleQuery)` | `/v1/chars-single/` `/v1/musics-single/` `/v1/cps-single/` | ❌ |

### 实现要点

1. **排名（ranking）**：解析 `character.character_list` JSON，按名称聚合票数，计算排名/本命比/性别分布。复杂度最高。
2. **趋势（trends）**：按 `submit_datetime` 分段统计票数变化，需要时间窗口参数。
3. **共投（covote）**：查两个实体同时被选的用户数，需要 JSONB 包含查询（PostgreSQL）。
4. **全局统计（global-stats）**：聚合各表行数，部分字段与 `SubmitDAO.get_statistics()` 重叠，注意复用。
5. **Rust query.pest 语法**：旧版有自定义查询 DSL，Python 侧不必复用；用 SQLAlchemy ORM 直接实现等价逻辑即可。
6. **注意 `get_all_*_submissions()`**：`VoteDataDAO` 已提供批量读接口，可作为 result 查询的数据入口。

### 建议实现顺序

```
global-stats → ranking → reasons → completion-rates → trends → single → covote → questionnaire → questionnaire-trend
```

（从最简单的聚合到最复杂的时序/共投查询）

### 缺少的测试

- result 模块目前无任何测试（单元/集成/契约均无）

---

## 六、自动补全 ❌

**对应 Rust：** `autocomplete/`（Rust 原版是空存根 `println!("Hello")`，Python 侧为新实现）

**现状：** 路由 + 服务骨架存在，DAO 三个方法全部返回空列表 `[]`。

| 端点 | 状态 |
|---|---|
| `POST /autocomplete/search` | ❌（调用链通，返回空结果） |

### 待实现

- `AutocompleteDAO.search_characters(query, limit)` — 在 `character` 表的 `character_list` JSON 内搜索角色名（模糊匹配），或从独立词表/候选表查询。
- `AutocompleteDAO.search_music(query, limit)` — 同上，针对音乐。
- `AutocompleteDAO.search_cps(query, limit)` — 同上，针对 CP。

> **数据来源待定：** 现有 schema 中无独立的候选项目表（候选角色名列表）。需要确认：(a) 从 `character/music/cp` 已投数据中提取？还是 (b) 需要新建 `candidate_*` 参考数据表并导入数据？

---

## 七、爬虫 ⚠️

**对应：** 旧 `scraper/`（Python 实现，非 Rust 移植）

**端点：** `POST /scraper/scrape` ✅（Redis 缓存 + UDID 支持）

**站点移植状态（旧版有 18 个站点）：**

| 站点 | 旧版 | 当前 |
|---|---|---|
| `bilibili.py` | ✅ | ✅ |
| `pixiv.py` | ✅ | ✅ |
| `twitter.py` | ✅ | ✅ |
| `nicovideo.py` | ✅ | ❌ |
| `nicoseiga.py` | ✅ | ❌ |
| `youtube.py` | ✅ | ❌ |
| `weibo.py` | ✅ | ❌ |
| `tieba.py` | ✅ | ❌ |
| `steam.py` | ✅ | ❌ |
| `dlsite.py` | ✅ | ❌ |
| `melon.py` | ✅ | ❌ |
| `dizzylab.py` | ✅ | ❌ |
| `acarticle.py` | ✅ | ❌ |
| `acfun.py` | ✅ | ❌ |
| `biliarticle.py` | ✅ | ❌ |
| `patchyvideo.py` | ✅ | ❌ |
| `pixnovel.py` | ✅ | ❌ |
| `thbwiki.py` | ✅ | ❌ |

**旧版工具类移植状态：**

| 工具模块 | 旧版 | 当前 |
|---|---|---|
| `biliutils.py` | ✅ | ✅ |
| `cache.py` | ✅ | ✅ |
| `network.py` | ✅ | ✅ |
| `match.py` | ✅ | ❌ |
| `parse.py` | ✅ | ❌ |

> **优先级：** 爬虫缺失不阻塞核心投票流程，可按需补充。B 站/Pixiv/Twitter 已覆盖主要使用场景。NicoVideo / YouTube / THBWiki 可根据本届投票内容决定是否需要。

---

## 八、GraphQL API ⚠️

**对应 Rust：** `gateway/src/`（schema.rs + submit_handler.rs + result_query.rs）

**现状：**
- `POST /graphql` — Strawberry schema 已挂载 ✅
- `SubmitQuery / SubmitMutation` — 查询/提交投票 ✅
- `ResultQuery` — 旧 gateway 的 `result_query.rs` 部分，**未实现** ❌
- `user-token-status` 端点 — 旧 gateway 有独立 `POST /user-token-status`，Python 侧合并进 `POST /user/token-status` ✅
- `GET /server-time` — 旧 gateway 有，Python 侧**未实现** ❌

**GraphQL result-query：** 依赖第五节 result DAO 完成后再做。

---

## 九、数据库迁移 ✅

| 版本 | 内容 | 状态 |
|---|---|---|
| `0001_initial_user_and_activity_log` | `user` + `activity_log` 表 + 索引 | ✅ |
| `0002_voting_tables` | `raw_character/music/cp/paper/dojin` + `character/music/cp/questionnaire` 遗留表 | ✅ |

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
| `tests/unit/test_voter_fe_serialization.py` | 单元 | VoterFE schema 序列化 |
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
| submit | 无任何测试 | 🟡 |
| vote_data | 无任何测试 | 🟡 |
| result | 无任何测试（模块本身未实现）| ❌ |
| autocomplete | 无任何测试（模块本身未实现）| ❌ |
| scraper | 无任何测试 | 🟢 |
| 覆盖率门禁 | `fail_under=80` 未开启 | 🟡 [B-010] |

---

## 十一、核心遗留问题速查

> 详细描述见 [`docs/BACKLOG.md`](docs/BACKLOG.md)。下表仅列出影响功能完整性的高优项。

| 编号 | 问题 | 严重度 |
|---|---|---|
| B-003 | submit 端点未做 `vote_token` JWT 校验（鉴权空洞）| 🔴 高 |
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
2. B-020+B-027  mypy 清告警 + CI lint 合并（半天）
3. B-021  Pydantic V2 迁移（半天）
4. B-008  数据回填脚本设计（独立 scripts/ 目录）
5. 爬虫站点补充（nicovideo / youtube / thbwiki，按本届需求排序）
```

### 下一个主要 PR

```
结果查询模块（第五节）— 工作量最大的单一剩余模块
  └── 建议先写 spec 文档 → 再按 global-stats → ranking → ... 顺序 TDD 实现
```

### 依赖链

```
B-007 SSO 落地
  └── B-011 移除 at_least_one_identifier 约束

B-025 移除 init_db 后门
  └── B-026 DB 治理纪律 CI 门禁

Result DAO 实现
  └── GraphQL ResultQuery 实现
  └── Autocomplete（如用已投数据作候选源）
```
