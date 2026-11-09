# thvote-be-re CHANGELOG

> 仓库级变更记录，按 CLAUDE.md §4 维护。日期格式 `YYYY-MM-DD`。
>
> 创建日期：2026-04-27
> **2026-08-31 整理**：合并 9 组重复条目、按日期倒序重排；**2026-07-01 之前**的条目已迁至 [2026H1](CHANGELOG-archive-2026H1.md)，**2026 年第三季度**已于 2026-11-08 分离至 [2026Q3](CHANGELOG-archive-2026Q3.md)。

## [2026-11-09] 问卷定义统一读取后端

- **Changed**：共享结构请求与类型，填写端改用应用内存复用；结果图表、文本详情和高级搜索按后端定义及 code 查询，支持加载失败重试、零回答显示；首页标题与说明读取后台内容。
- **Added**：管理台题目/选项 code 编辑、缺失提示；创建/更新/整树导入校验 ASCII 数字长度与同表重复，非法导入在替换旧树前拒绝。
- **Fixed**：结果查询补取完成率字段、空回答/趋势不再直接访问首条；修正接口结构示例及过时编码/趋势说明。
- **兼容性影响**：ID 作答关联、code 统计/DSL/链接保持；空 code 兼容，非空非法/重复 code 新写入分别返回 422/409。特殊图表和趋势代理绑定保留，未改门禁或统计算法。
- **数据迁移 / 配置变更**：无；不新增依赖或数据库约束，未回填、导入真实题库、重算、发布或部署。详见[设计](superpowers/specs/2026-11-09-questionnaire-backend-source-design.md)与[实施计划](superpowers/plans/2026-11-09-questionnaire-backend-source.md)。

## [2026-11-09] 登记问卷后端化迁移缺口

- **Added**：记录结果端静态题库引用、现有统计接口、id/code 与管理台断口，以及门禁、监控和跨届模型差异；第一阶段聚焦定义来源统一与编码维护，方案待确认。
- **Added**：按用户确认的角色模块加载方式编写设计和五步实施计划，明确结构内存复用、结果消费者接线、管理台编码校验、验证与回滚边界；尚未实现，具体校验细节供审阅。
- **兼容性影响**：仅审查记录，无产品代码或接口行为变化。
- **数据迁移 / 配置变更**：无；未查询线上题库、回填、重算或部署。

## [2026-11-08] 收敛现役文档入口与归档历史过程

- **Changed**：8 份已完成或被后续方案取代的实施计划、3 份明确失效的旧设计移入 archive，修正移动后的相对链接和现役索引；B-037 的展示差异与历史对比等实际剩余仍由 BACKLOG 跟踪。
- **Changed**：新增简短的当前后端结构／数据来源导航，明确设计记录与执行计划用途；不再从历史讨论或空 checkbox 重新派生工作。
- **Changed**：主 CHANGELOG 只保留近期条目，2026Q3 的 44 条记录按完整条目移入季度归档，历史正文保留。
- **兼容性影响**：仅文档路径和阅读入口变化，无代码、接口、依赖、测试门禁或工作流变化。
- **数据迁移 / 配置变更**：无；未部署、迁移、回填、重算或核验线上状态。

## [2026-11-08] 历史 BACKLOG 与文档状态核对

- **Changed**：按后端 44bd972、前端 edeaeea 核对，9 个已实现／过期条目退出开放队列并保留原始归档；修正“候选／问卷前端待做”“无生产通道”“爬虫无测试”“attempt 未展示”等失实状态。
- **Changed**：区分实际源码差异、外部／运营事项和按需建议；撤销 connect 必补、结果站旧 test／日期缺口、固定测试门禁等自动排期前提，保留历史对比接线和 monitor 提示等真实残留。
- **Changed**：同步索引、相关迁移计划／设计的当前状态、计票后补及 CI/CD 说明；证据、未核验范围和边界见 [核对记录](migration/backlog-audit-2026-11-08.md)。
- **兼容性影响**：仅文档，没有修改接口、功能、测试门禁或工作流；不据旧 checkbox 重跑迁移和部署。
- **数据迁移 / 配置变更**：无；未核验线上数据、Nacos、依赖告警或部署，不执行回填、重算、发布或依赖升级。

