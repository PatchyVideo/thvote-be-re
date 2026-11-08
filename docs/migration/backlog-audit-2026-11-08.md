# BACKLOG 与历史状态核对（2026-11-08）

## 范围与基准

本轮针对“历史遗留，实际已实现、已废弃或没有需求”的条目核对源码，并修正 BACKLOG、现役索引与相关主题文档入口。没有实施待办中的功能。

- 后端：`feat/pinyin-backend-search`，`44bd972`，包含远端 `origin/main=6d8afc1`。
- 前端：同名分支，`edeaeea`，包含远端 `origin/dev=ef028e0`。本次 fetch 后两条远端基线未变化。
- 前端原有 voteDraft、voteData、codegen、LOCAL_DEV 等未提交修改保留，未当成已提交功能计入结论。CP 元数据迁移已经单独提交 `edeaeea`。
- 未查询线上数据库、Nacos、依赖告警或实际部署；历史文档中的数据值、凭据状态和上线记录不作为本次实时结论。

## 退出开放队列的 9 个条目

原条目移入 [BACKLOG 归档](../BACKLOG-archive.md)，主题保留历史措辞，状态列及补记写明本轮判定。

| 编号 | 核对结果 | 当前源码证据 |
|---|---|---|
| B-028 | 同一 workflow 已有手动生产发布通道，“没有 prod 路径”已过时 | `.github/workflows/deploy-test.yml:39` 的 deploy_prod 输入、`:354` deploy-prod job、`:358` 条件及独立生产目标；不以缺少单独 deploy-prod.yml 判缺功能 |
| B-039 | 问卷主路径已经后端驱动，早期固定槽方案由 B-041 数组契约取代 | 前端 `questionnaire/Questionnaire.vue:140,239`、`questionnaire/lib/questionnaireStateV2.ts:22,60,199,254` |
| B-040 | 角色、音乐、CP 候选与资源已经从后端读取 | 前端 `common/lib/voteObjectsDataSource.ts:18,61,80`、角色／音乐 list 模块、CP CharacterSelect 使用共同角色列表 |
| B-041 | 问卷数组、category/order、required、隐藏组、答案提交及回填均有消费 | 前端 `questionnaireStateV2.ts:25,63,159`、`home/components/UserQuestionnaire.vue:54`、`questionnaireV2Parser.ts:72` |
| B-050 主项 | v1 已完成；“后补2/3/5/6仍开放”的集合失实 | trend、DSL 和 DB 白名单已接入；上届对比单独保留 B-050-后补3，不把整个计票工程重新列为待做 |
| B-050-后补2 | append-only 净增量趋势已接到主榜及 DSL 子集 | `src/apps/result/trend.py:21`、`compute_service.py:82,111`、`advanced_search/service.py:220`；历史提交 b230e37 |
| B-057 | 管理端、导入与前端收口已具备；历史数据部分合并到 B-050-后补3 | `src/apps/admin/router.py:827,878`；`voteable_import_service.py:209,299`（60a233e）；前端 metadata、candidateId 与专辑名反查，CP edeaeea |
| B-061 | API、DAO 与管理界面已展示 attempt | `src/apps/admin/monitor/schemas.py:48`、`dao.py:158,184`、`admin-ui/src/views/monitor/VotesView.vue:29,136` |
| B-063 | 已有关键解析、URL 路由与限流测试 | `tests/unit/test_scraper_sites.py`、`test_scraper_parse_url.py`、`tests/integration/test_scraper_rate_limit.py`；1559ea0 与 CHANGELOG 2026-10-20。未声称所有站点成功路径均穷尽覆盖 |

前端路径均位于 `Touhou-Vote/packages/vote/src/`，另有标注的 result 路径除外。源码行号对应本轮基准，后续可能变化。

## 不应自动当成功能缺口的记录

