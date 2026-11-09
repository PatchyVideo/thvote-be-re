# 当前后端结构与数据来源

> 核对：2026-11-09，当前分支 feat/questionnaire-backend-source；此前基线 e9dc072，整体完成政策及旧问卷门禁兼容退出纳入本轮提交，未推送或部署。本文是源码导航，不代表当前线上数据或部署已经核验。

## 入口与职责

- [src/main.py](../../src/main.py) 挂载 FastAPI、`/api/v1` REST、`/graphql` 与仍有调用方的 legacy 兼容路由。
- `src/apps/<模块>/router.py` 解析请求和转换响应，service 编排业务，dao 读取／写入数据；数据库模型在 `src/db_model/`。
- 接口字段查 [API 契约](../api/voteable-api-contract.md) 与实际路由／schema，开放事项查 [BACKLOG](../BACKLOG.md)。

## 与前端迁移相关的现状

| 信息／功能 | 当前来源与边界 | 实现入口 |
|---|---|---|
| 角色、音乐候选 | 后端按年度读取 candidate／voteable／work，返回候选 ID、资源与筛选 metadata | [vote_objects](../../src/apps/vote_objects/) |
| 名称、别名、图片与试听地址 | 数据库资料随候选接口下发；前端展示对象仍需加载，不再维护同一份静态资源表 | [vote_objects DAO](../../src/apps/vote_objects/dao.py) |
| 候选拼音搜索 | 唯一 POST `/api/v1/autocomplete/search`；pypinyin＋项目内匹配，返回完整候选 ID 集合 | [autocomplete](../../src/apps/autocomplete/)；[匹配规则](../superpowers/specs/2026-11-08-pinyin-candidate-search-design.md) |
| 问卷结构与提交 | 后端结构接口返回数组；GraphQL submitPaperV2／getPaperV2 提交及回填结构化答案 | [questionnaire](../../src/apps/questionnaire/) |
| 计票与结果 | 读取真实提交批次，使用数据库候选白名单，计算主榜／净增量趋势／DSL 子集结果 | [result](../../src/apps/result/) |

前端的临时筛选、个人未提交草稿及展示状态仍由前端管理。问卷定义经共享请求供填写/结果分别加载，结构仅在本次应用运行中内存复用，刷新重新请求；个人答案保留 localStorage。结果文字与筛选选项来自后端定义，统计仍用 code 查询计票快照；特殊图表和趋势代理题暂保留原绑定。静态投票时间仍是已识别现状。

## 问卷整体完成闸门与配置入口

### 当前产品规则与数据配置

本轮本地规则：至少存在一份必填、所有必填问卷完成，并至少完成一份 `category=extra` 且 `required=false` 的选填问卷。当前业务 A 为必填，B/C/D 为同一组选填；允许多填，不要求恰好一份。A/B/C/D 是业务标签，数据库实际身份和线上配置未核验。

| 后台字段/规则 | 当前设置 | 调整位置 |
|---|---|---|
| A 的必填属性 | `required=true`，`category=main` | 管理台问卷元数据；required 决定必须完成的集合 |
| B/C/D 的组选填身份 | `required=false`，`category=extra` | 管理台问卷元数据；只有 extra 且非必填才计入任选集合 |
| 组选填完成数量 | 至少1份，允许多填 | 目前固定在整体政策函数中，不是 Nacos/环境变量或管理台数量配置 |

当前使用已有字段和单层 main/extra，无新增表、组接口或阈值字段。必填集合或 extra 选填集合缺失时不视为整体完成；单份完成采用已实现的合法作答/可见题组规则，没有可答题目或没有题组的问卷不计完成。

### 代码入口与调用方向

| 职责 | 入口 | 说明 |
|---|---|---|
| 单份问卷完成集合 | [completion.py](../../src/apps/questionnaire/completion.py) 的 `completed_questionnaire_ids` / `completed_from_evaluation` | 与合法性共用 rules 结果；统计也复用此层。不要把组选填数量要求混入单份完成率 |
| **整体政策的修改点** | 同文件 `meets_completion_policy(questionnaires, completed)` | 统一表达“全部 required＋至少一份 extra”；将来调整配额先改这里并同步前端预判 |
| 定义和已保存答案的编排 | [QuestionnaireService.is_complete](../../src/apps/questionnaire/service.py) | 按本届最新已存答案求完成集合，再调用整体政策；`completion.is_complete` 是纯函数组合入口 |
| **实际服务端投票闸门** | [SubmitService._require_questionnaire](../../src/apps/submit/service.py) | 角色/音乐/组合提交调用，未完成抛 QUESTIONNAIRE_NOT_COMPLETED；复用预读答案。提名提交未调用同一闸门，不能据此前端守卫宣称服务端所有入口均已覆盖 |
| 前端体验预判 | `Touhou-Vote/packages/shared/api/questionnaire.ts` 的 `meetsQuestionnaireCompletionPolicy`，由 `vote/.../questionnaireStateV2.ts:isQuestionnaireAllDoneV2` 调用 | 使用同一结构字段与本地运行时完成情况，路由守卫和成功提示复用；它不代替后端对已提交答案的判断 |
| 前端入口拦截/文案 | `vote/src/main/main.ts` 的 `requireQuestionnaire` 守卫；`home/lib/questionnaireNameById.ts` 和 `UserQuestionnaireDp.vue` | 分类和提示同步新规则，网页刷新重新取定义 |

