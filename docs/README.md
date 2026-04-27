# `docs/` 索引

> 创建日期：2026-04-27
> 最后更新：2026-04-27

按用途分类。每份文档头部都有 `创建日期 / 最后更新` 元信息；本表只列入口和职责。

---

## 仓库级

| 文档 | 用途 |
|---|---|
| [`BACKLOG.md`](./BACKLOG.md) | 🎯 **后续开发单一仪表盘**——所有 follow-up 收拢到这里（B-001..B-N）；按"可立即并行做 / 等 PR merge / 战略阻塞"分组。**找下一步该做什么从这里开始。** |
| [`CHANGELOG.md`](./CHANGELOG.md) | 仓库级变更记录（按 CLAUDE.md §4） |
| [`REFACTOR_TODO.md`](./REFACTOR_TODO.md) | 历史的 FastAPI 重构 TODO（2026-04-27 从根目录移入；内容未做修订） |

## 架构（`architecture/`）

| 文档 | 用途 |
|---|---|
| [`architecture/database-schema-management.md`](./architecture/database-schema-management.md) | DB schema 管理现状与 4 阶段演进路线图（Alembic + init_db 共存的折中策略与目标态） |

## 模块迁移（`migration/`）

| 文档 | 用途 |
|---|---|
| [`migration/user-manager.md`](./migration/user-manager.md) | Rust → Python 用户与认证模块迁移文档（基础对照 + 阶段进度跟踪） |

## 运维 / 操作（`operations/`）

| 文档 | 用途 |
|---|---|
| [`operations/aliyun-onboarding.md`](./operations/aliyun-onboarding.md) | 阿里云 PNVS + DirectMail 从零到上线接入手册（账号/RAM/认证方案/域名验证/SMTP/smoke 验证 + 常见坑） |
| [`operations/cicd-pipeline.md`](./operations/cicd-pipeline.md) | CI/CD 流水线说明：4 个 workflow 的拓扑、Aliyun/Apollo 配置交付路径、触发约定、follow-up |

## 设计稿与实施记录（`superpowers/specs/`）

> 命名约定：`YYYY-MM-DD-<topic>-<kind>.md`，`<kind>` ∈ {`design`, `implementation-report`, `open-issues`}

| 文档 | 用途 |
|---|---|
| [`superpowers/specs/2026-04-27-user-auth-design.md`](./superpowers/specs/2026-04-27-user-auth-design.md) | 用户表与认证模块**设计稿**（路由、数据模型、流程、错误处理、测试策略；§九 是 follow-up F1-F9） |
| [`superpowers/specs/2026-04-27-user-auth-implementation-report.md`](./superpowers/specs/2026-04-27-user-auth-implementation-report.md) | 实施过程**事后记录**：交付清单、与设计稿的偏离、实施期发现的问题（F-impl-1..10） |
| [`superpowers/specs/2026-04-27-user-auth-open-issues.md`](./superpowers/specs/2026-04-27-user-auth-open-issues.md) | 用户与认证模块**已知问题清单**（U-1..U-19 + 祖传 L-1..L-3），按 PR 前已修 / PR 前待修 / PR 后再做 / 祖传 分组 |

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
