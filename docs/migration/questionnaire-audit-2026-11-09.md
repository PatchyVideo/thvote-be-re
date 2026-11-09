# 问卷现状审查与后端化缺口

## 当前规则与剩余清单

核对：2026-11-09，会话收尾；后端功能提交基线97e8fb4，前端功能提交基线16be240，均在 feat/questionnaire-backend-source。本会话未推送或部署，真实题库与线上状态未核验。下方首次审查表为历史记录，不能直接作为当前待办。

已完成并提交：定义来源统一、结果端静态题库迁移、管理台 code 编辑与格式/重复检查、提交答案题型/互斥/分支校验、共用完成评估与重复查询清理、main/extra 整体完成闸门、旧问卷放行退出、独立只读定义检查脚本。

| 阶段 | 后端提交 | 前端提交 | 记录 |
|---|---|---|---|
| 定义来源统一、id/code及管理台 | f12e3ce | 4fda4ef | [第一阶段](../superpowers/plans/2026-11-09-questionnaire-backend-source.md) |
| 答案合法性与单份完成评估 | e9dc072 | — | [第二阶段](../superpowers/plans/2026-11-09-questionnaire-answer-rules.md) |
| 全部必填＋至少一份extra、退出旧放行 | 23fb761 | 16be240 | [整体闸门](../superpowers/plans/2026-11-09-questionnaire-completion-gate.md) |
| 独立命令行定义检查 | 97e8fb4 | — | [检查脚本](../operations/questionnaire-check.md)、[验证记录](../superpowers/plans/2026-11-09-questionnaire-check.md#执行记录) |

下次从本文剩余清单接手：先核对目标环境与真实A/B/C/D映射，再运行 `python -m scripts.check_questionnaire`；脚本尚未对真实库执行。后续开发重点为V2管理监控/作废；特殊图表绑定和跨届定义按实际需要决定。检查脚本不接后台保存或CI，不新增额外检查模块，这是用户已确认范围。

### 已确认的新完成条件（2026-11-09，本地已接入）

用户确认新版共四份问卷：A 必填，B/C/D 为选填，整套完成条件为：

```text
completed(A) AND (completed(B) OR completed(C) OR completed(D))
```

即必须完整完成 A，并在 B/C/D 中至少完整完成一份；允许填写多份选填问卷。只完成 A、只完成 B/C/D，或只部分填写 A/所选问卷都不足以完成整套。单份完成沿用合法作答、可见题组全部完成的既有判断。

这是本次最新产品规则，取代旧 PRD 的“必填＋分问卷＋额外问卷”整套组合要求；原始需求附件保留历史原文。A/B/C/D 暂为业务标签，具体题库身份绑定在实施时核对，不根据旧静态表推定数据库 ID/code。本轮复用现有 required/category 接入前后端判断与文案：A 为 main/required，B/C/D 为 extra/非required，至少一份配额写在整体政策函数。未新增表/接口、未修改真实题库，未部署。整体闸门与以后调整入口见[架构总览](../architecture/backend-overview.md#问卷整体完成闸门与配置入口)。

整体政策先行验证为后端56 passed；退出兼容后，6份相关后端文件集中检查85 passed，随后新增 GraphQL 拒绝反馈覆盖并重跑受影响文件26 passed。前端共享问卷/状态/结果索引三份文件6 passed，`pnpm vote:build` 通过；flake8及两仓库diff检查通过，独立只读审阅无修复项。命令和边界见[整体闸门实施记录](../superpowers/plans/2026-11-09-questionnaire-completion-gate.md#执行记录)。定义检查阶段相关测试58 passed，修复配置日志输出后受影响文件31 passed，详见其验证记录。真实题库分类及账号操作未核验，无浏览器交互、真实数据改动或部署。


| 剩余事项 | 当前事实与影响 | 下一步边界 |
|---|---|---|
| 整套完成条件与文案 | 全部required＋至少一份extra选填已本地接入，旧 raw_paper 放行和无题目行数兜底已移除；三类投票按已保存答案判断，前端提示区分草稿与保存；实际A/B/C/D题库配置尚未核验 | 代码部分已完成，见[整体闸门记录](../superpowers/plans/2026-11-09-questionnaire-completion-gate.md)；剩余为核对真实题库分类及发布，产品条件无需再次确认。提名是否增加同一服务端条件单独确认，不清库或一并删除身份/legacy 路由 |
| V2 管理监控与作废 | 管理 paper 类仍读 RawPaperSubmit；paper_answer 无 invalidated，当前问卷答案未被同一路径管理 | 明确按人/按批次的查看、作废及统计口径后单独设计，不自动新增表/字段 |
| 真实定义检查与使用 | 本轮已实现[独立只读检查脚本](../operations/questionnaire-check.md)，覆盖结构、题型、选项、编码和引用等静态规则；尚未对真实题库运行。后台保存/导入仍只有原先局部校验 | 用户选择单脚本手动/发布前检查，不新增管理台检查模块或保存闸门；真实库配置确认后运行。检查通过不等于所有作答分支可解或结果已核验 |
| 特殊图表和趋势代理 | q11031 地图、q11011 饼图与总趋势代理仍是前端固定用途绑定 | 题目固定时可保留；希望后台自由指定时再确认配置方案，不认定必须新增字段 |
| 跨届与历史定义 | 结构不分届次，答案分届次；改题目含义/code或删除重建会影响历史解释/重算 | 先确认往届展示与编辑场景，再决定是否需要版本/快照；不自动扩成版本系统 |

待核验和运营事项：真实题库 code 是否齐全、现有存量是否有非法答案、真实账号提交/回填，以及部署后结果是否匹配尚未核验。旧非法答案未清理；第二阶段影响其完成率判断，题目回答计数管道仍未重做。结构/规则变更不会自动重算已保存结果，真实核验、清理、回填及重算另行授权。

查看入口：[BACKLOG](../BACKLOG.md) 跟踪总体队列；[第二阶段实施记录](../superpowers/plans/2026-11-09-questionnaire-answer-rules.md) 解释已完成校验及验证；[投票系统需求](../requirements/VoileLabs-人气投票项目-需求文档-投票系统.md) 对照原始规则。

## 首次审查背景（历史）

日期：2026-11-09。已 fetch 核对后端 origin/main=d7cf8cb、前端 origin/dev=5a6b4ae；问卷相关实现与当前工作区一致。未查线上题库或部署，不据本地静态表判断线上缺题或分配 ID。

## 范围与状态

用户已指定第一阶段处理：填写端与结果端统一读取后端问卷定义，以及 id/code/管理台衔接；已确认参考角色模块，共享请求与类型、分应用状态、结构内存复用，继续用 id 作答关联和 code 统计寻址。现已实现[设计](../superpowers/specs/2026-11-09-questionnaire-backend-source-design.md)和[实施计划](../superpowers/plans/2026-11-09-questionnaire-backend-source.md)，第一阶段已提交（后端 f12e3ce、前端 4fda4ef），第二阶段本地实现与验证完成；均未部署。下表保留审查时事实，最新状态见各阶段记录。

## 首次缺口清单（历史，当前状态见文首）

| 项目 | 已核对事实 | 处置范围 |
|---|---|---|
| 结果端静态题库 | `Touhou-Vote/packages/result/src/lib/Questionnaire.ts` 从 shared/data/questionnaire.ts 枚举查询题目、解读题干/类型/选项，并截取编码定位固定问卷槽位 | 第一阶段：改用后端结构建立 id/code/所属问卷映射 |
| 高级搜索 | `components/AdvancedSearch.vue` 的题目与选项选择器来自旧表，帮助链接也指向旧表；生成的 DSL 使用 code | 第一阶段：选项来源改后端，保留现有 DSL 编码语义 |
| 结果与文本详情 | `components/Questionnaire.vue`、`pages/QuestionnaireInputDetail.vue` 用静态题库解释结果；前者复用于全局、角色、音乐、组合详情 | 第一阶段：等待结构就绪后查询，文字与选项来自后端 |
| 特殊图表与趋势 | Questionnaire.vue 按 q11031 选地图、q11011 选饼图；QuestionnaireDetail.vue 用 q11011 作为总趋势代理 | 第一阶段需明确保留这些语义绑定还是后端配置；不能把任意第一题自动当同等语义 |
| 首页展示 | vote 首页 questionnaireNameById.ts 的 key 映射可覆盖后端标题、说明并提供图片 | 第一阶段核对数据与装饰边界，避免后端改名后前端仍展示旧文案 |
| id/code/管理台 | 作答用自增 id；统计按 code，缺 code 的题/选项被跳过。后端可写 code，但管理台表单未提供编辑 | 第一阶段补齐；编码生成、格式及唯一性策略须在实施方案中明确；不自动回填线上数据 |
| 缓存 | 填写端 sessionStorage 缓存结构并默认优先复用；localStorage 保存用户答案草稿 | 第一阶段明确结构缓存策略；答案草稿与题库缓存用途不同 |
| 门禁需求 | PRD 为必填＋至少一份分问卷＋至少一份额外问卷；V2 当前只检查 required 问卷 | 已记录，后续独立确认规则，不并入第一阶段 |
| legacy 门禁 | submitPaperVote 写 raw_paper；非空对象/数组可走旧门禁直接放行 | 已记录，后续确认兼容退出，不并入第一阶段 |
| 作答规则 | 后端校验 ID 存在与归属，但单选多选、未触发非默认分支仍可通过并计为完成 | 已临时复现，后续处理，不并入第一阶段 |
| 管理监控 | paper 监控及作废对应 raw_paper，未覆盖 V2 paper_answer | 后续独立确认 |
| 模型与文档 | API 文档仍展示旧结构；早期完成判定、ORM 顶部编码说明及趋势 resolver 注释过时。当前结构不分届次，答案分届次且按 attempt 追加，历史重算仍读当前定义 | 第一阶段同步所涉及契约与现状；跨届题库版本管理另行决策 |

## 已有查询能力

- `GET /api/v1/questionnaire/structure`：返回 questionnaires 数组，包含题目/选项 code、真实 id、层级、题干、选项和规则；无年度参数。后端缓存 1800 秒，管理修改触发失效。
- GraphQL `queryQuestionnaire(questionsOfInterest, voteYear, query)`：按 code 查询回答分布、文本回答和男女分段数量。接受带 q 前缀或裸 code；响应无题干、类型、选项文案。
- GraphQL `queryCompletionRates(voteYear, query)`：返回真实问卷 key 的完成人数、分母和比例。
- GraphQL `queryQuestionnaireTrend(questionIds, voteYear, query)`：按题返回趋势；实际计票已接 append-only 历史，resolver 的“尚未实现”注释过时。
- REST `POST /api/v1/result/questionnaire/`、`questionnaire-trend/`、`completion-rates/` 及另一组 GraphQL JSON 查询也存在。结果前端目前使用上面的 query* 契约。

普通结果读取 Redis 预计算快照；高级搜索 query 走既有筛选计算与缓存。修改结构不会自动重算结果。全年未计票会报 RESULT_NOT_COMPUTED；已计票但个别题无数据时，批量回答查询跳过该题、趋势返回对应空序列。零回答题的展示应由后端定义补齐，不能把缺结果等同题不存在。

## 第一阶段已实现（2026-11-09）

复用结构接口和现有统计接口。填写、跳题与答案继续使用真实 id；结果查询、DSL 和旧链接继续使用 code。前端只维护服务返回定义的索引、内存缓存和用户草稿，不保留正式静态题库。管理台补齐 code 维护及直接校验；不引入新数据库表、版本系统或自动恢复机制。

替代方案是将结果寻址全部改为 id，可减少双标识使用，但涉及统计快照键、筛选 DSL、旧链接及配置的成套迁移，范围更大。当前推荐沿用现有分工，先完成来源统一。

结构缓存按已确认方向仅在当前应用运行期间内存复用，刷新重新请求；请求失败显示错误与重试入口。本地已实现，未部署。

## 已完成验证与兼容边界

- 审查阶段运行 `python -m pytest tests/unit/test_questionnaire_completion.py tests/unit/test_questionnaire_answer_validation.py tests/unit/test_questionnaire_assembler.py tests/unit/test_questionnaire_importer.py -q`：36 passed，1 条现有 asyncio 弃用警告。
- 临时直接调用 validate_answer_rows/is_complete，复现单选两个选项、未触发非默认分支被接受；未新增永久测试。
- 未写库、回填、重算、发布或进行浏览器交互。当前文档记录不改变接口或运行行为；后续代码回滚和数据兼容按确认后的方案补充。

## 第一阶段验收与剩余

第一阶段现已提交：后端 f12e3ce、前端 4fda4ef，均在 feat/questionnaire-backend-source，未推送或部署。第二阶段已编写[作答规则设计](../superpowers/specs/2026-11-09-questionnaire-answer-rules-design.md)和[实施计划](../superpowers/plans/2026-11-09-questionnaire-answer-rules.md)，现已本地实现并完成相关验证；不把后续产品门禁/监控等事项并入。

共享结构请求/索引、填写内存复用和首页后台文案、结果图表/文本详情/高级搜索、管理台 code 编辑及创建/更新/导入校验已实现。历史空 code 兼容并提示，采用应用层重复检查，无 DB 迁移。无效整树导入在删除旧定义前拒绝。

相关 Python 检查 68 passed、前端行为测试 5 passed；填写、结果、管理台构建和改动文件 flake8/diff 检查通过。独立只读审阅后处理了零回答雷达图的空状态，详见实施计划。

第一阶段交付时继续跟踪：特殊图表与代理题绑定、完成规则和 legacy 门禁差异、作答规则校验、V2 管理监控/作废、跨届定义。作答规则校验随后已在第二阶段完成，当前剩余见文首。未查询线上题库或更改真实 code，无法据此确认线上已具备全部统计编码。未浏览器交互、部署或重算。

## 第二阶段：答案合法性与完成度（2026-11-09）

已在本地补齐题型/选项组/显式互斥、分支与隐藏作答校验，完成度复用同一规则结果，非法新批次不落库；合法部分答案仍可保存，门禁答案重复查询已移除。未推送或部署。历史已知非法作答不计对应卷完成，未知孤立组与空配置兜底保留，不自动清理或重算。

验证、临时前后端对照和性能测量见[实施记录](../superpowers/plans/2026-11-09-questionnaire-answer-rules.md)。第二阶段交付时，整套问卷完成产品规则、legacy 门禁退出、V2 管理作废、特殊图表配置与跨届定义仍未处理；整体条件随后已确认并本地接入，当前剩余见文首。题库配置校验只包含本轮运行计算不收敛的报错，没有完成管理端规则完整性治理。

第二阶段最终验证：相关pytest 99 passed，改动Python的flake8与diff检查通过；前端4类快照对照一致，临时CPU及本地SQL计数见实施记录。独立审阅指出的空配置旧题目ID兜底回归已修复，新提交仍严格校验。
