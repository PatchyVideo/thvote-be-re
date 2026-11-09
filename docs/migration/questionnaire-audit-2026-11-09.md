# 问卷现状审查与后端化缺口

日期：2026-11-09。已 fetch 核对后端 origin/main=d7cf8cb、前端 origin/dev=5a6b4ae；问卷相关实现与当前工作区一致。未查线上题库或部署，不据本地静态表判断线上缺题或分配 ID。

## 范围与状态

用户已指定第一阶段处理：填写端与结果端统一读取后端问卷定义，以及 id/code/管理台衔接；已确认参考角色模块，共享请求与类型、分应用状态、结构内存复用，继续用 id 作答关联和 code 统计寻址。现已实现[设计](../superpowers/specs/2026-11-09-questionnaire-backend-source-design.md)和[实施计划](../superpowers/plans/2026-11-09-questionnaire-backend-source.md)，第一阶段已提交（后端 f12e3ce、前端 4fda4ef），第二阶段本地实现与验证完成；均未部署。下表保留审查时事实，最新状态见各阶段记录。

## 缺口清单

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

剩余继续独立跟踪：特殊图表与代理题绑定后端配置、完成规则和 legacy 门禁差异、作答规则校验、V2 管理监控/作废、跨届定义版本。未查询线上题库或更改真实 code，无法据此确认线上已具备全部统计编码。未浏览器交互、部署或重算。

## 第二阶段：答案合法性与完成度（2026-11-09）

已在本地补齐题型/选项组/显式互斥、分支与隐藏作答校验，完成度复用同一规则结果，非法新批次不落库；合法部分答案仍可保存，门禁答案重复查询已移除。未推送或部署。历史已知非法作答不计对应卷完成，未知孤立组与空配置兜底保留，不自动清理或重算。

验证、临时前后端对照和性能测量见[实施记录](../superpowers/plans/2026-11-09-questionnaire-answer-rules.md)。剩余事项：整套问卷完成产品规则、legacy 门禁退出、V2 管理作废、特殊图表配置与跨届定义。题库配置校验只包含本轮运行计算不收敛的报错，没有完成管理端规则完整性治理。

第二阶段最终验证：相关pytest 99 passed，改动Python的flake8与diff检查通过；前端4类快照对照一致，临时CPU及本地SQL计数见实施记录。独立审阅指出的空配置旧题目ID兜底回归已修复，新提交仍严格校验。
