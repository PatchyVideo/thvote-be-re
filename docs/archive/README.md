# `docs/archive/` 归档索引

> 创建日期：2026-08-31

本目录存放**历史过程记录**：已实施完毕的实施计划、已废弃的设计、一次性交接文档、过期的进度快照。

**这里的内容不代表当前实现。** 找现状请去：

- [`../BACKLOG.md`](../BACKLOG.md) —— 还开放的工作
- [`../CHANGELOG.md`](../CHANGELOG.md) —— 已落地的变更
- [`../README.md`](../README.md) —— 现役文档索引

归档件保留原正文；新增归档状态说明，并随移动修正相对链接。原始正文与既有记录不因归档被重新认定为待办。

---

## 独立归档件

| 文档 | 状态 | 说明 |
|---|---|---|
| [`2026-05-30-refactor-todo.md`](./2026-05-30-refactor-todo.md) | 已归档 | 2026-05-30 的模块级迁移进度快照；内容已过期。迁出时转入 B-062／B-063；2026-11-08 核对时，前者已随旧建议链路废弃，后者已补关键测试，见 [本轮记录](../migration/backlog-audit-2026-11-08.md) |

---

## 实施计划（`superpowers/plans/`）

已执行完毕或已废弃的实施计划。计划是一次性的：写出来是为了指导实施，实施完就只剩追溯价值。

