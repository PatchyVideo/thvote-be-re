# 拼音候选搜索后端化实施计划

> 归档日期：2026-11-08。已执行或被后续方案取代；剩余实际事项以当前 BACKLOG 为准。
> 下文保留原设计／实施过程，仅调整相对链接；不要按旧步骤再次执行迁移、导入或部署。当前入口见 [文档索引](../../../README.md)。

> 状态：第一阶段已提交（后端 `77f43cf`、前端 `26f79df`），未发布或部署。本文保留该阶段的历史契约；当前接口以 [第二阶段收敛计划](2026-11-08-autocomplete-search-consolidation.md) 及设计/API 文档为准。
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans when implementing inline; use superpowers:subagent-driven-development only when the user chooses delegated execution. Steps use checkbox (`- [x]`) syntax. Project AGENTS.md and current user authorization take precedence.

**Goal:** 将角色、音乐与 CP 成员选择中的拼音搜索迁到 Python 后端，保留原文、简拼、混输和已配置的模糊音。

**Architecture:** 纯匹配器位于 `apps/autocomplete/pinyin.py`；候选用例负责 DAO 与 Redis；加法式 ID 搜索接口供前端三个选择入口使用。前端继续过滤个人已选项及作品类别，保持日期排序。派生语料与搜索结果首版只存 Redis。

**Tech Stack:** Python >=3.12、pypinyin==0.55.0、现有 FastAPI / SQLAlchemy / Redis；现有 Vue 3 / TypeScript / node:test / tsx。

**Spec:** [拼音候选搜索后端化设计](../../../superpowers/specs/2026-11-08-pinyin-candidate-search-design.md)。本文与设计一起阅读；本轮仅执行已确认范围。

## Global Constraints

- 只覆盖投票页角色、音乐和 CP 成员搜索；不扩展结果页、CP 组合推荐或管理端拼音编辑。
- 不改变旧 `/api/v1/autocomplete/search`；新增 `/api/v1/autocomplete/candidates/search`，返回全部匹配 candidate IDs。
- character 搜索 `name/aliases/work.name`；music 搜索 `name/aliases/work.name`；不跨字段匹配，不扩大到 `name_jp/include`。
- query 长度最多 64 个 Unicode 码点；规范化为 `strip().lower()`。年度按请求或 settings 明确解析。
- Redis 内部前缀 `autocomplete:pinyin:v1:`，语料和结果各 TTL 60 秒；不使用 `result:*`。
- 无数据库 schema、数据回填、进程级候选缓存、锁、等待队列、自动重试或恢复流程。
- 未获授权不 commit、push、发布、部署、重新计票或写真实数据库。不要把每段完成等同于提交授权。
- 保留两仓库无关改动；合作者分支只读。UI 验证最多截图，不自动点击或填表。
- 新测试只覆盖关键新增行为，复用现有 SQLite / fakeredis / node:test；本计划不要求全量测试或新端到端环境。

## Review Focus

以下五点分别归入相应任务的测试，不另建重复测试层：

1. 缩写或模糊音扩大匹配范围：`limi` 不应匹配“灵米”；Task 1。
2. 不同名称、别名和作品被拼接后误命中，以及不同年度 ID 混用；Task 2。
3. 空结果缓存、写后失效及 Redis 故障不能被当作业务零命中；Task 2。
4. 连续输入、清空或请求先后颠倒时旧结果覆盖新结果；Task 3。
5. 返回整数 ID 与前端字符串 ID、已选项排除、CP 可重复成员及日期排序；Task 4。

## 开始执行前（已完成）

确认设计中的模块位置、新接口和 Redis 存储方案。两端均使用 `feat/pinyin-backend-search`。前端原目录的未提交现场已归档和 stash，切换后保留尚未被上游包含的本地修改；原快照未删除。

查一次当前远端是否变化；若搜索相关实现出现新改动，先更新基线记录。不得借此自动发布或清理分支。依赖已经存在且无代码改动时，不为准备工作反复安装依赖或跑全量测试。

## Task 1：纯拼音准备与匹配

**Files:**
- Create: `src/apps/autocomplete/pinyin.py`
- Modify: `pyproject.toml`
- Create: `tests/unit/test_pinyin_matcher.py`

**Interfaces:**
- Consumes: 原始独立文本，以及由用例层规范化后的 query。
- Produces: `TextUnit`（原字、多个声母／韵母二元组）、`PreparedText = tuple[TextUnit, ...]`、`prepare_text(text: str) -> PreparedText`、`contains(text: PreparedText, query: str) -> bool`。

