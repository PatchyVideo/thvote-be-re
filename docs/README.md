# `docs/` 索引

> 创建日期：2026-04-27
> 最后更新：2026-08-31（**文档大扫除**：30 份已实施/已废弃的过程产物迁入 [`archive/`](./archive/)；补齐 07–08 月此前从未进索引的约 25 份文档；现役设计稿统一补状态头；CHANGELOG 去重排序并切分归档）

本表只列**现役文档**的入口与职责。历史过程记录在 [`archive/`](./archive/)，那里的内容**不代表当前实现**。

**每份文档头部都有状态与日期元信息**——设计稿带 `状态：已实施 / 部分实施 / 待实施`，读之前先看一眼。

---

## 🎯 从这里开始

| 我想…… | 去读 |
|---|---|
| **知道下一步做什么** | [`BACKLOG.md`](./BACKLOG.md) —— 单一仪表盘，所有 follow-up（B-001..B-063）收拢于此，按「🟢 可立即并行做 / ⏸ 等外部」分组 |
| **知道最近发生了什么** | [`CHANGELOG.md`](./CHANGELOG.md) —— 2026-07 起；更早见 [`CHANGELOG-archive-2026H1.md`](./CHANGELOG-archive-2026H1.md) |
| **了解投票业务本身要什么** | [`requirements/`](./requirements/) —— VoileLabs 官方需求文档，**权威口径来源** |
| **对接后端接口** | [`api/voteable-api-contract.md`](./api/voteable-api-contract.md) |

---

## 仓库级

| 文档 | 用途 |
|---|---|
| [`BACKLOG.md`](./BACKLOG.md) | 🎯 后续开发单一仪表盘。**这是仪表盘不是真理来源**——每项的上下文在源文档里，本表给一行摘要 + 跳转 |
| [`BACKLOG-archive.md`](./BACKLOG-archive.md) | 已完成 / 已废弃的 BACKLOG 条目，行文保留迁出时原样 |
| [`CHANGELOG.md`](./CHANGELOG.md) | 变更记录（按 CLAUDE.md §4），2026-07-01 起 |
| [`CHANGELOG-archive-2026H1.md`](./CHANGELOG-archive-2026H1.md) | 2026 上半年变更记录归档（至 2026-06-30） |

## 需求（`requirements/`）

> 官方需求文档，非我方产出。涉及口径分歧时**以此为准**。md 为转换版本，同目录附 docx 原件。

| 文档 | 用途 |
|---|---|
| [`requirements/…-投票系统.md`](./requirements/VoileLabs-人气投票项目-需求文档-投票系统.md) | 投票系统需求：投票规则、问卷、提名、账号 |
| [`requirements/…-投票结果页面.md`](./requirements/VoileLabs-人气投票项目-需求文档-投票结果页面.md) | 结果页需求：榜单口径、名次规则、各类图表与高级搜索组件 |

## 接口契约（`api/`）

| 文档 | 用途 |
|---|---|
| [`api/voteable-api-contract.md`](./api/voteable-api-contract.md) | 前端开发用 API 契约（Base URL `/api/v1`）：voteable / work 相关端点的请求响应模型 |

## 架构（`architecture/`）

| 文档 | 用途 |
|---|---|
| [`architecture/database-schema-management.md`](./architecture/database-schema-management.md) | DB schema 管理现状与 4 阶段演进路线图（Alembic + init_db 共存的折中策略与目标态） |
| [`architecture/nacos-hot-reload-limits.md`](./architecture/nacos-hot-reload-limits.md) | Nacos 热更新限制：`lru_cache` 缓存的客户端无法免重启热更新，及配套操作规程 |

## 模块迁移与对账（`migration/`）

| 文档 | 用途 |
|---|---|
| [`migration/user-manager.md`](./migration/user-manager.md) | Rust → Python 用户与认证模块迁移文档（基础对照 + 阶段进度跟踪） |
| [`migration/legacy-rest-compat.md`](./migration/legacy-rest-compat.md) | Legacy REST 兼容层：前端与仍在线的 Rust 部署共享同一份产物，nginx 把 `/v11-be/` 代理到后端**根路径**——这层扁平契约为什么必须存在 |
| [`migration/graphql-submit-bridge.md`](./migration/graphql-submit-bridge.md) | GraphQL Submit 桥接的背景、契约勘探与遗留风险（实现依据见对应设计稿） |
| [`migration/api-contract-audit-2026-07-14.md`](./migration/api-contract-audit-2026-07-14.md) | 前后端 API 契约**全量对账**：无漂移清单、result 包全量漂移、旧 GraphQL 死字段、待拍板决策 |
| [`migration/result-stats-audit-2026-08-14.md`](./migration/result-stats-audit-2026-08-14.md) | 结果统计层**三方审计**（前端需求 × Python 后端 × legacy Rust 交叉核实）：接口覆盖面基本迁全，缺口是几处内部深度实现 + 高级搜索 DSL |