```text
合法作答/可见题组 → 单份完成集合
                    ↓
       meets_completion_policy（整体组合政策）
                    ↓
  QuestionnaireService.is_complete（按已保存答案）
                    ↓
 SubmitService._require_questionnaire（服务端阻止投票）
```

配置运维时，调整哪份必填/哪份属于选填组，使用管理台的 required/category 即可；变更阈值（例如改为至少2份）目前需要修改后端 `meets_completion_policy` 与前端 `meetsQuestionnaireCompletionPolicy`，同步文案和相关用例。以后出现多个组选N时再设计独立分组模型，不预先新增机制。

本轮已按[整体闸门实施计划](../superpowers/plans/2026-11-09-questionnaire-completion-gate.md)移除 raw_paper 直接放行和空题库 row-coverage 完成兜底。角色/音乐/组合提交只按本届最新已保存的 V2 答案判断；REST 未完成返回 HTTP 422、detail=QUESTIONNAIRE_NOT_COMPLETED，GraphQL 使用同名 error_kind 及中文提示。不清库，也不一并删除身份或 legacy 路由。问卷提交本身仍允许合法未完成快照，不能在 submitPaperV2 中要求整套完成后才保存。

定义编辑完成后可运行 `python -m scripts.check_questionnaire`，直接读取四张定义表检查结构与引用，错误退出1、警告不阻断、无法执行退出2。检查函数和入口都在单个脚本中，未接后台保存/发布状态或CI；与用户作答/投票完成闸门职责不同。规则及使用边界见[问卷定义检查](../operations/questionnaire-check.md)。

## 缓存与更新

- `src/common/cache.py` 提供公共读缓存及前缀失效；管理写入复用既有失效路径。
- 候选列表缓存 600 秒，问卷结构缓存 1800 秒；拼音派生语料与查询结果分别缓存 60 秒。
- `result:*` 是计票产物，按计票流程重建，不随普通读缓存清理。
- 个人身份／提交数据不进入本次公共候选搜索缓存；前端已选项不影响共享匹配结果。
- 后端管理失效、前端内存复用和用户草稿是不同生命周期，不能以“清缓存”为由一起删除。

## 迁移与操作边界

当前本地 Alembic 图是单 head 0022；云端迁移状态未查询，新增迁移前重新核对。导入、回填、重算、部署与推送需用户当前授权，历史计划里的命令不构成执行许可。

运维代码入口见 [CI/CD 说明](../operations/cicd-pipeline.md)，Nacos 限制见 [热更新限制](nacos-hot-reload-limits.md)。实际服务器操作先遵守项目 AGENTS 中的部署约定。

## 设计与历史资料

- [技术设计记录](../superpowers/specs/README.md)：查当时的需求映射与取舍，旧状态／checkbox 不作实施清单。
- [已完成或被取代的计划](../archive/README.md)：保留执行过程；B-037 的展示差异与历史对比等真实残留继续由 BACKLOG 跟踪。
- [最近变更](../CHANGELOG.md)、[2026Q3](../CHANGELOG-archive-2026Q3.md)、[2026H1](../CHANGELOG-archive-2026H1.md)：按发生日期追溯，不作为当前数据或部署结论。
- [官方需求原文](../requirements/) 保留原始依据，不参与过程文档精简。

## 问卷作答规则（2026-11-09 本地实现）

`StructureIndex → rules → validation → completion → service`：rules 是无 IO 的纯计算，validation 先检查结构/引用并复用分支评估，completion 使用同一结果计算完成集合。提交只保存合法快照，未完成不等于非法；统计和门禁复用相同单份完成语义。读取仍忽略孤立题组，提交严格拒绝未知 ID。投票门禁将预读答案传入 service，避免重复查询；未新增结构缓存、表或接口。

关联推进有界且从默认可见组开始，结果不能由隐藏组答案自行解锁。详细规则、错误契约与临时性能/SQL 观察见[实施记录](../superpowers/plans/2026-11-09-questionnaire-answer-rules.md)。没有核验线上题库、部署或重算。