| 文档 | 状态 | 落地去向 / 废弃原因 |
|---|---|---|
| [`2026-06-08-questionnaire-admin-frontend.md`](superpowers/plans/2026-06-08-questionnaire-admin-frontend.md) | 2026-11-08 归档 | 问卷数组契约、提交与回填已接入；本轮未核验线上题库或部署 |
| [`2026-06-08-questionnaire-frontend.md`](superpowers/plans/2026-06-08-questionnaire-frontend.md) | 2026-11-08 归档 | 早期固定槽方案已由后续数组契约取代，主路径已后端化 |
| [`2026-06-08-security-frontend.md`](superpowers/plans/2026-06-08-security-frontend.md) | 2026-11-08 归档 | 主要接入已实现；逐条提示差异及可选展示保留 B-037 判断，不重跑整个旧计划 |
| [`2026-06-08-vote-objects-frontend.md`](superpowers/plans/2026-06-08-vote-objects-frontend.md) | 2026-11-08 归档 | 候选／资源／candidateId／metadata 已接入，CP 收口 edeaeea |
| [`2026-07-21-work-table-unified.md`](superpowers/plans/2026-07-21-work-table-unified.md) | 2026-11-08 归档 | 代码收口已具备；历史榜单数据／接线保留 B-050-后补3 |
| [`2026-09-06-user-identity-model.md`](superpowers/plans/2026-09-06-user-identity-model.md) | 2026-11-08 归档 | 身份归一化已于 2026-09-06 实施，旧迁移步骤只供追溯 |
| [`2026-11-08-autocomplete-search-consolidation.md`](superpowers/plans/2026-11-08-autocomplete-search-consolidation.md) | 2026-11-08 归档 | 统一 /autocomplete/search 已本地提交，见后端 44bd972、前端 4c2af13；未发布 |
| [`2026-11-08-pinyin-candidate-search.md`](superpowers/plans/2026-11-08-pinyin-candidate-search.md) | 2026-11-08 归档 | 第一阶段实现已提交，后续统一接口取代临时路径；未发布 |
| [`2026-05-13-autocomplete.md`](./superpowers/plans/2026-05-13-autocomplete.md) | 已实施 | 落地于 `src/apps/autocomplete/`（dao/service/router 齐备） |
| [`2026-05-13-result-query.md`](./superpowers/plans/2026-05-13-result-query.md) | 已实施（后被取代） | 计票核心已于 2026-07-18 由 B-050 v1 重写取代，见 [b050-result-recount-v1](../superpowers/specs/2026-07-18-result-recount-id-based-design.md) |
| [`2026-05-16-quick-wins.md`](./superpowers/plans/2026-05-16-quick-wins.md) | 已实施 | B-017/018/025/027/029/030 六项均已完成，见 [BACKLOG-archive](../BACKLOG-archive.md) |
| [`2026-05-16-sso-implementation.md`](./superpowers/plans/2026-05-16-sso-implementation.md) | 已实施 | B-007，2026-05-17 完成（QQ + THBWiki OAuth，migration 0004） |
| [`2026-05-20-graphql-schema-alignment.md`](./superpowers/plans/2026-05-20-graphql-schema-alignment.md) | 已实施（部分被取代） | `types.py`/`resolvers/` 已落地；result 查询部分于 2026-07-19 由契约层 `result_compat.py` 重写取代 |
| [`2026-05-30-graphql-login-bridge.md`](./superpowers/plans/2026-05-30-graphql-login-bridge.md) | 已实施 | CHANGELOG 2026-05-30「GraphQL 登录 mutation 桥接」 |
| [`2026-06-07-admin-panel.md`](./superpowers/plans/2026-06-07-admin-panel.md) | 已实施（UI 已被取代） | B-035，2026-06-07；单文件 Web UI 于 2026-07-18 由 B-049 Vue 重写取代 |
| [`2026-06-07-graphql-submit-bridge.md`](./superpowers/plans/2026-06-07-graphql-submit-bridge.md) | 已实施 | CHANGELOG 2026-06-07「GraphQL Submit 桥接」 |
| [`2026-06-07-mongodb-sync.md`](./superpowers/plans/2026-06-07-mongodb-sync.md) | 已实施 | B-034，2026-06-07（11 collections + 断点续传 + CLI/API 双入口） |
| [`2026-06-08-candidate-management.md`](./superpowers/plans/2026-06-08-candidate-management.md) | 已实施 | B-036，2026-06-08 |
| [`2026-06-08-questionnaire-admin-backend.md`](./superpowers/plans/2026-06-08-questionnaire-admin-backend.md) | 已实施 | B-041 后端，2026-07-14 合入 main |
| [`2026-06-08-questionnaire-backend.md`](./superpowers/plans/2026-06-08-questionnaire-backend.md) | 已实施 | B-039 后端，2026-07-14 合入 main |
| [`2026-06-08-security-backend.md`](./superpowers/plans/2026-06-08-security-backend.md) | 已实施 | B-037 后端，2026-07-14 合入 main |
| [`2026-06-08-vote-objects-backend.md`](./superpowers/plans/2026-06-08-vote-objects-backend.md) | 已实施 | B-040 后端，2026-07-14 合入 main |
| [`2026-06-08-works-voting-backend.md`](./superpowers/plans/2026-06-08-works-voting-backend.md) | 已废弃 | B-038，2026-06-08 确认官方作品投票本届不做 |
| [`2026-06-08-works-voting-frontend.md`](./superpowers/plans/2026-06-08-works-voting-frontend.md) | 已废弃 | B-038，同上 |
| [`2026-06-09-frontend-api-version-upgrade.md`](./superpowers/plans/2026-06-09-frontend-api-version-upgrade.md) | 已实施 | v11→v12 前缀切换，2026-07-14 随 nginx v12 路由上线 |
| [`2026-06-09-nginx-routing-fix.md`](./superpowers/plans/2026-06-09-nginx-routing-fix.md) | 已实施 | CHANGELOG 2026-07-14「nginx v12 路由部署」 |
| [`2026-07-17-admin-console-security-monitoring-backend.md`](./superpowers/plans/2026-07-17-admin-console-security-monitoring-backend.md) | 已实施 | B-049 Plan 1，2026-07-17（migration 0014 + `src/apps/admin/monitor/`） |
| [`2026-07-18-b050-result-recount-v1.md`](./superpowers/plans/2026-07-18-b050-result-recount-v1.md) | 已实施 | B-050 v1，2026-07-18 |
| [`2026-07-19-result-graphql-compat.md`](./superpowers/plans/2026-07-19-result-graphql-compat.md) | 已实施 | B-052，2026-07-19（12 个 `query*` 契约层） |
| [`2026-07-20-voteable-cross-year-stable-id.md`](./superpowers/plans/2026-07-20-voteable-cross-year-stable-id.md) | 已实施 | 后端 v1，2026-07-23 合入 main |
| [`2026-07-23-tally-db-truth-source.md`](./superpowers/plans/2026-07-23-tally-db-truth-source.md) | 已实施 | B-050-后补6，#26 于 2026-08-13 合入 main 并部署（迁移 0016 + `voteable_import_service.py`） |
| [`2026-08-14-advanced-search-dsl.md`](./superpowers/plans/2026-08-14-advanced-search-dsl.md) | 已实施 | B-050-后补5，2026-08-14（`src/apps/result/advanced_search/`） |
| [`2026-08-29-questionnaire-trend-append-only.md`](./superpowers/plans/2026-08-29-questionnaire-trend-append-only.md) | 已实施 | B-050-后补2 Step 2，2026-08-29（迁移 0017 + `src/apps/result/trend.py`） |