- **B-055 connect**：结果页仍有占位文件，但入口已注释；旧结果审计 §六已经确认无对应需求。不能因看到“维护中”就安排补页。
- **B-055 CP compare/evolution**：现有结果站确实只有四个 CP 页面，页面数量与角色／音乐不同本身不是已批准需求。
- **B-055 Doujin**：当前 `packages/result/src/pages/Doujin.vue:13` 仍有 1272 及示例作品／评论；旧审计允许运营维护。是否数据化留待具体运营需要。
- **B-055 `/test` 与日期**：当前 result router 已无旧 `/test`；vote 包自己的 TestPage 是另一对象，本轮不转造新待办。结果页已使用统一 voteYear 与后端 timeline，不能继续沿用“20多处 year11／2022 日期”的旧描述。
- **B-062**：旧建议链路和 CP 空方法已在 44bd972 移除；这表示该历史实现被废弃，不表示新增了 CP 组合搜索。删除 BACKLOG 中未编号的重复记录。
- **B-010／013／020／026**：覆盖率阈值、幂等性、mypy 和新增 schema 治理检查仍是按场景决定的建议。缺少这些机制不自动证明当前功能有 bug，也不授权扩大测试或 CI。
- **B-031／056**：配置格式兼容与历史迁移命名需要维护约束，不能直接删除兼容或重命名已执行迁移。本地静态解析迁移图为单 head 0022，云端 Alembic 状态未查询。
- **GET /server-time**：当前源码未发现该接口；当前业务调用方也未发现相关调用。旧 gateway 曾有此端点不构成必须移植的证据。

## 仍存在或只完成一部分的内容

| 项目 | 本次确认的边界 |
|---|---|
| B-037 | 主要提名校验响应、待审核提示与问卷门禁已有实现；逐条 index 提示与原计划有差异，现为合并原因／重复数量。可选 approved 展示原本就待产品确认，不自动升级需求 |
| B-050-后补3 | 主榜 `compute_service.py:111` 和子集 `advanced_search/service.py:249` 仍传空 historical，GraphQL `result_compat.py:164` 使用 -1／-1.0。旧 load_historical 已删除；“现有函数按name取值”和“硬编码0”均需撤销。线上历史数据与旧 API 可用性未核验 |
| B-053 | 任意问卷题 DSL 过滤已有回答索引和 QCond；专用任选轴一次输出多个分组的 API／前端尚未提供，是否需要另行决定 |
| B-059 | `nacos.py:357`、`config.py:20` 会 warning，再尝试本地或默认配置；未 fail-fast 属实，“静默无日志”不准确。是否改变启动规则仍需具体决策 |
| monitor 提示 | `_B050_NOTE` 仍声称要等计票重写；实际 `compute_dao.py:41` 已排除作废的最新票。残留问题是提示文案，不是作废能力未接计票 |
| B-033 | 前端 `home/lib/user.ts:190` 仍调用 `${API_PREFIX}/user-token-status`，后端仍挂载 legacy router。不能直接删除兼容层 |

B-045／046 的前端耗时与 clientEnv 已在角色、音乐、CP、提名提交中传递；问卷 V2 提交仅 voteToken＋answers，不能扩成“所有提交入口都一致”的结论。当前部署、真实落库、问卷内容与语义 code、Nacos 开关以及旧依赖告警均保持“未核验”。

## 文档处理与验证

- BACKLOG 分为源码仍有差异、外部／运营状态、按需建议，取消重复的旧“立即做”和“推荐下一步从零迁移”队列。
- 相关前端计划／设计、work 统一、计票后补、autocomplete 旧设计增加当前状态；历史正文和 checkbox 只保留追溯用途，不伪装成逐步重新执行。
- 更新文档索引、旧 refactor-todo 归档入口及结果审计入口，防止“已归档”状态又从另一入口重新出现。
- CP 改动提交前相关测试 5 passed，ESLint 通过；生产构建在该代码版本通过。文档整理不新增产品测试，不重跑全量测试，也不触发部署、迁移、重算或依赖升级。
- 文档改动验证使用 `git diff --check`、新增 Markdown 链接目标检查、编号归档一致性检查；原有未提交文件保留。

本轮已通过新增 Markdown 链接目标检查、9 项编号唯一归档／移出开放表检查及两仓库 `git diff --check`；后端源码、测试、workflow、迁移和依赖均无改动。