## [2026-11-08] 统一 autocomplete 搜索入口（第二阶段）

- **Changed**：唯一公开入口收敛到 `POST /api/v1/autocomplete/search`，采用分类／关键词／年度输入及完整 candidate IDs 输出；候选服务归入 `service.py`，DAO 年度参数只在查询时传入。
- **Removed**：旧 suggestions 请求响应模型、限量 ILIKE 查询、空 `search_cps()`、临时 `/autocomplete/candidates/search` 路由及重复服务文件；旧行为测试随对应功能移除，保留真实候选与缓存测试。
- **Changed**：配套前端调用统一路由，公共输入框更名为 `CandidateSearchInput.vue`；拼音算法、两层 Redis 缓存和筛选排序行为不变。
- **兼容性影响**：明确替换原 `/search` 的 suggestions 契约，临时候选路径不保留兼容别名；仓库内未发现旧建议业务调用方。前后端须使用同一阶段的配套版本，回滚亦同。B-062 旧 CP 空实现随功能移除，不代表新增 CP 组合搜索。
- **数据迁移 / 配置变更**：无数据库迁移、依赖或配置变化；沿用现有 autocomplete 缓存失效，新语料／结果 namespace 不变。未推送或部署。

## [2026-11-08] 拼音候选搜索迁至 Python 后端

- **Added**：`pypinyin==0.55.0` 与项目内纯匹配器，支持原文、全拼、声母简拼、多音字、混输和原有模糊音；新增 `POST /api/v1/autocomplete/candidates/search`，按分类与年度返回全部匹配 candidate IDs。
- **Added**：Redis 派生语料及查询结果各缓存 60 秒，复用现有 autocomplete 写入失效、手动清理及故障直算逻辑；不增加数据库字段或 JS 运行时。
- **Changed**：配套前端角色、音乐与 CP 成员选择使用新接口；保留个人筛选与排序，增加等待／失败提示并忽略过期响应，移除前端 Pinin。设计、实施计划和 API 契约已同步。
- **兼容性影响**：旧 `/autocomplete/search` 不变；需先发布后端，再发布配套前端；回滚先前端后后端。当前只在两个 `feat/pinyin-backend-search` 分支本地实现，未部署。
- **数据迁移 / 配置变更**：无数据迁移或新增配置；后端安装新增 Python 依赖。Redis 沿用既有配置。

## [2026-10-29] 生产上线前加固：关闭 API 文档 + 移除测试登录旁路 + deploy-prod 流水线

- **Added**：`Settings.expose_api_docs`（`EXPOSE_API_DOCS`，默认 `false`）。`src/main.py` 按开关传 `docs_url`/`redoc_url`/`openapi_url`，并给 `AppGraphQLRouter` 传 `graphql_ide`——关闭时 `/docs`、`/redoc`、`/openapi.json`、浏览器打开 `/graphql` 均 404，`POST /graphql` 不受影响。回归用例 `tests/unit/test_expose_api_docs.py`（8 例）。
- **Removed**：测试登录旁路整体删除（P-4）：`src/common/verification/test_bypass.py`、`sms_code.py`/`email_code.py` 两个 `consume` 短路、`Settings` 两个字段、`tests/unit/test_test_login_bypass.py`。测试/生产 Nacos 同步删键；`grep -r TEST_LOGIN_BYPASS src` 为空。设计稿与操作文档标记为已移除，`scripts/e2e/scraper_frontend.js` 改为需真实验证码。
- **Added**：`.github/workflows/deploy-test.yml` 新增 `deploy_prod` 手动触发开关与 `deploy-prod` job（`needs: [build-backend, deploy-test]`，复用同一 digest 部署到生产机 `/opt/thvote/prod`）；compose 未变，依赖（redis/nacos）由生产目录的 `docker-compose.deps.yml` 单独维护。
- **Fixed**：`TRUSTED_PROXY_IPS` / `ADMIN_ALLOWED_IPS` 改为 `NoDecode` + 宽容解析，接受 `""`、JSON 数组、逗号分隔三种写法。此前把这两个键按文档写成空串会让 `Settings()` 在 import 期抛 `SettingsError`、进程起不来（生产首次部署实测踩中）。用例 `tests/unit/test_config_ip_lists.py`。
- **兼容性影响**：生产环境 graphQL 文档/调试界面不可用属预期；调用方若依赖 `/openapi.json` 生成客户端，需在测试环境用 `EXPOSE_API_DOCS=true`。
- **数据迁移 / 配置变更**：生产 Nacos 新建 namespace `thvote-prod` + dataId `thvote_be`；`ADMIN_ALLOWED_IPS`/`TRUSTED_PROXY_IPS` 留空、`EXPOSE_API_DOCS=false`。未导入用户数据、未改前端仓库。

