# `docs/` 索引

> 创建日期：2026-04-27
> 最后更新：2026-06-08（新增 candidate-management 及 Block 1-3 跨前后端 design+plan：B-037 安全 / B-038 作品投票 / B-039 问卷结构化 / B-040 投票对象迁后端）

按用途分类。每份文档头部都有 `创建日期 / 最后更新` 元信息；本表只列入口和职责。

---

## 仓库级

| 文档 | 用途 |
|---|---|
| [`BACKLOG.md`](./BACKLOG.md) | 🎯 **后续开发单一仪表盘**——所有 follow-up 收拢到这里（B-001..B-N）；按"可立即并行做 / 等 PR merge / 战略阻塞"分组。**找下一步该做什么从这里开始。** |
| [`CHANGELOG.md`](./CHANGELOG.md) | 仓库级变更记录（按 CLAUDE.md §4） |

## 架构（`architecture/`）

| 文档 | 用途 |
|---|---|
| [`architecture/database-schema-management.md`](./architecture/database-schema-management.md) | DB schema 管理现状与 4 阶段演进路线图（Alembic + init_db 共存的折中策略与目标态） |
| [`architecture/nacos-hot-reload-limits.md`](./architecture/nacos-hot-reload-limits.md) | Nacos 热更新限制：lru_cache 缓存客户端无法免重启热更新，操作规程 |

## 模块迁移（`migration/`）

| 文档 | 用途 |
|---|---|
| [`migration/user-manager.md`](./migration/user-manager.md) | Rust → Python 用户与认证模块迁移文档（基础对照 + 阶段进度跟踪） |

## 运维 / 操作（`operations/`）

| 文档 | 用途 |
|---|---|
| [`operations/aliyun-onboarding.md`](./operations/aliyun-onboarding.md) | 阿里云 PNVS + DirectMail 从零到上线接入手册（账号/RAM/认证方案/域名验证/SMTP/smoke 验证 + 常见坑） |
| [`operations/cicd-pipeline.md`](./operations/cicd-pipeline.md) | CI/CD 流水线说明：当前唯一的 `deploy-test.yml` 拓扑、Nacos 配置交付路径、触发约定、follow-up |
| [`operations/deploy-server-setup.md`](./operations/deploy-server-setup.md) | 部署机环境配置：docker-compose.yml 的生命周期、Redis/Nacos 管理方式 |
| [`operations/nacos-config-center.md`](./operations/nacos-config-center.md) | Nacos 配置中心 + 服务注册接入说明（2026-05-12 替换原 Apollo；含 R-NACOS 双控制台访问） |
| [`operations/login-config-checklist.md`](./operations/login-config-checklist.md) | 🎯 登录模块所需 Nacos 配置项**待填清单**（按登录方式分组 + JSON 骨架 + 访问入口）|

## 设计稿与实施记录（`superpowers/specs/`）

> 命名约定：`YYYY-MM-DD-<topic>-<kind>.md`，`<kind>` ∈ {`design`, `implementation-report`, `open-issues`}

| 文档 | 用途 |
|---|---|
| [`superpowers/specs/2026-04-27-user-auth-design.md`](./superpowers/specs/2026-04-27-user-auth-design.md) | 用户表与认证模块**设计稿**（路由、数据模型、流程、错误处理、测试策略；§九 是 follow-up F1-F9） |
| [`superpowers/specs/2026-04-27-user-auth-implementation-report.md`](./superpowers/specs/2026-04-27-user-auth-implementation-report.md) | 实施过程**事后记录**：交付清单、与设计稿的偏离、实施期发现的问题（F-impl-1..10） |
| [`superpowers/specs/2026-04-27-user-auth-open-issues.md`](./superpowers/specs/2026-04-27-user-auth-open-issues.md) | 用户与认证模块**已知问题清单**（U-1..U-19 + 祖传 L-1..L-3），按 PR 前已修 / PR 前待修 / PR 后再做 / 祖传 分组 |
| [`superpowers/specs/2026-06-07-mongodb-sync-design.md`](./superpowers/specs/2026-06-07-mongodb-sync-design.md) | MongoDB 全量历史数据同步**设计稿**（4 类数据 A/B/C/D、断点重试、migration 0006、CLI+API 双入口） |
| [`superpowers/specs/2026-06-07-admin-panel-design.md`](./superpowers/specs/2026-06-07-admin-panel-design.md) | 管理端**设计稿**（REST API 扩展 + 单文件 Web UI，覆盖用户管理、同步触发、候选项、审计日志、导出） |
| [`superpowers/specs/2026-06-08-candidate-management-design.md`](./superpowers/specs/2026-06-08-candidate-management-design.md) | 候选项管理增强**设计稿**（B-036，CSV/JSON 导入 dry-run 预览 + 单条编辑 + 白色主题） |
| [`superpowers/specs/2026-06-09-api-version-upgrade-and-nginx-routing-fix-design.md`](./superpowers/specs/2026-06-09-api-version-upgrade-and-nginx-routing-fix-design.md) | v11→v12 API 版本升级 + nginx location 精确路由**设计稿**（配套 plans：[nginx-routing-fix](./superpowers/plans/2026-06-09-nginx-routing-fix.md)、[frontend-api-version-upgrade](./superpowers/plans/2026-06-09-frontend-api-version-upgrade.md)；**均未实施**，联调前置） |
| [`superpowers/specs/2026-06-09-mongodump-import-design.md`](./superpowers/specs/2026-06-09-mongodump-import-design.md) | 离线 BSON dump 导入**设计稿**（`scripts/import_mongo_dump.py`，复用 sync mappers） |

