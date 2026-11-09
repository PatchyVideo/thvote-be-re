# 问卷答案合法性与完成度实施计划

> **For agentic workers:** 使用 superpowers:executing-plans 在当前会话按任务执行；不默认委派。项目约定优先：不机械新增测试、全量验证、自动提交或发布。

**Goal:** 后端读取真实定义后校验题型、互斥、分支，并用同一份规则结果判断完成度；合法未完成可保存，非法答案拒绝。

**Architecture:** 沿用 StructureIndex、validation、completion、service，新增小型纯规则模块 rules.py。复用索引和单次规则评估，保持 GraphQL 成功返回和现有作答错误契约。

**Tech Stack:** 现有 Python >=3.12、FastAPI/Strawberry、SQLAlchemy、pytest；仅临时对照前端 TypeScript 解析器，无新增依赖。

**Spec:** [作答规则设计](../specs/2026-11-09-questionnaire-answer-rules-design.md)。状态：用户已授权实施，2026-11-09 本地实现与相关验证完成，未推送或部署；后端基线 f12e3ce，前端基线 4fda4ef。

> 历史阶段说明：本计划已完成，下文“不改 required 产品规则”是当时的范围约束。后续整体条件已改为全部必填＋至少一份 extra 选填，当前状态见[架构总览](../../architecture/backend-overview.md#问卷整体完成闸门与配置入口)。

## Global Constraints

- 命令和 BE 路径均相对 thvote-be-re；FE 为 `/data/sunyunbo/www/Touhou-Vote`。
- 业务判断以后台定义和真实 id 为准，一次加载四层，字典/集合查找；不逐题查库，不以 code 计算层级。
- 维持全量答案快照、合法未完成保存、append-only 批次和最新批次读取；不能自动修正用户答案后保存。
- 不改 required 产品规则、旧 raw_paper 门禁、作废、编码、跨届定义版本和题目回答/趋势统计算法。
- 不新增独立预校验接口、GraphQL 完成字段、DB 迁移/新表、缓存层、恢复状态机、依赖或 CI。
- 保留历史孤立组忽略、空配置门禁兜底，以及统计排除空配置的既有边界；不回填或清理历史答案。
- 当前 feat/questionnaire-backend-source 存在其他任务未提交改动，执行前检查隔离方式和实际 diff；保留无关文件，不操作合作者分支。
- 未经后续明确要求不自动提交/推送/部署/重算；本计划编写不执行产品代码修改。
- 运行相关已有检查，新永久测试只覆盖关键行为；不浏览器自动点击或填表。

## Review Focus

1. 全量快照包含其他未答问卷、空隐藏行，不能被“至少一项”一概拒绝；Task 1/3。
2. 隐藏题组自触发、错误分支、链式触发必须由可见来源决定；Task 1。
3. 多触发同组、单向 mutex、分支切换后的旧答案不能被静默修正保存；Task 1/3。
4. 旧存量非法或孤立答案不导致计票批次崩溃，空配置兼容不得扩大到新非法提交；Task 2。
5. 请求/统计不重复建索引或按题查库；复用预读答案不把空列表当未传；Task 3/4。

## Task 1：纯规则评估与严格提交校验

**Files:** 新增 `src/apps/questionnaire/rules.py`；修改 `structure_index.py`、`validation.py`；扩展 `tests/unit/test_questionnaire_answer_validation.py`，必要的分支场景放小型 `tests/unit/test_questionnaire_rules.py`，避免重复覆盖同一故障。

**Interfaces:**
- rules 定义内部 `AnswerIssue(code, questionnaire_id, group_id, question_id, message)`，可空定位字段；`RuleEvaluation` 含可见组、允许当前题映射、合法已答组、非法问卷集合、首个错误及配置错误信息。
- `evaluate_rules(index: StructureIndex, rows_by_group: dict[tuple[int, int], dict]) -> RuleEvaluation` 只计算规则；依赖 index，不反向导入 validation/completion/service。
- `assess_answers(index: StructureIndex, rows: list[dict]) -> RuleEvaluation` 放 validation，先检查引用和行形状再调规则。逐问卷记录是否非法，便于完成率读取不因单人旧数据退出。
- `validate_answer_rows(structure: dict, rows: list[dict]) -> None` 保留兼容包装；内部构建 index 并按 assessment 首错抛现有 ValidationError。service 可直接复用已建索引的 assess，避免再次包装/建索引。
- is_done_row 的内容判断若迁入 rules，validation 保留必要重导出，不形成 rules→validation→rules 环。

- [x] 在现有真实夹具中补充失败用例：Single 两项、选择题夹文本、Input 夹选项、Multiple 跨 optionGroup、显式 mutex 同时命中。断言原始 rows 未被修改；空选项为合法未答，错误类型 false/0 不能被转成空数组。
- [x] 实现局部题型检查与索引复用，使用集合去重/查互斥；不在路由/DAO 中加入业务循环。保留现有 `maxInputLen` 与空文本契约。
- [x] 用一份小型分支定义覆盖默认题、非默认题被触发、隐藏未触发、链式触发及失效分支；伪造隐藏行自触发/相互触发不能变成合法回答。多个合法来源命中同组时当前题在集合内可保留。
- [x] 按设计实现有界推进，初始状态来源于后台定义；只用有效可见来源传播。题组 order 和数组稳定顺序沿用当前解析器，不按真实 id 数值推断前后。不收敛标记配置错误，不能返回完成。
- [x] 用临时脚本给同一份合法样本调用 FE `questionnaireV2Parser.ts` 与后端评估，对照默认/隐藏/多触发/互斥后的合法快照；不建立常驻跨语言测试框架。若样本暴露前端语义冲突，记录具体差异并先报告。
- [x] 运行 `python -m pytest tests/unit/test_questionnaire_answer_validation.py tests/unit/test_questionnaire_rules.py -q`（若无需独立 rules 测试文件，移除该路径）。预期关键错误被拒绝、合法未完成通过。永久测试只调用生产函数并断言结果，不验证源码字符串或镜像算法。

## Task 2：完成判断消费同一评估

**Files:** 修改 `src/apps/questionnaire/completion.py`、按需 `src/apps/result/compute_dao.py`；扩展 `tests/unit/test_questionnaire_completion.py` 和现有完成率集成覆盖所在的 `tests/integration/test_result_compute.py`。

**Interfaces:** `completed_from_evaluation(index: StructureIndex, evaluation: RuleEvaluation) -> set[int]` 不再计算分支。保留 `completed_questionnaire_ids(index, answers)`、`is_complete(structure, answers)`，在兼容包装中调用同一 assessment。

- [x] 将 completion 当前 `_visible_group_ids` 的独立传播替换为 Task 1 结果。一个已配置问卷有至少一个可见组、可见组均合法已答且本卷无规则错误才计完成。
- [x] 保留未知/已删除组孤立行的历史忽略行为；这只用于 stored completion 包装，新提交仍严格拒绝。空配置门禁 row-coverage 及无 required 的既有纯函数行为保持，不能借新 rules 消除这些兼容策略。
- [x] 单元层验证单选多项、互斥/错误分支不计该卷完成；合法可选卷和必填卷分别统计，不把一份可选卷错误变成其他合法卷错误。已有“未知组被忽略”有效断言保留。
- [x] 结果批处理沿用外层一次 index 和按人最新批次；个人非法作答使对应问卷不计完成，不能异常退出整批。保持统计排除未配置问卷，以及题目回答计数、全局人群分母和趋势算法原状。
- [x] 集成层只补一个混合人群场景（合法与非法历史作答、另一份合法问卷），断言完成集合/完成率，不复制全部 unit 场景。
- [x] 运行 `python -m pytest tests/unit/test_questionnaire_completion.py tests/integration/test_result_compute.py tests/integration/test_questionnaire_feed.py -q`。如真实夹具受新关键语义影响，修正其合法作答前提并保留业务断言；不放宽预期掩盖失败。

## Task 3：服务编排、错误兼容与重复查询清理

**Files:** 修改 `src/apps/questionnaire/service.py`、`src/apps/submit/service.py`；按需 `src/api/graphql/errors.py`；保持 `resolvers/questionnaire_v2.py` 的公开返回类型。复用 `tests/integration/test_paper_v2_validation.py`、`test_questionnaire_domain.py`、`test_security_submit.py`。

**Interfaces:**
- `submit_answers(...)->int` 与 `submitPaperV2:Boolean` 保持；内部 flatten→加载定义→单次 index/assessment→非法抛错或保存，评估结果可直接供 completion 使用，不存新的完成字段。
- `QuestionnaireService.is_complete(vote_id, vote_year, *, answers: list[dict] | None = None) -> bool` 接受可选预读答案，仅在 is None 时读库，不能把 [] 当作未传。

- [x] 修正 flatten 对选项错误类型的真假值掩盖，只保留约定的缺省/None 空状态；调用 Task 1 的 assessment。用户错误仍为 INVALID_PAPER_ANSWER，中文信息含问题/题组位置和具体原因，不回显输入文本或凭证。
- [x] 配置不收敛返回 QUESTIONNAIRE_CONFIGURATION_ERROR，并提供安全中文文案；没有新字段，也不把其错误伪装为成功或用户选错。
- [x] 保持非法请求在 DAO replace_answers 前终止。一个集成用例先保存合法批次，再提交单选多项，断言没有新增行/attempt 且旧答案不变；一个合法部分回答快照保存成功但未完成。复用已有 GraphQL 夹具验证原错误契约，避免同场景跨层重复铺开。
- [x] `_require_questionnaire` 保留 legacy 分支和 `not answers` 判定；把已经读取的 answers 传给 qsvc.is_complete，避免第二次读取。无需修改 RawPaperSubmit/旧接口权限。
- [x] 运行 `python -m pytest tests/integration/test_paper_v2_validation.py tests/integration/test_questionnaire_domain.py tests/integration/test_security_submit.py -q`；预期现有鉴权、空批次、追加批次和合法门禁行为保留。

## Task 4：性能取样、文档与集中验收

**Files:** `docs/api/voteable-api-contract.md`、`docs/api/result-statistics.md`、`docs/architecture/backend-overview.md`、`docs/BACKLOG.md`、`docs/CHANGELOG.md`、`docs/migration/questionnaire-audit-2026-11-09.md`。本任务的临时脚本放 `.superpowers/` 下，不散落业务根目录。

- [x] 写清合法与完成的区别、现有 bool/错误契约、配置错误、分支/互斥语义、历史兼容和非法历史答案不计对应卷完成的影响。标记作答规则本地完成，其他门禁产品/legacy/监控/跨届项继续待办。
- [x] 临时合成 100、1000 个组的题库与合法答案（用多个问卷保持需求编码容量无关），分别测 index 构建、单次合法/完成评估耗时与迭代轮数。只报告机器/样本/结果，不保证生产延迟，不新增性能阈值或 CI。
- [x] 用本地测试 DB 的 SQLAlchemy 事件临时计数一次 V2 提交和一次结构化门禁查询，确认没有逐题 SQL、预读答案不重复查询。该观察不新增永久 mock 调用顺序测试，不连接云端。
- [x] 集中执行前三任务的实际测试文件一次，以及 `tests/integration/test_result_compat_advanced_search.py`，覆盖完成率复用后的筛选路径；只因新失败/具体风险扩大检查。
- [x] 对实际改动 Python 文件运行 `python -m flake8 <files>`、`git diff --check`。无前端代码变化时不重建整站、不执行浏览器流程。
- [x] 自查模块依赖和异常边界：rules 无 IO、校验与完成单一语义、未修改输入、非法不入库、无新增 DB/缓存/接口。记录真实命令和未验证项，再更新计划状态；不声称已验收线上题库或统计。

## 交付与回滚

默认在现有后端功能分支按上述顺序实施，无前端功能改动、无线上操作。新写入会拒绝此前仅靠前端限制的非法答案；已有合法页面输出应保持可提交。仍需人工决定何时部署、是否对历史完成率重算，计划不构成这些操作授权。

回滚本轮代码恢复旧校验与完成判断，不需要 schema 迁移；期间写入的合法答案仍在原表，历史非法数据未被清除。未自动清理、补写任何真实记录。

## 实际交付与验证（2026-11-09）

实现：新增 rules.py；validation 提供 assess_answers/require_valid 并保留入口；completion 改读同一评估；service 单次索引/校验后保存，门禁传入预读答案。未改前端、DB、缓存或公开字段。

最终相关检查命令：

```bash
python -m pytest tests/unit/test_questionnaire_completion.py tests/unit/test_questionnaire_answer_validation.py tests/unit/test_questionnaire_rules.py tests/integration/test_paper_v2_validation.py tests/integration/test_questionnaire_domain.py tests/integration/test_security_submit.py tests/integration/test_result_compute.py tests/integration/test_questionnaire_feed.py tests/integration/test_result_compat_advanced_search.py -q
python -m flake8 src/apps/questionnaire/rules.py src/apps/questionnaire/validation.py src/apps/questionnaire/completion.py src/apps/questionnaire/structure_index.py src/apps/questionnaire/service.py src/apps/submit/service.py src/api/graphql/errors.py
git diff --check
```

结果：pytest 99 passed（14.27s，2 条已有弃用警告），flake8/diff 检查通过。新增测试先复现旧实现未拒绝单选/互斥/错误分支、false选项被转空，以及旧空配置完成兜底回归，再验证修复。未新增浏览器或性能 CI。

前后端临时对照：同一份定义分别用 FE normalizeQuestionnaireDraftV2/parseQuestionnaireRuntimeV2 及 BE assess_answers/completed_from_evaluation，默认、链式、多触发和互斥清理后4份合法快照均被后端接受，可见组/完成结果一致。脚本在本计划 .superpowers 临时目录，不提交。

本机 Python 3.13.2 临时 CPU 取样，5次中位数，每份问卷100组连续隐藏触发：

| 总组数 | 索引构建 | 规则评估 | 从评估求完成集合 | 实际轮数 |
|---|---|---|---|---|
| 100 | 0.079ms | 7.086ms | 0.020ms | 100 |
| 1000（10份问卷） | 1.524ms | 143.271ms | 0.447ms | 每份100 |

这是合成长链计算，不含网络/数据库延迟，不作为线上承诺；当前需求规模和真实关联深度未核验。未因此添加新缓存或第二套算法。

本地 SQLite SQLAlchemy事件计数：V2提交5次SELECT（四层定义各一次＋最大attempt一次）；结构化门禁6次SELECT（legacy检查、paper_answer各一次＋四层定义各一次）。组数100也没有逐题查询，门禁答案读取只有一次。使用内存测试库，无云端读写。

独立只读审阅发现空配置问卷的旧题目ID会阻断历史行覆盖兜底；已仅在 stored completion 包装中恢复已知组行覆盖并去重，添加失败→通过用例，新提交同样载荷仍拒绝。之后重跑上述相关检查；无未处理的重要审阅项。

实施说明：为保留当前功能分支里的既有未提交工作，原位局部修改，未切换工作区。没有浏览器交互、真实账号或云端题库核验；未清理旧答案、重算结果、推送或部署。legacy门禁、required产品条件、监控/作废、跨届题库和完整后台配置治理继续独立待办。

用户追加审阅（2026-11-09）：按要求由 gpt-6.1-sol 子代理执行一轮只读审阅，未发现需要修复的具体问题；未对既有规则扩展范围。随后按原范围复查测试/静态检查，并将本阶段代码和文档整理为一个后端提交；不包含其他角色资料、记忆或前端草稿任务改动，不推送。