## [2026-10-22] 详情问卷保留筛选条件与组合目标

- **Fixed**：角色/音乐/组合详情问卷将原约束与目标对象通过 AND 合并，保留 OR 分组；三个本届榜单的指令模式详情链接也携带原约束。沿用已有压缩 URL 参数并兼容旧链接。
- **Added**：现有高级搜索 DSL 支持 `cp=("A","B"[,"C"])`，完整无序组合匹配、保留重复成员，基于组合票而非角色共同投票。
- **兼容性影响**：GraphQL/REST 字段不变，query 语法加法扩展；先发布后端再发布前端。
- **数据迁移 / 配置变更**：无；未发布、部署或操作真实数据。见 [详情筛选说明](api/result-detail-filters.md)。

## [2026-10-22] 修正部门有效票与问卷填写统计

- **Fixed**：角色/音乐/组合 `global.totalVotes` 按最新、未作废的部门提交计票，不再累加票位；单票组合不入榜但其提交仍计有效票。候选票数、本命及平均/中位得票不变。
- **Fixed**：问卷完成率按真实问卷 key、当届最新答案批次、实际可见题组和实质作答计算；复用门禁规则且保持门禁行为。主榜及高级搜索共用人群统计，结果前端从既有结构接口读取问卷标题，提示显示实际完成率。
- **兼容性影响**：响应字段不变，修正 totalVotes 和 completion.name 口径；旧结果须安排人工重算后更新。图表形式不变，不新增反作弊规则。
- **数据迁移 / 配置变更**：无；未发布、未重算真实结果。见 [统计口径说明](api/result-statistics.md)。

## [2026-10-22] 结果快照时间范围与趋势横轴

- **Added**：计票与结果一起保存投票起止、统计截止、结果生成时间；新增可空 GraphQL `queryResultTimeline(voteYear)`，旧缓存返回 null。
- **Fixed**：趋势桶保留不足一小时的末桶；高级搜索按主榜快照时间分桶，避免配置修改后日期错位。结果前端六处趋势页使用同份时间元信息，移除旧固定日期与延伸至 2099 年的横轴。
- **兼容性影响**：接口加法式变更；新前端需后端先发布。旧快照排名可读，趋势待人工重新计票生成时间信息后显示；反作弊完成后人工计票的流程不变。
- **数据迁移 / 配置变更**：无数据库迁移、无新增配置；未部署、未重算线上结果。见 [接口与发布说明](api/result-timeline.md)。

## [2026-10-20] Scraper 测试补齐 + DLsite 解析修复（B-063）

> 前端作品提名页的“自动获取信息”此前只有 URL 路由/限流测试；本轮补全
> 站点路由与关键解析器单测，并用 Playwright 从真实前端页面验证。

### Added
- **`tests/unit/test_scraper_sites.py`**（22 例）：Steam/THBWiki/Bilibili/DLsite/Dizzylab/Melon 的成功解析；Pixiv/YouTube/Twitter 缺凭据 fail-closed；AcFun/Nico/贴吧/微博 结构缺失时返回结构化 `parsererr`；`process.get_data` 对未知 URL 与解析异常的处理。
- **URL 路由全量用例**：Bilibili（BV/AV/CV/移动端）、Twitter/X、Pixiv 图/小说、Nico 动画/静画、YouTube、微博、贴吧、PatchyVideo、Steam、DLsite、Melonbooks、Dizzylab、AcFun 视频/文章，共 28 个链接形态。
- **`scripts/e2e/scraper_frontend.js` + `docs/testing/scraper-e2e.md`**：Playwright 从前端登录/提名页发起的真实 E2E 脚本与运行手册。