### 跨前后端功能设计（Block 1-3，2026-06-08）

> 每块拆 **后端(含管理端) / 前端(thvote-fe)** 两份 design + 两份 plan。前端仓库 `D:\personal\thvote-fe`。

| Block | 后端设计 | 前端设计 |
|---|---|---|
| **B-037 安全** | [security-backend-design](./superpowers/specs/2026-06-08-security-backend-design.md) | [security-frontend-design](./superpowers/specs/2026-06-08-security-frontend-design.md) |
| **B-038 作品投票** ⛔废弃 | [works-voting-backend-design](./superpowers/specs/2026-06-08-works-voting-backend-design.md) | [works-voting-frontend-design](./superpowers/specs/2026-06-08-works-voting-frontend-design.md) |
| **B-039 问卷结构化(3A)** | [questionnaire-backend-design](./superpowers/specs/2026-06-08-questionnaire-backend-design.md) | [questionnaire-frontend-design](./superpowers/specs/2026-06-08-questionnaire-frontend-design.md) |
| **B-040 投票对象迁后端(3B)** | [vote-objects-backend-design](./superpowers/specs/2026-06-08-vote-objects-backend-design.md) | [vote-objects-frontend-design](./superpowers/specs/2026-06-08-vote-objects-frontend-design.md) |
| **B-041 自由问卷管理** | [questionnaire-admin-backend-design](./superpowers/specs/2026-06-08-questionnaire-admin-backend-design.md) | [questionnaire-admin-frontend-design](./superpowers/specs/2026-06-08-questionnaire-admin-frontend-design.md) |

> 对应实施计划在 `superpowers/plans/2026-06-08-<topic>-{backend,frontend}.md`（每块 4 份文档：design×2 + plan×2）。**B-038 作品投票已废弃**（官方作品本届不做）。实施顺序建议 B-037 → B-039/B-040。**B-037/B-039/B-040/B-041 后端已全部合入 main（2026-07-14），四项的前端侧均待做**；B-041 取代 B-039 的 admin/契约部分。

---

## 阅读建议

### 第一次进项目想了解用户与认证模块
1. 读设计稿 `superpowers/specs/2026-04-27-user-auth-design.md` §一 § 二理解范围
2. 读迁移文档 `migration/user-manager.md` 看与 Rust 的对照
3. 读实施报告 `superpowers/specs/2026-04-27-user-auth-implementation-report.md` 看实际交付了什么

### 准备上线 / 配置阿里云
- 读 `operations/aliyun-onboarding.md`，按章节顺序操作

### 准备改 CI/CD 或排障部署
- 读 `operations/cicd-pipeline.md`，特别是 §七触发约定

### 想做 Schema 变更
- 读 `architecture/database-schema-management.md`，按当前所处阶段决定是否需要 Alembic migration

### review 用户与认证模块 PR
- 先看 `superpowers/specs/2026-04-27-user-auth-open-issues.md` —— 已知问题都登记在册了，把注意力放在表外的事

### 想知道下一步开发做什么
- 直接打开 [`BACKLOG.md`](./BACKLOG.md)，按"🟢 可立即并行做"挑一项

---

## 维护规则

- **新增文档**必须在表头加 `创建日期 / 最后更新` 两行
- **修改文档**至少把 `最后更新` 改成当天日期，理想情况附一行修订说明
- **新增/移动文档**同步更新本索引
- 跨文档引用时优先**相对路径** + 锚点（§N），便于浏览器/IDE 跳转
- 临时草稿不进 `docs/`；草稿状态的文件命名 `YYYY-MM-DD-DRAFT-*.md` 提醒读者