## 运维 / 操作（`operations/`）

| 文档 | 用途 |
|---|---|
| [`operations/nacos-config-center.md`](./operations/nacos-config-center.md) | Nacos 配置中心 + 服务注册接入说明（2026-05-12 替换原 Apollo；含双控制台访问、§八 事故记录） |
| [`operations/cicd-pipeline.md`](./operations/cicd-pipeline.md) | CI/CD 流水线：当前唯一的 `deploy-test.yml` 拓扑、Nacos 配置交付路径、触发约定 |
| [`operations/deploy-server-setup.md`](./operations/deploy-server-setup.md) | 部署机环境：仓库外维护的 `docker-compose.yml` 生命周期、Redis/Nacos 管理方式 |
| [`operations/aliyun-onboarding.md`](./operations/aliyun-onboarding.md) | 阿里云 PNVS + DirectMail 从零到上线接入手册（账号/RAM/域名验证/SMTP/smoke + 常见坑） |
| [`operations/captcha-onboarding.md`](./operations/captcha-onboarding.md) | 验证码 2.0 人机验证接入手册（B-043：开通/建场景/RAM AK/Nacos 六键/smoke + **个人→公家账户切换清单**） |
| [`operations/login-config-checklist.md`](./operations/login-config-checklist.md) | 🎯 登录模块所需 Nacos 配置项**待填清单**（按登录方式分组 + JSON 骨架 + 访问入口） |
| [`operations/mock-vote-data.md`](./operations/mock-vote-data.md) | Mock 投票数据生成器手册（`scripts/generate_mock_votes.py`：一条命令灌几千合成投票供 result 联调，`mock-` 前缀可随时清理，**仅测试环境**） |

## 数据样本（`scraper/`）

| 文档 | 用途 |
|---|---|
| [`scraper/candidate-extraction/samples/README.md`](./scraper/candidate-extraction/samples/README.md) | THBWiki 角色数据源样本（原始 wikitext + 解析后 CSV），配合候选抽取设计稿使用 |

---

## 设计稿（`superpowers/specs/`）

> 记录**当时的设计意图与取舍**——「为什么这么做」的长期参考。每份头部有 `状态` 行标明落地情况。
> 已废弃、纯操作性、或属事后记录的设计稿已迁入 [`archive/superpowers/specs/`](./archive/superpowers/specs/)。

### 用户与认证

| 文档 | 主题 |
|---|---|
| [`2026-04-27-user-auth-design.md`](./superpowers/specs/2026-04-27-user-auth-design.md) | 用户表与认证模块设计（路由、数据模型、流程、错误处理、测试策略；§九 是 follow-up F1–F9） |
| [`2026-04-27-user-auth-open-issues.md`](./superpowers/specs/2026-04-27-user-auth-open-issues.md) | 已知问题清单（U-1..U-19 + 祖传 L-1..L-3）。**review 认证模块 PR 前先看这份**——表内问题都在册，注意力放到表外 |
| [`2026-05-16-medium-priority-backlog-design.md`](./superpowers/specs/2026-05-16-medium-priority-backlog-design.md) | 中优先级 backlog 批量设计；**B-008（Mongo→PG 用户回填脚本）的源文档，该项仍开放** |

### 提交与 GraphQL 契约

| 文档 | 主题 |
|---|---|
| [`2026-05-13-submit-completion-design.md`](./superpowers/specs/2026-05-13-submit-completion-design.md) | Submit 模块补完（vote_token 鉴权、paper 校验） |
| [`2026-05-20-graphql-schema-alignment-design.md`](./superpowers/specs/2026-05-20-graphql-schema-alignment-design.md) | GraphQL schema 与前端对齐（标量注册、字段重命名、强类型响应） |
| [`2026-05-30-graphql-login-bridge-design.md`](./superpowers/specs/2026-05-30-graphql-login-bridge-design.md) | 登录 mutation 桥接：业务逻辑不动，只加 GraphQL 桥 |
| [`2026-06-07-graphql-submit-bridge-design.md`](./superpowers/specs/2026-06-07-graphql-submit-bridge-design.md) | 投票提交/回读适配前端契约（5 mutation + 5 回读 query） |
| [`2026-07-19-result-graphql-compat-design.md`](./superpowers/specs/2026-07-19-result-graphql-compat-design.md) | Result 前端契约层：12 个 `query*` + 问卷语义 code + 分段统计（B-052） |