- [x] 在一个参数化用例中放设计 §4.4 的独立正反例，新增多音字不同读音、查询末尾未输完、单向规则不能反向扩大、英文标点原文的最小覆盖。不枚举所有读音组合。
- [x] 运行 `python -m pytest tests/unit/test_pinyin_matcher.py -q`，确认新增行为尚未实现。不要把依赖未安装造成的 import error 当作行为失败的充分证据。
- [x] 经已确认依赖路线添加 `pypinyin==0.55.0`。逐字获取无声调多读音，保留原文分支；按设计 §4 的字面声母／韵母拆分和非递归规则生成匹配选项。
- [x] 用记忆化查询位置匹配或等价二维 DP 实现 `contains`：从任意原文位置开始，消费连续原文字，可在各字原文／声母／完整读音间混合选择；只有查询结束时允许读音前缀未输完。不跳过原文字，不用正则解释 query。
- [x] 示例预期必须直接成立，不依赖旧库输出或复制生产算法：

```python
assert contains(prepare_text("雾雨魔理沙"), "mo理sha") is True
assert contains(prepare_text("二小姐"), "rxiaojie") is True
assert contains(prepare_text("路米"), "lvmi") is True
assert contains(prepare_text("灵米"), "limi") is False
assert contains(prepare_text("魔甲理沙"), "mls") is False
```

- [x] 再运行该测试文件。对关键样例有分歧时定位读音来源或匹配规则；不为消除分歧擅自修改产品预期。需要时在临时环境对照旧 Pinin，不能将 JS 加进生产或永久 Python 测试依赖。

**交付：** 可独立调用的纯匹配器；它不知候选、年度、数据库或 Redis。

## Task 2：候选 ID 接口、语料与结果缓存

**Files:**
- Create: `src/apps/autocomplete/candidate_search.py`
- Modify: `src/apps/autocomplete/dao.py`
- Modify: `src/apps/autocomplete/schemas.py`
- Modify: `src/apps/autocomplete/router.py`
- Modify only if an existing invalidation call is missing: `src/apps/admin/router.py`
- Extend: `tests/integration/test_autocomplete.py`
- Extend narrowly for HTTP contracts: `tests/integration/test_vote_objects.py`
- Read / reuse: `src/common/cache.py`, `tests/unit/test_cache.py`

**Interfaces:**
- Consumes: Task 1 的准备与匹配函数。
- Produces: `AutocompleteDAO.load_search_documents(self, category: Literal["character", "music"], vote_year: int) -> list[tuple[int, tuple[str, ...]]]`。
- Produces: `CandidateSearchRequest(category, query, vote_year=None)`、`CandidateSearchResponse(category, query, vote_year, candidate_ids)`，精确约束见设计 §5。
- Produces: `CandidateSearchService(dao, redis, default_year)` 与 `async search(request: CandidateSearchRequest) -> CandidateSearchResponse`；HTTP POST `/api/v1/autocomplete/candidates/search`。

- [x] 复用 `test_autocomplete.py` 的真实 SQLite session；加入新 DAO 和服务行为用例。使用现有 fakeredis 条件，不另建测试工程。
- [x] 用同一 voteable 的两个年度候选验证返回的是请求年度的 candidate ID；名称、别名、work.name 均可独立命中。让 query 只能跨两个字段拼接时不命中。
- [x] 一次增加 11 条可匹配候选，断言全部 11 个 ID 返回且无重复；覆盖空查询全部、未知年度空集合。这个用例专门避免旧默认 limit=10 被带入新接口。
- [x] 在真实 DAO + fakeredis 服务测试中验证：缓存命中、空结果命中、改变查询仍可复用派生语料，以及调用现有 autocomplete 前缀失效后能看到修改后的别名。不用“执行了某个内部函数”代替返回值断言。
- [x] Redis 故障使用一个明确抛连接异常的缓存替身，但 DAO 和匹配器保持真实；断言仍返回实际命中 ID。数据库失败须传播错误，不缓存成空集合。
- [x] 按设计 §6 实现两个 JSON 缓存；共享 namespace 不包含用户已选项，结果值只存完整 ID 列表。语料存原字及音节二元组，缓存版本为 `v1`，两层 TTL 都为 60 秒；复用现有 fail-open helpers。
- [x] 在 `test_vote_objects.py` 复用现有 app/engine/patch_redis，仅覆盖新 POST 路径、回显字段、非法 category、超长 query、默认年度和显式年度。原有算法／DAO 场景不复制到 HTTP 层。
- [x] 保留旧 service、schemas 与 `/search` 行为；不得通过修改旧接口配额来适配新前端。
- [x] 核对管理写入已有失效回调，必要时仅接入已有 helper。手动 `scope=autocomplete` 应同时移除新两类键，`result:*` 不受影响。
- [x] 在后端目录集中运行：

