# 当前后端结构与数据来源

> 核对：2026-11-08，基于 feat/pinyin-backend-search 已提交实现。本文是源码导航，不代表当前线上数据或部署已经核验。

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

`StructureIndex → rules → validation → completion → service`：rules 是无 IO 的纯计算，validation 先检查结构/引用并复用分支评估，completion 使用同一结果计算完成集合。提交只保存合法快照，未完成不等于非法；统计和门禁复用相同语义及现有历史兼容。投票门禁将预读答案传入 service，避免重复查询；未新增结构缓存、表或接口。

关联推进有界且从默认可见组开始，结果不能由隐藏组答案自行解锁。详细规则、错误契约与临时性能/SQL 观察见[实施记录](../superpowers/plans/2026-11-09-questionnaire-answer-rules.md)。没有核验线上题库、部署或重算。
