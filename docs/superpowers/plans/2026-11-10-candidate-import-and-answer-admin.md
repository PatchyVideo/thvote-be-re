# 候选导入与新版答卷管理实施计划

> **For agentic workers:** 使用 superpowers:executing-plans，在当前 feat 分支连续实施；用户已确认方案并要求直接执行，不再重复请求计划批准。

**Goal:** 修正候选导入并提供新版答卷的查看、历史批次、整批作废和恢复。

**Architecture:** 保留现有 FastAPI、SQLAlchemy 和 Vue 管理台。候选解析在纯函数中，引用查询与写入通过 DAO；答卷管理按 router/schema/service/DAO 分层，复用现有题库和完成度逻辑。作废字段保存在 paper_answer，同批统一更新。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy、Alembic、Vue 3、TypeScript，无新增依赖。

**Spec:** [已确认设计](../specs/2026-11-10-candidate-import-and-answer-admin-design.md)。

## Global Constraints

- 保留当前未提交文档和用户改动；不提交、推送、部署或执行云端迁移。
- 本次仅生成新增字段的迁移文件；旧 raw_paper 物理删表及其他退出任务保留后续处理。
- 有错误的候选导入整批不写入；修改导入条件后必须重新预览。
- 最新答卷作废不回退；保留原始答案供回填，投票资格与统计排除作废数据。
- 不自动作废其他类别的票，不新增采集字段、队列或自动计票机制。
- 只为关键新行为和具体缺口补测试，不做浏览器自动交互验证。

## Review Focus

- 预览后修改输入或届次不能沿用旧报告确认；确认仍须后端重新校验。
- 同一对象重复、对象不存在、排序不合法时不能部分写入；缺省排序保留已有值。
- 筛选有效/作废必须发生在选择最新批次之后，不能返回旧有效批次冒充当前答案。
- 最新作废须同时影响完成门禁、普通计算和高级筛选；历史批次作废不改变最新选择。
- 题库引用已不存在时仍可查看原始 ID；未采集的设备和 IP 不得当作异常信号。

### Task 1: 候选导入后端与页面

**Files:** 修改 `src/apps/admin/candidate_service.py`、`service.py`、`schemas.py`、`router.py`，`src/apps/result/compute_dao.py`；`admin-ui/src/views/CandidatesView.vue`、`api/types.ts`。

**Interfaces:** 保留现有导入请求与端点；响应保留 valid/rejected/imported，扩展每行名称、作品、排序、action 与 create/update/unchanged 数量。候选列表新增 voteable_id、sort_order。服务端配置通过现有 stats 获取当前届次。

- [x] 在已有候选导入单元/集成用例中覆盖整数、重复、缺失引用、整批拒绝、真实名称预览及排序保留。
- [x] 修正解析、校验和引用查询；有错误不写，确认重复执行校验，直接按唯一引用关系 upsert，移除无效自动合并调用。
- [x] 页面提供文件读取、示例、正确预览和独立目标，清除过期报告；修正列表编辑回填并移除合并入口。
- [x] 运行 `python -m pytest tests/unit/test_candidate_import.py tests/integration/test_candidate_admin.py -q`，预期通过。

### Task 2: 答卷作废字段与统一读取口径

**Files:** 修改 `src/db_model/questionnaire_def.py`、`src/apps/questionnaire/dao.py`、`service.py`、`src/apps/result/compute_dao.py`；新增 `alembic/versions/0023_paper_answer_invalidated.py`（先确认迁移头）；补现有 questionnaire 集成测试。

**Interfaces:** `latest_batch(rows)` 保持原始最新批次选择；新增 `effective_latest_batch(rows)`，最新任一行作废则返回空。`get_answers` 继续返回原始内容，增加 `get_answers(effective=True)` 供完成门禁使用；预载原始答案时检查作废字段。统计和高级筛选经同一 DAO 排除作废数据。