### 计票与结果（B-050 系列）

| 文档 | 主题 |
|---|---|
| [`2026-07-18-result-recount-id-based-design.md`](./superpowers/specs/2026-07-18-result-recount-id-based-design.md) | **计票/结果模块重写**：纯 id 贯穿、candidate 白名单制、CP 无序 key + active 分离、离线批量算。含 candidate 两段身世与旧 name-based 流程脆弱性分析 |
| [`2026-07-23-tally-db-truth-source-design.md`](./superpowers/specs/2026-07-23-tally-db-truth-source-design.md) | 计票真相源迁 DB：白名单从前端快照 JSON 迁到 `voteable`/`candidate`，双键（8-hex 旧 id / candidateId）聚合 |
| [`2026-08-14-advanced-search-dsl-design.md`](./superpowers/specs/2026-08-14-advanced-search-dsl-design.md) | 高级搜索/筛选 DSL：**关键认知——DSL 不是"过滤已算好的榜"而是"换一个投票子集重算榜"**；lark 解析 + 子集重算复用 compute 纯函数 |
| [`2026-08-29-questionnaire-trend-append-only-design.md`](./superpowers/specs/2026-08-29-questionnaire-trend-append-only-design.md) | 问卷趋势 + append-only 提交历史：改票产生负桶的真实净增量序列 |

### 候选项 / 投票对象 / 作品

| 文档 | 主题 |
|---|---|
| [`2026-06-08-candidate-management-design.md`](./superpowers/specs/2026-06-08-candidate-management-design.md) | 候选项管理增强（B-036）：CSV/JSON 导入 dry-run 预览 + 单条编辑 |
| [`2026-07-20-voteable-cross-year-stable-id-design.md`](./superpowers/specs/2026-07-20-voteable-cross-year-stable-id-design.md) | voteable 跨年稳定 id：候选项脱离年份、跨届可比 |
| [`2026-07-21-work-table-unified-design.md`](./superpowers/specs/2026-07-21-work-table-unified-design.md) | work 表统一：作品归属与类型收敛（收尾清单见 BACKLOG **B-057**） |
| [`2026-07-20-thbwiki-candidate-extraction-design.md`](./superpowers/specs/2026-07-20-thbwiki-candidate-extraction-design.md) | 从 THBWiki 抽取候选角色数据，取代每年手工核对清单 |
| [`2026-06-09-mongodump-import-design.md`](./superpowers/specs/2026-06-09-mongodump-import-design.md) | 离线 BSON dump 导入（`scripts/import_mongo_dump.py`，复用 sync mappers） |
| [`2026-06-07-mongodb-sync-design.md`](./superpowers/specs/2026-06-07-mongodb-sync-design.md) | MongoDB 全量历史数据同步（4 类数据 A/B/C/D、断点重试、CLI + API 双入口） |

### 安全与反刷票

| 文档 | 主题 |
|---|---|
| [`2026-07-16-captcha-anti-abuse-design.md`](./superpowers/specs/2026-07-16-captcha-anti-abuse-design.md) | 注册防刷人机验证（B-043，阿里云验证码 2.0：闸发码、双入口收口、fail-closed、成本/排期） |
| [`2026-07-17-anti-vote-farming-design.md`](./superpowers/specs/2026-07-17-anti-vote-farming-design.md) | 反刷票证据采集（B-044，设备 UUID + 可信 IP，**只取证不拦截**） |
| [`2026-07-17-submit-timing-signal-design.md`](./superpowers/specs/2026-07-17-submit-timing-signal-design.md) | 提交耗时 + 服务端改票计数（B-045/B-046，`fill_duration_ms` + `attempt`；改票假阳性由 attempt 兜底） |
| [`2026-07-17-block-scripts-design.md`](./superpowers/specs/2026-07-17-block-scripts-design.md) | 拦脚本（B-048，Origin/Referer 校验；只拦变更、query 放行；**默认关灰度**） |
| [`2026-06-08-security-backend-design.md`](./superpowers/specs/2026-06-08-security-backend-design.md) | 安全块后端（B-037）：二创提名校验 + 人工审核队列 + 提名时间窗 + 投票问卷门禁 |
| [`2026-08-14-test-login-bypass-design.md`](./superpowers/specs/2026-08-14-test-login-bypass-design.md) | ⚠️ 测试登录旁路（白名单固定验证码）。**临时测试设施，公开上线前必须整体移除**：`grep -r TEST_LOGIN_BYPASS` |

