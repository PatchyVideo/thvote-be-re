# 问卷定义来源统一实施计划

> **For agentic workers:** 执行时使用 superpowers:executing-plans 按任务推进；不默认委派。用户或适用指令明确要求委派时才使用 superpowers:subagent-driven-development。复用项目测试约束，不机械新增测试或自动提交。

**Goal:** 填写、结果和管理台围绕同一份后端问卷定义工作，移除结果生产链路的静态题库依赖，补齐 code 维护。

**Architecture:** 沿用角色模块的共享请求、分应用状态和内存复用方式。作答关联用 id，统计/DSL/链接用 code；现有结构与统计接口继续使用。

**Tech Stack:** 现有 Vue 3、TypeScript、fetch/Apollo、Python >=3.12、FastAPI、SQLAlchemy、pytest、node:test/tsx；无新增依赖。

**Spec:** [已确认方向与具体设计建议](../specs/2026-11-09-questionnaire-backend-source-design.md)。状态：用户已授权执行，2026-11-09 本地实现与验证完成，未提交或部署。

## Global Constraints

- 后端路径以 `thvote-be-re/` 为根；下文 FE 指 `/data/sunyunbo/www/Touhou-Vote/`，BE 指 `/data/sunyunbo/www/Thvote-be/thvote-be-re/`。
- 复用已有结构和统计接口，不新增公开查询、DB 表字段、迁移、依赖或 CI。
- 答案和 related/mutex 继续用真实 id；code 用于结果查询、DSL 和链接，不自动生成或回填。
- 填写规则、草稿 key/答案形状、跳题解析器、提交与回填协议沿用当前行为。
- 结构只在本次应用运行中复用；刷新重新拉取。个人 localStorage 草稿不当作题库，也不随结构缓存清理删除。
- 特殊图表、代理题和门禁差异有明确范围边界，不能顺手增加展示配置、状态机或跨届版本系统。
- 保留用户未提交改动；不 commit、push、部署、导入真实题库或重算结果。执行前按 using-git-worktrees 确认隔离位置与基线，避免遗漏用户依赖的改动。
- 验证按完整改动集中执行；新增测试仅覆盖真实关键行为。页面最多截图，不自动点击或填表。

## Review Focus

1. 新建题目 id=100、code=11011 这类不相关的标识，仍能查询和解释正确结果；Task 1/4 覆盖。
2. 异步结构尚未就绪、请求失败后重试，不应以空清单或旧表冒充加载成功；Task 3/4 覆盖。
3. 已计票但没有回答的题和零票选项正常显示；未计票错误继续可辨识；Task 4 覆盖。
4. code 为空、重复或格式错误，管理页、批量导入和筛选器表现一致；Task 2/4 覆盖。
5. 相同应用多处使用时复用请求，刷新后重新请求；草稿与当前筛选人群不被改动；Task 3/4 检查。无需为所有页面复制相同测试。

## Task 1：共享请求、类型与结果索引

**Files:** FE `packages/shared/api/questionnaire.ts`（新建）；`packages/shared/data/questionnaireV2.ts`（修改）；`packages/shared/api/__tests__/questionnaire.test.ts`（小型行为测试）。

**Interfaces:**
- `fetchQuestionnaireStructure(url: string, init?: RequestInit): Promise<QuestionnaireStructureResponse>`：共享 fetch 和最小结构检查，错误向调用方抛出。
- `buildQuestionnaireIndex(structure: QuestionnaireStructureResponse): QuestionnaireIndex`：纯函数；输出 `questions`（全部题目，保留所属 questionnaire/group）、`questionByCode`、`optionByCode`、`questionnaireByKey`。Map 的 code key 为无 q 前缀字符串；空 code 不加入 code map，不用 id 替代；同一题/选项 code 重复时报清晰的定义错误，避免误合并。
- `QuestionnaireQuestionV2/QuestionnaireOptionV2` 增加 `code?: string | null`、`order?: number`，兼容旧草稿和既有夹具；无正式题目内容。

