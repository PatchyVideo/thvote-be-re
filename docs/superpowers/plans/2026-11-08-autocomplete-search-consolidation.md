# 统一 autocomplete 搜索入口

> 状态：2026-11-08 用户已确认；接口收敛已实现，相关检查及整体只读审阅通过，按两阶段分别本地提交。未推送或部署。
> 执行方式：按 superpowers:executing-plans 在当前分支执行；工作区约定优先，不引入额外机制。

## 目标与已确认取舍

第一阶段已提交：后端 `77f43cf`、前端 `26f79df`。原方案为了兼容旧 suggestions 契约保留了两套搜索；仓库内未发现旧接口业务调用方，用户确认只保留一个入口。

最终唯一入口为 `POST /api/v1/autocomplete/search`，采用第一阶段的 `CandidateSearchRequest` / `CandidateSearchResponse`：category、query、可选 vote_year → category、规范化 query、实际 vote_year、全部 candidate_ids。旧 `{query, limit} → {suggestions}` 契约被替换，临时 `/autocomplete/candidates/search` 路径移除，不增加兼容分流或别名路由。

拼音规则、DAO 查询字段、Redis namespace / TTL / 失效、前端筛选及排序语义沿用第一阶段。旧建议缓存键不再读写，现有 autocomplete scope 仍可清理。无数据库迁移、数据操作、新配置或依赖变更。发布需配套前后端；回滚前端与后端到同一阶段，不能混用两个阶段的前端和搜索契约。

## 文件与职责

- 后端 `src/apps/autocomplete/service.py`：用第一阶段候选服务替换旧建议服务；移除重复 `candidate_search.py`。
- `dao.py`：只保留 `load_search_documents`，删除旧 ILIKE 方法和空 CP 方法；DAO 不再保存未使用的默认年度，年度由 service 明确传入。
- `schemas.py`：只保留 CandidateCategory 与候选搜索输入输出；`router.py` 只保留 `/search` 和一个 service 依赖。
- `tests/integration/test_autocomplete.py`：保留真实 DAO + Redis 的新行为测试，更新服务导入和 DAO 构造；删除只测旧契约的用例。
- `tests/integration/test_vote_objects.py`：原 HTTP 用例改为 `/search`；原断言继续验证完整新契约、默认／显式年度及非法输入。
- 移除 `tests/unit/test_autocomplete_service.py`，其旧 limit 分配断言随已删除建议功能过时，不新增测试证明删除。
- 前端 hook 及两份相关测试改为统一路径；将 `common/components/AutoComplete.vue` 改为 `CandidateSearchInput.vue`，更新角色和音乐导入及模板。CP 独立输入继续使用共享 hook。
- 同步 API 文档、设计当前状态、两端 changelog 与前端开发说明；第一阶段计划作为历史实施记录保留。B-062 随旧建议链路移除归档为废弃项，不宣称实现 CP 组合推荐。

## 实施顺序

- [x] 先改已有 HTTP 用例和真实 hook 测试的目标路径，运行观察新契约尚未接到统一入口的失败。
- [x] 合并 service / route / schema / DAO；保留拼音与缓存行为；清理过时测试并更新保留用例的导入。
- [x] 更新前端路径及输入框命名，不改变交互或已确认功能范围。
- [x] 更新文档与 changelog；集中运行下面的相关检查。
- [x] 对第二阶段做一次整体只读审阅；只修具体关键问题，完成第二阶段两仓库提交。保留全部无关工作区改动，不 push / merge / deploy。

## 验证与审阅重点

- 真实 HTTP 请求 `/search` 使用新候选契约，query/year/category 校验仍成立。
- 前端 hook 实际发往 `/v12-be/api/v1/autocomplete/search`，忽略过期响应、清空和失败状态仍成立。
- 单一 router/service，旧 schemas、ILIKE 路径及临时候选路由已无业务引用；不机械复制拼音规则测试。
- backend: `python -m pytest tests/unit/test_pinyin_matcher.py tests/unit/test_cache.py tests/integration/test_autocomplete.py tests/integration/test_vote_objects.py -q --tb=short`；`python -m flake8 src/ --max-line-length=88`。
- frontend: `./node_modules/.bin/tsx --test packages/vote/src/common/lib/__tests__/candidateSearch.test.ts packages/vote/src/common/lib/__tests__/useCandidateSearch.test.ts`；本次相关文件 ESLint；`pnpm --filter @touhou-vote/vote build`。
- 两端 `git diff --check`；检查暂存区只包含本阶段改动。无浏览器自动交互或线上验收。


## 本地验证记录

- 第一阶段提交前：后端相关 45 项测试与 flake8 通过；前端 4 项测试与投票页构建通过。
- 第二阶段：先将真实 HTTP 用例指向 `/search`，观察返回旧 suggestions 导致契约断言失败；真实 hook 用例观察仍请求临时候选 URL，路径断言失败。合并实现后两项恢复通过。
- 后端集中命令：上述保留范围 `33 passed`，两条现存 asyncio / Strawberry 弃用提示；删除的 12 项仅对应已移除的旧建议行为。生产 `flake8 src/ --max-line-length=88` 通过。
- 前端两个测试文件：`4 passed`；相关文件 ESLint 通过；投票页构建通过（现有 Browserslist 数据过期提示未改）。
- 不运行浏览器自动交互、线上请求或数据库操作；无关改动保留在工作区，不纳入两阶段提交。

- 最终整体只读审阅未发现 Critical / Important / Minor 问题；确认服务代码搬移及输入框重命名的内容完全一致，无需追加修复。两端暂存区检查通过，无关文件原始哈希未改变。