### 管理端

| 文档 | 主题 |
|---|---|
| [`2026-07-17-admin-console-vue-security-monitoring-design.md`](./superpowers/specs/2026-07-17-admin-console-vue-security-monitoring-design.md) | 管理后台安全监控（B-049）：流量概览 / IP·设备聚类 / 可疑名单 / 账号钻取 + 处置；`X-Admin-Secret` 强制 + IP 白名单 |
| [`2026-07-18-admin-console-vue-frontend-design.md`](./superpowers/specs/2026-07-18-admin-console-vue-frontend-design.md) | 管理台前端 Vue3+Vite+TS 模块化重写（拆掉 1115 行单文件 admin_ui） |
| [`2026-06-08-questionnaire-admin-backend-design.md`](./superpowers/specs/2026-06-08-questionnaire-admin-backend-design.md) | 自由问卷管理后端（B-041）：全层级 CRUD + 自研嵌套编辑器；取代 B-039 的 admin/契约部分 |

### 问卷与投票对象（Block 3）

| 文档 | 主题 |
|---|---|
| [`2026-06-08-questionnaire-backend-design.md`](./superpowers/specs/2026-06-08-questionnaire-backend-design.md) | 问卷结构化后端（B-039）：4 结构表 + admin 整树导入 + structure 查询 + 完成校验升级 |
| [`2026-06-08-vote-objects-backend-design.md`](./superpowers/specs/2026-06-08-vote-objects-backend-design.md) | 投票对象迁后端（B-040）：`merged_into` 去重合并 + 分类查询端点 |

### 前端侧设计（`thvote-fe` / `Touhou-Vote` 仓库）

> 这四块的**后端已于 2026-07-14 合入 main，前端侧全部待做**（2026-08-13 确认由我方负责）。

| 文档 | 对应 |
|---|---|
| [`2026-06-08-security-frontend-design.md`](./superpowers/specs/2026-06-08-security-frontend-design.md) | B-037 安全 |
| [`2026-06-08-questionnaire-frontend-design.md`](./superpowers/specs/2026-06-08-questionnaire-frontend-design.md) | B-039 问卷结构化 |
| [`2026-06-08-vote-objects-frontend-design.md`](./superpowers/specs/2026-06-08-vote-objects-frontend-design.md) | B-040 投票对象 |
| [`2026-06-08-questionnaire-admin-frontend-design.md`](./superpowers/specs/2026-06-08-questionnaire-admin-frontend-design.md) | B-041 自由问卷管理 |

### 已被后续设计取代（仍保留供追溯）

| 文档 | 被谁取代 |
|---|---|
| [`2026-05-13-autocomplete-design.md`](./superpowers/specs/2026-05-13-autocomplete-design.md) | 无取代；CP 搜索缺口见 BACKLOG **B-062** |
| [`2026-05-13-result-query-design.md`](./superpowers/specs/2026-05-13-result-query-design.md) | 计票部分已由 [`2026-07-18-result-recount-id-based-design.md`](./superpowers/specs/2026-07-18-result-recount-id-based-design.md) 重写取代 |
| [`2026-06-07-admin-panel-design.md`](./superpowers/specs/2026-06-07-admin-panel-design.md) | 单文件 Web UI 已由 [`2026-07-18-admin-console-vue-frontend-design.md`](./superpowers/specs/2026-07-18-admin-console-vue-frontend-design.md) 取代 |

---

## 实施计划（`superpowers/plans/`）

> **只剩未实施完的 6 份**。已执行完毕的 25 份在 [`archive/superpowers/plans/`](./archive/superpowers/plans/)。
> ⚠️ plans 里的 `- [ ]` checkbox **从未被维护过**（BACKLOG **B-057⑤**），不要拿它判断完成度。