- [x] 写简短测试，调用真实索引函数：id 与 code 不相等时正确关联；非固定八槽位的问卷可找到；缺 code 不冒用 id；重复 code 报错。一个 HTTP 错误用例检查请求函数拒绝失败响应。
- [x] 实现上述接口，遵循 shared/api/voteObjects.ts；基本结构检查只为后续 map/遍历提供所需形状，不另建 schema 框架。
- [x] 运行 `pnpm exec tsx --test packages/shared/api/__tests__/questionnaire.test.ts`，预期全部通过；不测试源码字符串或 mock 内部调用顺序。

## Task 2：管理台 code 编辑及后端直接校验

**Files:** BE `admin-ui/src/api/types.ts`、`admin-ui/src/views/QuestionnaireView.vue`；`src/apps/questionnaire/admin_service.py`、`admin_dao.py`、`admin_router.py`、`service.py`、`dao.py`；按需新增小型 `code_validation.py`；复用 `tests/integration/test_questionnaire_admin.py`、`test_questionnaire_code.py`。

**Interfaces:** 保留现有创建/更新/导入接口和返回形状。建议明确错误 `422 INVALID_QUESTIONNAIRE_CODE`（非空长度/字符错误）、`409 QUESTIONNAIRE_CODE_CONFLICT`（同类 code 重复），管理台沿用已有错误展示。

- [x] 补齐题目、选项类型中的 code；新建/编辑/保存/回显携带字符串或 null，界面明确 id 只读、code 可编辑以及空 code 无统计的影响。
- [x] 后端统一去除 code 首尾空白、空值归一 null；非空题码 5 位 ASCII 数字、选项码 7 位。未传 code 的局部更新不得清空已有值。
- [x] DAO 增加同表 code 存在查询，更新排除自身。写入前在 service 校验；不把查询放进路由，不改变父子关联 ID。
- [x] 整树导入在任何删除前校验树内非空 code 格式与重复；导入是全量替换，不与即将被替换的原树做冲突判断。所有可用导入入口复用校验，不为未使用 importer 路径假造接线。
- [x] 在现有集成夹具中覆盖 create/update→公开结构回显、格式错误、重复拒绝、同值更新、缺省/null 兼容；一个导入失败用例断言原树仍存在。尽量复用同层现有用例，不在多个层复制场景。
- [x] 记录非唯一 DB 索引保持现状，应用校验不承诺并发唯一性；不附加并发锁或自动清理。

**验收：** 新建题目可从管理表单保存 code 并被结构接口返回；非法编码显示可理解错误，原数据没有被无效导入删除。

## Task 3：填写端沿用角色加载生命周期

**Files:** FE `packages/vote/src/questionnaire/lib/questionnaireStateV2.ts`、`packages/vote/src/home/components/UserQuestionnaire.vue`、`UserQuestionnaireDp.vue`、`packages/vote/src/home/lib/questionnaireNameById.ts`；必要时局部调整 `Questionnaire.vue` 错误/重试呈现。消费入口核对 `home/lib/user.ts` 和 `main/main.ts`，不重做守卫。

**Interfaces:** 保留 `questionnaires`、`structureLoading/structureError`、`structureReady`、`loadQuestionnaireStructure(force = false)` 以及草稿/提交导出名称，减少调用方变更。

- [x] 将直接 fetch 替换为 Task 1 请求函数，继续传 `${API_PREFIX}/questionnaire/structure`。
- [x] 去掉 sessionStorage 读取/写入作为结构来源；成功状态在内存复用，合并进行中请求，首次失败后手动重试可重新请求。旧键只做移除，不清用户答案。
- [x] 成功加载后继续 ensureAnswerState/归一化；输入、跳题、buildAnswerStatePayload、restorePaperV2、localStorage key 保持现有契约。
- [x] 首页名称和说明直接使用后端 title/introduction，按 key 图片装饰暂保留；未知 key 使用默认图或现有无图布局，不恢复静态题干内容。
- [x] 添加一组小型加载行为测试（`questionnaire/lib/__tests__/questionnaireStateV2.test.ts`），按现有 tsx/node:test 方式提供最小浏览器存储与 fetch stub：同次成功复用、失败后重试、预置过时 sessionStorage 仍拉后端且保留 localStorage 草稿。先确认当前 alias 能按现有 tsconfig 解析，不安装测试框架。
- [x] 命令：`pnpm exec tsx --tsconfig packages/vote/tsconfig.json --test packages/vote/src/questionnaire/lib/__tests__/questionnaireStateV2.test.ts`。只为这些真实加载性质补测试，不扩展成浏览器流程。

