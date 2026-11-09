# 问卷定义命令行检查实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. 用户已授权本轮先计划再直接实施，主 agent 执行。

**Goal:** 提供随时可运行、可用退出码作为发布前闸门的只读问卷检查脚本。

**Architecture:** 纯检查函数与数据库读取、命令入口同处 scripts/check_questionnaire.py，复用现有 code 格式规则与配置。不改后台保存流程，不新增业务模块。

**Tech Stack:** Python >=3.12、SQLAlchemy、argparse、dataclasses、现有 pytest/SQLite。

**Spec:** [已确认的脚本设计](../specs/2026-11-09-questionnaire-check-design.md)。

**Status:** 2026-11-09 实现、检查及一次独立只读审阅完成；审阅发现的配置日志输出问题已修复，后端已提交97e8fb4。未推送、部署或运行真实库检查。

## Global Constraints

- 不新增接口、发布状态、数据库字段、依赖或CI工作流，不自动修复数据，也不阻止后台逐项编辑过程中的中间状态。
- related 严格指向后续题组，按 order 比较，不能按 ID 或 code 推断；mutex 不能指向自身，允许单向声明。
- 缺失 code 仅警告，不提高现有编码要求。
- 实现和文档完成后不自动提交、推送或部署。
- 延续用户指定 feat/questionnaire-backend-source 检出；保留无关 CHANGELOG/README 改动及未跟踪资料，验证不读真实库。

## Review Focus

- 普通加载器过滤的孤立行也必须被发现。
- 多个错误一次报告，不能首错即退出。
- 单向 mutex 和不同 option_group 不能误报；related 判断使用 order。
- 警告仍退出0，定义错误退出1，无法完成检查退出2；不能误放行。
- 数据库检查只读，错误输出不带敏感连接内容。

### Task 1：实现单文件脚本与行为覆盖

**Files:** Create `scripts/check_questionnaire.py`、`tests/integration/test_questionnaire_check.py`。

**Interfaces:** `check_definitions(questionnaires: list[dict], groups: list[dict], questions: list[dict], options: list[dict]) -> list[Issue]`；`load_definitions(session: AsyncSession) -> tuple[list[dict], list[dict], list[dict], list[dict]]`；`main(argv: list[str] | None = None) -> int`。Issue 包含 severity/code/kind/node_id/message。所有辅助函数都保留在同一脚本。

- [x] 在现有集成测试目录，用真实定义字典覆盖合法结构、错误集合、向后/跨问卷/无效引用及 code 警告；测试先运行，确认新脚本缺失导致失败。
- [x] 实现纯检查函数。先索引ID/父子关系，再检查单个节点和引用；不使用通用规则注册器、图求解或动态插件。
- [x] 实现四表完整读取及命令入口。命令只查询、不建表/写入；配置和查询失败返回2，错误输出脱敏。
- [x] 用临时SQLite运行真实脚本，覆盖退出0/1/2、缺失code不阻断和读取后数据不变；覆盖孤立记录，不 mock 核心检查函数。
- [x] 运行 `python -m pytest tests/integration/test_questionnaire_check.py tests/unit/test_questionnaire_completion.py tests/unit/test_questionnaire_rules.py tests/integration/test_questionnaire_code.py -q`；预期通过。
- [x] 运行 `python -m flake8 scripts/check_questionnaire.py tests/integration/test_questionnaire_check.py`、`python -m scripts.check_questionnaire --help` 和 `git diff --check`；不运行默认真实数据库检查。

### Task 2：记录使用方式与剩余边界

**Files:** Create `docs/operations/questionnaire-check.md`；Modify `docs/README.md`、`docs/CHANGELOG.md`、`docs/BACKLOG.md`、`docs/migration/questionnaire-audit-2026-11-09.md`、`docs/superpowers/plans/README.md`。

**Interfaces:** 运维文档消费任务1命令及退出码，明确手动/发布前调用同一命令；不宣称已经自动接入CI或后台保存校验。

- [x] 写出配置来源、命令、错误与警告示例、退出码和实际未覆盖范围，登记已实现独立检查、仍未接后台保存。
- [x] 更新索引与changelog，检查本地文档链接；独立只读审阅后，只修具体核心问题，记录验证证据和未验证真实库。

## 执行记录

- 新增单个脚本及一份测试文件；复用 normalize_code、数据库模型和应用配置。完整读取四张定义表，孤立父子记录不会在组装时被忽略；不修改现有 CRUD、作答/完成评估或缓存。
- 测试先因脚本缺失而失败。初次实现后29 passed、1项测试夹具定位断言失败：重复code报告第二条记录，已把重复值放到第二条记录，保持对实际错误ID的断言。
- 按任务1集中命令运行四份相关测试：58 passed，1项既有配置event-loop弃用警告。flake8、--help和diff检查通过。
- 独立只读审阅确认定义检查及只读路径，发现配置/Nacos加载器可能提前记录原始异常。新增调用真实main的回归用例先复现失败，再仅在脚本加载配置期间禁用内部日志并恢复先前级别；不改变应用配置回退语义。
- 修复后只重跑受影响文件：`python -m pytest tests/integration/test_questionnaire_check.py -q --tb=short` →31 passed，1项相同既有警告；`python -m flake8 scripts/check_questionnaire.py tests/integration/test_questionnaire_check.py`、`python -m scripts.check_questionnaire --help` 和 `git diff --check` 均通过。
- 命令测试使用临时SQLite，真实子进程覆盖合法/警告退出0、孤立行退出1、缺表/无效连接配置退出2，并核对检查前后数据库文件内容不变。配置失败输出回归不访问Nacos网络。
- [操作说明](../../operations/questionnaire-check.md)、文档索引、架构入口、BACKLOG和剩余清单同步；文档链接检查通过。未核验真实数据库、账号或部署，不新增CI、保存校验、额外业务模块或接口。
- 未实现全分支可达性/答案可满足性求解、并发编辑一致性机制或任意Python字典输入校验框架；这些不属于已确认的数据库检查脚本范围。无数据迁移或自动修复，删除脚本即可回退。