### Fixed
- **DLsite 解析**：`title_el[0].text_content()` 是 BeautifulSoup API，lxml 元素没有该方法，真实页面会直接 `parsererr`；改为 `"".join(itertext())`。
- **Bilibili 无账号抓取**：不再只发随机 `buvid3`。`get_cookies()` 先读 env 覆盖，再查 12h 缓存，最后调用 `/x/frontend/finger/spi` 获取访客 `buvid3/buvid4` + 当前 `b_nut`；无需 `SESSDATA`，Redis 故障也不阻断。**注**：测试机出口 IP 仍被 B 站风控返回 HTML，本机同代码实测 code=0；该机需代理或 SESSDATA 才能真实抓取。

### Tests
- Scraper 相关 51 例全过；`apps/scraper` 行覆盖 **22.1% → 55%**（Steam/THBWiki/DLsite/Dizzylab/Melon 均 69%+）。
- Playwright 前端 E2E：手机号 `19900000001` + 固定码 `888888` 登录，提名页实测 THBWiki/Steam 自动填充成功，Bilibili 当前失败与非法域名均按预期报错。

## [2026-10-20] 老 Mongo 用户导入：bcrypt 兼容 + 旧 id 映射（migration 0020）

> 为把 `thvote_users/voters.bson`（121,957 条）导入测试库，恢复 0018 删掉的
> bcrypt+salt 校验，并新增旧 `_id` 到新 UUID 账号的桥表。旧选票不导（D3-A）。

### Added
- **migration 0020/0021**：`user.legacy_salt`、`legacy_user_mapping(legacy_object_id, user_id, role, batch_id, imported_at)`；0021 把 `role` 放宽到 VARCHAR(32)（`conflict_existing` 长 17，0020 的 16 不够）。
- **`src/db_model/legacy_user_mapping.py`**：映射模型（role ∈ primary/duplicate/conflict_existing）。
- **`scripts/import_legacy_voters.py`**：流式解析、按 `voter_logs` 最后活动去重、测试账号/坏邮箱过滤、分批写入、preflight/commit 双模式。
- **`scripts/rollback_legacy_user_import.py`**：按 batch 回滚，带投票/日志引用保护。
- **`scripts/backup_user_tables.py`**：无 `pg_dump` 依赖的 CSV 轻量备份。
- 测试：`test_legacy_password.py`、`test_legacy_voter_import.py`、`test_legacy_login_compat.py`。

### Changed
- **`src/common/security/password.py`**：新增 `verify_legacy_password` / `verify_any_password`；`AuthProvider` 暴露同名方法。
- **`src/apps/user/service.py`**：登录、改密、注销改用 `verify_any_password`；bcrypt 登录成功后升级 Argon2id 并清空 `legacy_salt`。
- **`pyproject.toml`**：加回 `bcrypt>=4.0.0`；`sqlalchemy` 改为 `sqlalchemy[asyncio]`，显式拉 `greenlet`（SQLAlchemy 2.1 起不再自动安装，Python 3.14 CI 的 alembic 因此失败）。

### 兼容性
- Argon2i 老哈希无需改动即可验证并自动升级；bcrypt 老哈希保留原密码。
- 新注册账号行为不变（始终 Argon2id，`legacy_salt` 为 NULL）。
- 对外接口 shape 不变。

### Tests
- 新增 16 个单元用例 + 5 个登录兼容集成用例；相关 user/auth 回归 38 passed。
- 真实 dump 只读 preflight 计数：winners 80,053 / users 80,050 / mappings 121,951 / conflicts 3。

历史记录：[2026Q3](CHANGELOG-archive-2026Q3.md)；[2026H1](CHANGELOG-archive-2026H1.md)。