```bash
python -m pytest tests/unit/test_pinyin_matcher.py tests/unit/test_autocomplete_service.py tests/unit/test_cache.py tests/integration/test_autocomplete.py tests/integration/test_vote_objects.py -q
```

**交付：** 旧前端可继续使用；新接口可独立返回正确 ID。没有数据库迁移和发布动作。

## Task 3：前端请求函数与 Vue 搜索状态

**Files in Touhou-Vote:**
- Create: `packages/shared/api/candidateSearch.ts`
- Create: `packages/vote/src/common/lib/useCandidateSearch.ts`
- Create: `packages/vote/src/common/lib/__tests__/candidateSearch.test.ts`
- Create: `packages/vote/src/common/lib/__tests__/useCandidateSearch.test.ts`

**Interfaces:**
- Consumes: Task 2 的完整响应；URL 为 `${API_PREFIX}/api/v1/autocomplete/candidates/search`；当前 voteYear 显式传入请求。
- Produces: `fetchCandidateSearch(baseUrl, category, query, voteYear): Promise<CandidateSearchResult>`，类型定义见设计 §7。
- Produces: `useCandidateSearch(category: CandidateCategory, query: Ref<string>)`，返回 `matchedIds: Ref<Set<string>>`、`loading: Ref<boolean>`、`error: Ref<string | null>`。

- [x] 请求 helper 测试实际 JSON 请求／响应转换：整数 ID 转字符串在 Vue hook 内处理；HTTP 失败、回显类别／年度／query 不符或 ID 数组无效时抛出可展示错误。不重写全套 HTTP 验证框架。
- [x] 用 Vue `effectScope`、`ref`、`nextTick` 调用真实 hook，并用可手动 resolve 的 fetch Promise 模拟返回。覆盖 query A 后输入 B、B 先返回、A 后返回，以及输入后清空两种核心场景；断言只保留当前输入结果。无需浏览器或 DOM 工程。
- [x] 实现 hook：空查询不请求；非空查询清旧 ID 后请求；watch cleanup 使过期回调无效；成功设置 ID，当前失败设置 error。不要增加额外 debounce、重试、请求队列或历史查询缓存。
- [x] 运行前端现有工具：

```bash
./node_modules/.bin/tsx --test packages/vote/src/common/lib/__tests__/candidateSearch.test.ts packages/vote/src/common/lib/__tests__/useCandidateSearch.test.ts
```

**交付：** 可复用的前端异步搜索状态，尚不移除旧 Pinin。

## Task 4：三个入口切换、旧依赖清理与文档收尾

**Files in Touhou-Vote:**
- Modify: `packages/vote/src/vote-character/lib/characterList.ts`
- Modify: `packages/vote/src/vote-music/lib/musicList.ts`
- Modify: `packages/vote/src/vote-couple/components/CharacterSelect.vue`
- Modify: `packages/vote/src/vote-character/components/CharacterSelect.vue`
- Modify: `packages/vote/src/vote-music/components/MusicSelect.vue`
- Modify: `packages/vote/src/common/components/AutoComplete.vue`（仅补输入长度约束，保留节流）
- Modify: `packages/vote/src/common/lib/characterSearch.ts`（保留筛选与排序）
- Remove when no callers remain: `packages/vote/src/common/lib/pinin.ts`, `packages/vote/src/vote-music/lib/musicSearch.ts`
- Replace / remove obsolete cases: `packages/vote/src/vote-music/lib/__tests__/musicSearch.test.ts`
- Modify: `packages/vote/package.json`, `pnpm-lock.yaml`, `doc/ai-generated/vote-dev-notes.md`, `docs/CHANGELOG.md`

**Backend docs:** `docs/api/voteable-api-contract.md`, `docs/CHANGELOG.md`，以及本设计／计划状态。后端 API 文档原自动补全示例与实际格式有漂移，修改时保留旧 suggestions 契约，单列新 ID 搜索端点，不将提案描述成已经上线。

**Interfaces:**
- Consumes: Task 3 hook 与已加载的候选列表。
- Produces: 三个选择入口统一走后端匹配；已选项、CP 重复成员规则、作品／类别过滤和日期排序保持现状。