## Task 4：结果端全部题库消费者接后端

**Files:** FE `packages/result/src/lib/Questionnaire.ts`、`components/Questionnaire.vue`、`components/AdvancedSearch.vue`、`pages/QuestionnaireInputDetail.vue`；`pages/QuestionnaireDetail.vue` 仅处理加载/空趋势，保留代理题选择。小型测试 `packages/result/src/lib/__tests__/Questionnaire.test.ts`。

**Interfaces:**
- `ensureQuestionnaireStructure(): Promise<QuestionnaireIndex>`：仿照 voteObjectResources.ts，成功复用内存，合并进行中请求，失败解除进行中引用以支持手动重试。URL 为 `/res-be/api/v1/questionnaire/structure`。
- 以响应式 loaded/loading/error 状态通知 Vue 消费者；`allQuestionnaireIDList` 从已加载且有 code 的题目产生 `q<code>`，getter 不再解析固定槽位或读旧表。
- 查找函数明确返回题目或 null；统计返回未知 code 时忽略该未知项并显示当前定义，不能回退旧题库解释。已有压缩 URL/DSL 继续保存 code。

- [x] 重写 lib/Questionnaire.ts 的数据来源，复用 Task 1 索引。测试直接调用加载器与查找接口，用 id≠code、非固定问卷 key 的响应确认真实来源和请求复用/失败重试。
- [x] 通用 Questionnaire 先等结构就绪再 queryQuestionnaire；完成率及标题共用同一响应，删除组件独立 fetch 标题的重复加载。GraphQL 选择集补取现有 rate/total 字段，避免读取未请求字段；不改变 schema。
- [x] 以定义题目为基础关联统计：已计票的缺项补零，选项按后端定义排列；题目按 code 数值升序。无 code 题显示简短未配置统计提示，不以空 query 查询它。
- [x] 保留现有特殊图表 code 绑定；空结果不会访问 entries[0] 或趋势 [0] 的不存在字段。文本详情的题名查后端定义，未知 qid 显示未找到，合法题无回答显示空列表。
- [x] AdvancedSearch 选择器只读取后端定义的 Single/Multiple 题及有 code 的选项；checkQuestionAvailable 使用可查询选项判断，继续保留原单选/多选过滤交互。旧已分享条件按原 code 发送，不自动改写。帮助文字保留 DSL 语法，去掉静态题库 Github 链接，可展示本次加载的编号和内容。
- [x] 核对 `QuestionnaireDetail.vue`、角色/音乐/组合详情的既有人群 query 和 URL 传递，沿用 AND 目标约束；不把加载结构时的空状态覆写成空筛选条件。
- [x] 在前述 node 测试/Task 1 索引测试中用真实生产转换逻辑覆盖缺统计补零、缺 code/重复 code、code 查文字；组件的空 entries、筛选传递做定向自查与构建，不为每个页面搭建重复 mock 测试层。
- [x] 命令：`pnpm exec tsx --test packages/result/src/lib/__tests__/Questionnaire.test.ts`；`rg -n 'shared/data/questionnaire|IDToBigQuestionnaire|IDToSmallQuestionnaire' packages/result/src` 应无运行时旧题库引用。旧表在其他历史/测试入口仍有使用时保留，不按文件名直接删除。

## Task 5：文档、集中验证与交付