## 设计稿与实施记录（`superpowers/specs/`）

**只有已废弃、纯操作性、或属于事后记录的 spec 才归到这里**——仍有参考价值的设计稿留在 [`../superpowers/specs/`](../superpowers/specs/) 现役目录。

| 文档 | 状态 | 落地去向 / 废弃原因 |
|---|---|---|
| [`2026-05-13-autocomplete-design.md`](superpowers/specs/2026-05-13-autocomplete-design.md) | 已被取代 | 旧 ILIKE 建议实现及 CP 空方法已移除，由拼音候选接口取代 |
| [`2026-06-07-admin-panel-design.md`](superpowers/specs/2026-06-07-admin-panel-design.md) | 已被取代 | 单文件 admin panel 已被 Vue 管理台设计取代 |
| [`2026-06-08-questionnaire-frontend-design.md`](superpowers/specs/2026-06-08-questionnaire-frontend-design.md) | 已被取代 | 旧固定槽／年度契约被后续问卷数组契约取代 |
| [`2026-04-27-user-auth-implementation-report.md`](./superpowers/specs/2026-04-27-user-auth-implementation-report.md) | 已归档 | 实施过程事后记录，非设计文档；模块现状见 [migration/user-manager](../migration/user-manager.md) |
| [`2026-06-08-works-voting-backend-design.md`](./superpowers/specs/2026-06-08-works-voting-backend-design.md) | 已废弃 | B-038，2026-06-08 确认官方作品投票本届不做 |
| [`2026-06-08-works-voting-frontend-design.md`](./superpowers/specs/2026-06-08-works-voting-frontend-design.md) | 已废弃 | B-038，同上 |
| [`2026-06-09-api-version-upgrade-and-nginx-routing-fix-design.md`](./superpowers/specs/2026-06-09-api-version-upgrade-and-nginx-routing-fix-design.md) | 已实施 | v12 路由已于 2026-07-14 上线；纯操作性设计，无长期参考价值 |


## 交接记录（`superpowers/handoffs/`）

一次性任务交接记录。

| 文档 | 状态 | 落地去向 / 废弃原因 |
|---|---|---|
| [`2026-07-21-work-refactor-test-fix-handoff.md`](./superpowers/handoffs/2026-07-21-work-refactor-test-fix-handoff.md) | 已归档 | 一次性交接记录，任务已完成；代码收口已完成；实际历史对比剩余见 BACKLOG B-050-后补3 |


---

## 归档规则

往这里加东西之前，先确认它属于以下四类之一：

1. **实施计划已执行完** —— 有 CHANGELOG 落地条目或 BACKLOG 已标完成
2. **设计已废弃** —— 明确决定不做
3. **一次性过程记录** —— 实施报告、交接文档、进度快照
4. **快照类文档已过期** —— 内容描述的是某个时点，且已有在维护的替代品

加进来时**必须**：

- 在文件 H1 之后插入归档状态块：状态 + 证据（B 编号 / CHANGELOG 日期 / 代码路径）+ 「不代表当前实现」+ 归档日期
- 在本索引加一行
- **不删除正文**，历史判断依据要能追溯

> 判定状态时**不要凭印象**。plans 里的 `- [ ]` checkbox 从未被维护过（见 BACKLOG B-057⑤），不能作为完成度依据；
> 请以 [`../BACKLOG.md`](../BACKLOG.md) / [`../BACKLOG-archive.md`](../BACKLOG-archive.md) / [`../CHANGELOG.md`](../CHANGELOG.md) 三者交叉核对，必要时直接查代码。