- [x] 确认 Alembic 迁移头，添加 `invalidated NOT NULL DEFAULT false`，无答案回填改写；迁移文档说明降级会丢失标记。
- [x] 针对真实数据库答案覆盖最新作废、恢复、历史作废、新提交、届次隔离；断言完成资格、当前统计及历史序列，不连带改变其他票。
- [x] 完成当前答案与历史统计排除；保留原始回填，排除最新作废账号的整段历史，最新有效时跳过作废历史批次。
- [x] 运行受影响的已有问卷规则、完成度、feed 和 domain 测试，预期通过。

### Task 3: 答卷管理接口与页面

**Files:** 新增 questionnaire 下 `submission_admin_dao.py`、`submission_admin_service.py`、`submission_admin_schemas.py`、`submission_admin_router.py`，在 `src/api/rest/v1/__init__.py` 注册；新增 `admin-ui/src/api/questionnaireSubmissions.ts`、`views/QuestionnaireSubmissionsView.vue`，修改路由、导航和账号详情入口；修改旧监控 DAO 去除 paper。

**Interfaces:** `GET /admin/questionnaire-submissions` 分页最新列表；`GET /admin/questionnaire-submissions/{vote_year}/{vote_id}` 全批次可读详情；`PATCH /admin/questionnaire-submissions/{vote_year}/{vote_id}/{attempt}` 设置 invalidated，attempt=0 表示原有 NULL 批。沿用 require_admin。

- [x] DAO 在数据库按账号、届次选择最新，再筛状态、排序、分页；详情读取历史，更新限定账号/届次/批次。
- [x] service 复用题库和完成规则，序列化题目/选项、原始 ID、输入及缺失引用提示，分开返回填写完成与资格。
- [x] 补关键接口集成测试：分页筛选、可读详情/孤立引用、整批更新、404、鉴权。
- [x] 实现列表/详情/批次切换/作废恢复及重新计票提示；账号页面链接答卷管理；通用监控不再读 raw_paper。
- [x] 运行新接口测试与相关既有监控测试，预期通过。

### Task 4: 集中验证、文档与复核

**Files:** 更新 `docs/BACKLOG.md`、`docs/CHANGELOG.md`、`docs/README.md`、问卷审查文档；新增接口与迁移现状文档。

- [x] 更新当前状态、接口、行为兼容性、迁移/回退限制及后续 raw_paper 工作。
- [x] 集中运行相关 Python 测试、改动模块静态检查、`pnpm --dir admin-ui build`、`git diff --check`。不运行无关全量流程。
- [x] 执行一次独立只读复核，处理核心正确性问题并仅重跑受影响检查。
- [x] 更新本计划勾选项和实际结果，实施阶段交付未提交改动；随后用户授权提交并准备PR，说明云端迁移及页面交互未执行。


## 执行记录（2026-11-10）

本轮按确认设计在当前 `feat/questionnaire-backend-source` 连续实施，基线为 `159d3c4`；保留原有未提交文档。目标远端同名 feat ref 不存在，未推送或修改远端。实施阶段未执行 commit、云端迁移、部署或真实业务写入；后续按用户授权准备提交及PR，云端操作仍未执行。

### 实际实现与局部调整

- 候选引用/排序严格校验并按整批写入，预览查询当前连接的数据库；文件读取和预览共用已有 busy 状态，读取开始即清除旧报告，避免二者重叠。没有新增请求队列或状态机。
- 新管理 API 注册在现有 REST v1 组合入口，而非直接修改 main。原始回填保留，`get_answers(effective=True)` 与预载答案的 invalidated 检查共同防止门禁绕过。
- 现有高级筛选缓存仍跟随结果 snapshot_version，在手动重新计票后切换版本；新计算直接使用已排除作废数据的 DAO，没有新增缓存恢复机制。
- 管理 stats 及账号详情 paper 状态切换 V2。提交人数包括有保存记录但未完成/作废的账号，与完成资格分开。
- 测试解释器使用 PATH 中的项目 Python 3.13（项目要求 >=3.12）；没有 `.venv`。未安装新依赖。

### 验证与证据