**Files:** BE `docs/api/voteable-api-contract.md`、`docs/architecture/backend-overview.md`、`docs/BACKLOG.md`、`docs/CHANGELOG.md`、审查记录；FE `doc/ai-generated/questionnaire-v2-notes.md`、`result-dev-notes.md`、`docs/CHANGELOG.md`。

- [x] 文档写实际结构、id/code 分工、编码校验错误、前端内存生命周期与后端结构缓存/计票快照区别；更新 ORM 顶部和趋势 resolver 的过时说明（仅注释）。不要声称所有展示规则或历史题库版本均已后端化。
- [x] BE 运行：`python -m pytest tests/unit/test_questionnaire_completion.py tests/unit/test_questionnaire_answer_validation.py tests/unit/test_questionnaire_assembler.py tests/unit/test_questionnaire_importer.py tests/integration/test_questionnaire_admin.py tests/integration/test_questionnaire_code.py tests/integration/test_questionnaire_feed.py tests/integration/test_result_compat_ranking.py tests/integration/test_result_compat_advanced_search.py -q`；仅新失败或新改动触发追加检查，不自动全量回归。
- [x] BE 对改动 Python 文件运行 `python -m flake8 <实际改动文件>`；管理台运行 `npm --prefix admin-ui run build`，包含 vue-tsc 与 Vite。
- [x] FE 三组小型行为测试集中执行一次；运行 `pnpm vote:build`、`pnpm result:build`。这两个命令主要验证打包，不作为完整类型或交互验收；构建若触发现有 codegen，先核对其是否访问外部 schema，不因失败覆盖用户已有脚本改动。
- [x] 两仓库运行 `git diff --check`、定向 diff 自查。需要页面验证时最多截图，报告未进行真实账号提交、回填及线上统计验收。
- [x] 每项交付完成后再勾选，并把缺口状态更新为“本地已实现/已验证”；未完成的特殊绑定、门禁、监控、跨届定义继续留待办。

## 交付边界与顺序

Task 1 提供共享契约；Task 2 与 Task 3 可分别完成，Task 4 依赖 Task 1，Task 5 集中收口。默认同一执行者顺序处理，不默认启用并行 agent。

代码配套版本需要管理维护好 code 后，结果页才能查询相应题目；已有 code 不变的旧链接继续有效。没有 DB 迁移，不自动执行真实题库编辑或计票。若以后发布，先核对定义/code，再发布配套前端；code 改动所需重算单独授权。

回滚：回滚本轮配套产品代码；人工改过的定义/code 需人工核对恢复。用户现有无关改动始终保留。不得根据计划中的步骤自动执行 commit、push、部署或清理数据。

## 实际验证记录（2026-11-09）

- 本计划 Task 5 所列后端 pytest 命令：68 passed，2 条已有弃用警告；新增用例覆盖管理写入/回显和无效导入不删除原树。
- `pnpm exec tsx --tsconfig packages/vote/tsconfig.json --test packages/shared/api/__tests__/questionnaire.test.ts packages/vote/src/questionnaire/lib/__tests__/questionnaireStateV2.test.ts packages/result/src/lib/__tests__/Questionnaire.test.ts`：5 passed。填写端测试用例确认旧 session 缓存不阻止请求、失败可重试且草稿保留。
- `pnpm vote:build`、`pnpm result:build`、`npm --prefix admin-ui run build` 通过；后者包含 vue-tsc。修改 Python 文件 flake8、两仓库 git diff --check 通过。前端 Vite 构建不代替全量类型或真实交互验证。
- 独立只读审阅未发现重要缺陷；审阅指出的零回答多选雷达图 0/0 在问卷层增加空状态处理，随后复查结果构建。
- 实施偏差：为保留双仓库已有依赖性未提交改动，在当前非主分支原位局部实现，未创建新 worktree。测试命令补传现有 tsconfig 以解析 alias。未引入新框架、并发机制或永久浏览器测试。
- 未运行浏览器交互、真实账号提交回填或线上数据库/统计验收；未回填、重算、发布、部署、commit 或 push。