- [x] 角色与音乐 list 模块用命中 ID 对当前已有过滤列表求交，空 query 直接保留原列表；不取后端结果顺序替代日期排序。CP 本地 query 使用同一 hook，但保留允许选择重复成员的规则。
- [x] 在三个选择框接入设计 §7 的等待和失败提示；公共搜索输入与 CP 输入增加 `maxlength=64`。非空 query 待返回时不显示旧关键词的列表。本命选择仍从现有已投项中选择，不改投票提交或草稿。
- [x] Task 3 的真实 hook 测试断言成功响应产生 `Set<string>`。源列表求交只保留现有简单 filter 与排序，不另写复制 filter 实现的测试。自查角色／音乐排除已选项与 CP 不排除的差别。
- [x] 所有入口切换后搜索 Pinin 调用，移除已无调用的源文件、依赖和过时测试。后端已有拼音规则测试，前端不复制这些场景，也不新增测试证明旧文件被删。
- [x] 同步前端开发说明、后端 API 契约、两端 changelog 和设计状态；记录后端先于前端提供接口、回滚先前端后后端，以及无数据库迁移。
- [x] 运行 Task 3 两个前端测试文件和投票页构建：

```bash
./node_modules/.bin/tsx --test packages/vote/src/common/lib/__tests__/candidateSearch.test.ts packages/vote/src/common/lib/__tests__/useCandidateSearch.test.ts
pnpm --filter @touhou-vote/vote build
```

- [x] 按完整改动做一次自查、`git diff --check` 和必要截图。没有 UI 交互授权时，不自动点击或输入；真实搜索体验由用户人工试用反馈。测试已过且无新问题后结束验证。

**交付：** 拼音词典和匹配计算不再随投票前端执行，旧后端接口仍兼容。产品验收前仍须实际部署授权与人工试用；本计划不包含这些操作的授权。

## 计划自查与交接

- 纯匹配器、搜索服务、DAO、API 与 Vue hook 的函数名和 ID 类型在设计与计划中保持一致。
- 每一项首版匹配范围与缓存行为都有对应任务；数据持久化、结果页、CP 推荐和读音编辑没有被带入范围。
- 新增测试集中于实际新行为，复用既有层次；没有新增端到端环境或性能工作流。
- 用户已确认，四项任务在当前会话顺序执行；最终只做一次整体只读审阅。


## 执行记录（2026-11-08）

- 两端功能分支均为 `feat/pinyin-backend-search`；已核对远端基线，保留原有无关修改。实施阶段未执行 commit、push、部署或真实数据写入；用户随后授权按两阶段分别提交。
- 后端：`python -m pytest tests/unit/test_pinyin_matcher.py tests/unit/test_autocomplete_service.py tests/unit/test_cache.py tests/integration/test_autocomplete.py tests/integration/test_vote_objects.py -q --tb=short` → 45 passed；有现存 asyncio / Strawberry 弃用提示。
- 后端：`python -m flake8 src/ --max-line-length=88` → 通过。新增匹配器及 autocomplete 集成测试静态检查也通过；没有扩展到修复原 vote_objects 测试文件的已有样式问题。
- 前端：`./node_modules/.bin/tsx --test packages/vote/src/common/lib/__tests__/candidateSearch.test.ts packages/vote/src/common/lib/__tests__/useCandidateSearch.test.ts` → 4 passed。
- 前端：`pnpm --filter @touhou-vote/vote build` → 通过。构建仍提示现有 Browserslist 数据过期，本次不更新无关依赖。
- 前端：对本次相关 TS/Vue 文件运行既有 ESLint；两端 `git diff --check` 通过。
- 不运行浏览器自动交互；未验证线上数据、线上接口或部署后的完整链路。发布需另获授权，并遵循后端先、前端后的顺序。

- 最终整体只读审阅未发现 Critical / Important / Minor 问题；按已确认范围暂不引入并发回填恢复机制、不扩展搜索字段与 CP 组合推荐，不以本地验证替代线上体验验收。
- 锁文件：`pnpm install --lockfile-only --frozen-lockfile --ignore-scripts --offline` 通过，Pinin 的 importer、package 与 snapshot 三处条目已移除，没有更新其他依赖。

### 工作区交接

- 沿用用户要求的两个现有功能分支，保留无关未提交改动；误归属时可用原始备份对照，不自动清理。
- 前端原始现场备份位于 `/tmp/sunyunbo/thvote-frontend-pinyin-before-1meloex6/`，指针 `/tmp/sunyunbo/thvote-frontend-pinyin-backup`；stash 也保留。
- codegen 冲突保留远端新 schema 地址与原本地退出码修复，changelog 保留唯一旧条目；如果需要复原，使用归档中的原文件核对。
- 用户追加授权将当前迁移与后续接口收敛分开提交；不推送、合并或部署。原 vote_objects 测试文件已有样式问题未扩展修复，新增功能与生产静态检查已通过。