| 文档 | 状态 |
|---|---|
| [`2026-05-16-mongodb-migration.md`](./superpowers/plans/2026-05-16-mongodb-migration.md) | **待实施**（B-008）：目标脚本 `scripts/migrate_users_from_mongodb.py` 尚不存在 |
| [`2026-06-08-security-frontend.md`](./superpowers/plans/2026-06-08-security-frontend.md) | 待实施（B-037 前端） |
| [`2026-06-08-questionnaire-frontend.md`](./superpowers/plans/2026-06-08-questionnaire-frontend.md) | 待实施（B-039 前端） |
| [`2026-06-08-vote-objects-frontend.md`](./superpowers/plans/2026-06-08-vote-objects-frontend.md) | 待实施（B-040 前端） |
| [`2026-06-08-questionnaire-admin-frontend.md`](./superpowers/plans/2026-06-08-questionnaire-admin-frontend.md) | 待实施（B-041 投票前端） |
| [`2026-07-21-work-table-unified.md`](./superpowers/plans/2026-07-21-work-table-unified.md) | **部分实施**：后端主体已合入 main，收尾清单见 BACKLOG **B-057** |

---

## 归档（`archive/`）

历史过程记录，**不代表当前实现**。索引见 [`archive/README.md`](./archive/README.md)。

| 子目录 | 内容 |
|---|---|
| [`archive/superpowers/plans/`](./archive/superpowers/plans/) | 25 份已执行完 / 已废弃的实施计划 |
| [`archive/superpowers/specs/`](./archive/superpowers/specs/) | 4 份已废弃 / 纯操作性 / 事后记录类设计稿 |
| [`archive/superpowers/handoffs/`](./archive/superpowers/handoffs/) | 1 份一次性任务交接记录 |
| [`archive/2026-05-30-refactor-todo.md`](./archive/2026-05-30-refactor-todo.md) | 模块级迁移进度快照（内容已过期；仍成立的缺口已转 B-062 / B-063） |

---

## 阅读建议

**第一次进项目**
1. [`requirements/`](./requirements/) 了解投票业务本身要什么
2. [`BACKLOG.md`](./BACKLOG.md) 看当前战场
3. 挑一项，顺着它的「源文档」列跳到对应设计稿

**接手用户与认证模块**
1. [`2026-04-27-user-auth-design.md`](./superpowers/specs/2026-04-27-user-auth-design.md) §一 §二 理解范围
2. [`migration/user-manager.md`](./migration/user-manager.md) 看与 Rust 的对照
3. [`2026-04-27-user-auth-open-issues.md`](./superpowers/specs/2026-04-27-user-auth-open-issues.md) 看已知问题

**接手计票 / 结果模块**
1. [`2026-07-18-result-recount-id-based-design.md`](./superpowers/specs/2026-07-18-result-recount-id-based-design.md) —— 现行计票口径的根文档
2. [`migration/result-stats-audit-2026-08-14.md`](./migration/result-stats-audit-2026-08-14.md) —— 与前端需求、legacy Rust 的三方缺口对账
3. BACKLOG 的 **B-050-后补N** 系列看还有什么没做

**准备上线 / 配置阿里云** → [`operations/aliyun-onboarding.md`](./operations/aliyun-onboarding.md)、[`operations/captcha-onboarding.md`](./operations/captcha-onboarding.md) 按章节顺序操作

**改 CI/CD 或排障部署** → [`operations/cicd-pipeline.md`](./operations/cicd-pipeline.md) §七触发约定；配置问题看 [`operations/nacos-config-center.md`](./operations/nacos-config-center.md)

**做 Schema 变更** → [`architecture/database-schema-management.md`](./architecture/database-schema-management.md)，按当前所处阶段决定是否需要 Alembic migration

---

## 维护规则

- **新增文档**头部必须有 `创建日期 / 最后更新`；设计稿另加 `状态` 行
- **修改文档**至少把 `最后更新` 改成当天，理想情况附一行修订说明
- **新增 / 移动 / 归档文档**同步更新本索引——索引失修是这次大扫除要解决的主要问题，别让它复发
- 跨文档引用优先**相对路径** + 锚点（§N）
- 临时草稿不进 `docs/`；草稿状态命名 `YYYY-MM-DD-DRAFT-*.md`
- **文档过期时归档而非删除**，并在头部标注「不代表当前实现」+ 现状去向；规则见 [`archive/README.md`](./archive/README.md)