- 候选新增场景先复现失败，相关 `tests/unit/test_candidate_import.py` 和 `tests/integration/test_candidate_admin.py` 首轮修正后 **21 passed**。
- `python -m pytest tests/unit/test_questionnaire_completion.py tests/unit/test_questionnaire_answer_validation.py tests/integration/test_questionnaire_domain.py tests/integration/test_questionnaire_feed.py -q` → **55 passed**。
- `python -m pytest tests/integration/test_questionnaire_submissions.py tests/integration/test_admin_monitor.py -q` → **18 passed**；新接口用例在路由实现前均失败。
- 集中执行以下 16 份文件：`test_candidate_import`、`test_candidate_admin`、`test_candidate_whitelist`、contract `test_candidate_endpoints`/`test_admin_endpoints_ext`、`test_admin_routes_ext`、`test_questionnaire_completion`、`test_questionnaire_answer_validation`、`test_questionnaire_rules`、`test_questionnaire_domain`、`test_questionnaire_feed`、`test_questionnaire_submissions`、`test_admin_monitor`、`test_paper_v2_validation`、`test_net_delta_trend`、`test_advanced_search_service`：**155 passed，9 failed**，35.22 秒。
- 上述9项均来自旧白名单测试的 raw_paper 解锁准备。用 `git archive HEAD` 创建干净临时副本，单独运行 `test_known_character_id_accepted`，确认基线同样因 QUESTIONNAIRE_NOT_COMPLETED 失败。改为复用现有 V2 `seed_structure/answer` 准备，保留所有候选断言；`python -m pytest tests/integration/test_candidate_whitelist.py tests/integration/test_candidate_admin.py -q` → **17 passed**。没有通过放宽预期或恢复旧门禁来消除失败。
- 最后仅为换行规范调整新模块，重跑 `python -m pytest tests/integration/test_questionnaire_submissions.py -q` → **3 passed**。其余已通过项目未重复全量运行。
- `pnpm --dir admin-ui build` → TypeScript 与 Vite 均通过（93模块）。构建产物已更新到 `src/admin_ui`。
- 对全部修改的 Python 业务模块、新路由和0023迁移执行项目默认 `python -m flake8 ...` → 退出0；`git diff --check` → 退出0；`python -m alembic heads` → 单头0023。
- 临时 PostgreSQL 16：完整迁移至0022，写入本地示例原答案，0023升级→0022降级→0023升级；确认原答案保留、新字段默认false，并验证最新列表筛选和整批状态更新。临时数据库服务已停止；不是云端库。
- 独立只读复核发现一个文件读取/旧预览重叠问题，已用现有 busy 修正；其他核心候选/答卷路径未发现问题。复核未自行运行浏览器、测试或云端操作，采用主任务的上述实际验证结果。

仍未验证：浏览器页面交互、真实云端迁移、真实题库/账号答卷和部署后计票；不以构建与本地测试替代这些验收。此前 asyncio/strawberry 弃用警告保留，不在本轮扩展依赖升级。


## 后续提交与PR检查（用户另行授权）

- 用户随后要求检查整个分支、提交推送并准备PR合并，覆盖此前未提交的本轮功能与操作记录；原实施阶段不提交限制由本次授权更新。未授权执行云端迁移或部署。
- 当前仓库既有CI范围的全量本地检查：`python -m pytest tests/ -q` → 943 passed、1 failed、3 skipped（947项，119.35秒）。唯一失败为旧 `test_gate_structured` 只完成必填即期待放行，与当前至少一份extra规则冲突。
- 复用现有V2题库/答案修正上述测试准备，保留通过/拦截断言；`python -m pytest tests/integration/test_gate_structured.py -q` → 2 passed。
- `python -m flake8 src/ --max-line-length=88` → 通过。最终PR分支基于最新origin/main迁入问卷与资料管理提交，不重复带入已合并拼音历史，也不夹带独立PR#36的音乐快照修复。
- 合入main会触发既有测试环境自动发布及 `alembic upgrade head`。PR检查不会构建或部署；实际合并前需说明0023迁移影响及回退。
