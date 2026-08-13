# 后续开发 BACKLOG（单一仪表盘）

> 创建日期：2026-04-27
> 最后更新：2026-08-13 第二轮（大扫除：31 条已完成/废弃项迁至 [BACKLOG-archive.md](./BACKLOG-archive.md)；B-028/B-054/B-042②/B-043尾项标 ⏸ 等外部——用户确认只能等；前端队列确认我方负责。此前同日：#26 合入盘点、B-050-后补6 完成、事故修复）

把散落在 5 份文档里的 follow-up 收拢到这里。**这是仪表盘，不是真理来源**——每项的上下文还在原文档里，本表只给一行摘要 + 跳转。

如果新发现 follow-up，**两件事都要做**：（1）写进对应主题的源文档；（2）在本表加一行。

---

## 状态总览（现存开放项；已完成/废弃项见 [BACKLOG-archive.md](./BACKLOG-archive.md)）

| 编号 | 主题 | 严重度 | 可并行做？ | 源文档 |
|---|---|---|---|---|
| **B-008** | MongoDB → PostgreSQL 历史用户数据回填脚本 | 中（**设计稿已写，实现未做**；`scripts/` 仍空） | 🟢 可立即做（独立 scripts/ 目录） | [medium-priority-backlog-design](./superpowers/specs/2026-05-16-medium-priority-backlog-design.md) |
| **B-010** | 测试覆盖率门禁切到 `fail_under=80` | 低 | 🟡 待模块稳定 1-2 sprint | [design §九 F6](./superpowers/specs/2026-04-27-user-auth-design.md) / spec §九 |
| **B-011** | SSO 落地后移除 `User.at_least_one_identifier` CHECK 约束（约束仍在 `src/db_model/user.py:49` + migration 0001） | 低 | 🟢 可立即做（**阻塞已解除**：B-007 已完成） | [design §九 F7](./superpowers/specs/2026-04-27-user-auth-design.md) |
| **B-013** | 邮件/短信发送的"已发送"幂等性（避免阿里云调用成功但写日志失败造成的双发） | 低 | 🟡 低优先级，待发送链路稳定 | [design §九 F9](./superpowers/specs/2026-04-27-user-auth-design.md) |
| **B-019** | 错误响应 `{"detail":"..."}` 与 Rust 的 `{"error":"...","service":"..."}` 不一致 | 低 | 🟡 等前端反馈是否需要 | [open-issues §三 U-11](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-020** | mypy 在 CI 不是硬门禁；先清现存告警，再去掉 `\|\| true` | 低 | 🟢 可立即做 | [open-issues §三 U-12](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-022** | 给 CI 加 PG-only 契约测试：插两行同 email 的 user，断言 partial unique index 抛 IntegrityError | 低 | 🟢 可立即做 | [open-issues §三 U-14](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-023** | `tests/integration/conftest.py` 的 `pytest.importorskip("fakeredis")` 改为硬 `import` | 低 | 🟢 可立即做 | [open-issues §三 U-15](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-024** | `UserDAO.save()` 加 `session.merge()` 防 detached instance 静默 no-op | 低 | 🟢 可立即做（防御性加固） | [open-issues §三 U-18](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-026** | DB 治理纪律：PR 模板 model 改动提示 / CI `alembic check` / `db_model 改动必须有 migration` 检查 | 低 | 🟢 可立即做（**阻塞已解除**：B-025 已完成） | [schema-mgmt §三阶段 4](./architecture/database-schema-management.md) |
| **B-028** ⚡ | `.github/workflows/deploy-test.yml` 当前唯一的部署 workflow 没有 prod 路径——main 分支推送也只触发部署到 test 环境（镜像 tag 区分为 `prod` vs `test`，但部署目标都是 TEST_SERVER_HOST）。需要确认是否真的没有 prod 发布通道，或补一个 `deploy-prod.yml`。**注：2026-05-19 的 3 个 `fix(ci)` 提交只是修 deploy-test.yml 的 YAML/包发现 bug，未补 prod 通道，此项仍开放** | 高 | ⏸ **等上游拍板**（2026-08-13 用户确认：只能等） | [cicd-pipeline §二](./operations/cicd-pipeline.md) |
| **B-031** | `src/common/nacos.py` 的 `_parse_config_content` 自带 JS 风格 JSON 容错解析（正则提取），属于隐式技术债——上游 Nacos 配置应该写标准 JSON，让解析器走 `json.loads`。如果是为了兼容某个老 dataId，需文档化该 dataId 的写法约束 | 低 | 🟢 可立即做 | `src/common/nacos.py:29-97` |
| **B-037** | 安全块：二创提名校验(域名/发布时间/udid去重)+ 人工审核队列 + 提名时间窗 + 投票问卷门禁(弱校验) | 🟡 后端+管理端已完成 (2026-06-08)；前端待做（**前端=我方负责，准备开做**，2026-08-13） | — | 后端✅[plan](./superpowers/plans/2026-06-08-security-backend.md)：配置/模型0007/纯校验/DAO/编排+门禁/GraphQL/管理端审核UI/公开查询;前端[plan](./superpowers/plans/2026-06-08-security-frontend.md)待实施 |
| **B-039** | 问卷结构化系统(Block 3A)：后端 4 结构表 + admin 整树导入 + structure 查询 + 结构化答题 + 完成校验升级；前端 questionnaireV2 改从后端拉(一次性切换) | 🟡 后端已完成 (2026-06-08, 已合并 main 2026-07-14)；前端待做（**前端=我方负责，准备开做**，2026-08-13） | — | 后端✅：模型0008/assembler/completion/domain/graphql submitPaperV2/门禁升级/整树导入+UI；前端[plan](./superpowers/plans/2026-06-08-questionnaire-frontend.md)待做 |
| **B-040** | 投票对象迁后端(Block 3B)：角色/音乐 merged_into 去重合并(自动+admin手调) + /vote-objects/characters\|music\|{id} 分类查询；前端角色/音乐/CP 改从后端拉 | 🟡 后端已完成 (2026-06-08, 已合并 main 2026-07-14)；前端待做（**前端=我方负责，准备开做**，2026-08-13） | — | 后端✅：merged_into 0009/detect_merges/merge端点/compute归并/vote-objects端点/合并UI；前端[plan](./superpowers/plans/2026-06-08-vote-objects-frontend.md)待做 |
| **B-041** | 问卷管理增强：自由问卷列表(去年份,持续迭代) + 全层级 CRUD(问卷/题组/题/选项) + 自研嵌套编辑器；契约改问卷数组(migration 0010);取代 B-039 的 admin/契约部分 | 🟡 后端+管理端已完成 (2026-06-09, 已合并 main 2026-07-14)；投票前端待做（**前端=我方负责，准备开做**，2026-08-13） | — | 后端✅：模型重塑+0010/assembler数组/importer数组/completion required/结构端点去年份/扁平答案/13 CRUD端点/自研嵌套编辑器UI；前端[plan](./superpowers/plans/2026-06-08-questionnaire-admin-frontend.md)待做 |
| **B-043** | 注册防刷：发验证码前强制人机验证（阿里云验证码 2.0,service 层双入口收口,默认 fail-closed）+ 补齐发码端点 per-IP 限流与短信 per-号码守卫（当前发码端点**无任何后端限流**,2026-07-16 勘探发现） | 🟡 **人机验证已通真人验收** (2026-07-17):后端壳+Nacos(ENABLED=true,fail-closed)+前端 widget(Touhou-Vote `11a7630`,含 getInstance 触发时机修复)全链路打通,浏览器实测弹窗→过验→倒计时→收码正常;剩:①~~发码 per-IP 限流+短信 per-号码守卫~~✅已做(2026-07-17,service 层 per-IP 30/60s@captcha前 + 短信 per-号码 1/60s@captcha后,367 passed) ②海外网络加载实测 ③上线前切公家账户(手册§六，⏸ 等上游，2026-08-13) | — | [design](./superpowers/specs/2026-07-16-captcha-anti-abuse-design.md) / [接入手册](./operations/captcha-onboarding.md) |
| **B-048** | 拦脚本：让变更请求尽量来自真人浏览器。① 服务端 Origin/Referer 校验（对 GraphQL mutation + REST 提交/发码/登录要求带浏览器头,不带→403）② 端口收口（`:18000` 直连关闭,走 nginx） | 🟡 ①**已合并已部署,默认关** (2026-08-13 确认在 main:`REQUIRE_BROWSER_ORIGIN` 默认 false)——待 Nacos 置 true 灰度开启+真人回归;②**待办**（阻塞:前端 codegen 直连 :18000,收口前须先改走 nginx 代理） | 🟢 ①只差配置开关;②需先改前端 codegen | [design](./superpowers/specs/2026-07-17-block-scripts-design.md) |
| **B-047** | 反机器人特征 IP→ASN/数据中心归属：投票/注册 IP 富化出 ASN、标记机房/代理 IP（阿里云 ECS/AWS 等机房 IP 投票=高度可疑）。写入时或离线查;或用数据中心 IP 段名单。只取证不拦截 | ⏳ 待办（用户 2026-07-17 指定放待办） | 🟢 可独立做（依赖 B-044 可信 IP，已具备） | [反机器人特征清单见 submit-timing/anti-vote-farming 设计] |
| **B-049** | 管理端安全监控台：`require_admin` 统一闸门(secret 常量时间比较 + IP 白名单,fail-closed) + 监控 API(概览/IP·设备聚类/可疑打分/投票浏览器/账号钻取) + 处置动作(单条投票作废/恢复、账号人工复核，仅记录) | 🟡 **后端 Plan 1 已实现** (2026-07-17)：migration `0014`(`raw_*.invalidated` + 索引 + `voter_review` 表) + `src/apps/admin/monitor/`(只读查询 + 处置端点，401 passed，flake8 clean)。**处置动作仅写标记/行，不接入排名计算**——排名效果推迟到 B-050。①✅ `main.py` 三个 ops 端点(`reload-config`/`discover*`)已纳入 `require_admin` 闸门(2026-07-17,勘察确认无内部/自动调用方,唯一调用方是带 secret 的 admin UI)；②前端 Plan 2 **Phase 1+2 已实现** (2026-07-18)：`admin-ui/` Vue3+Vite+TS 模块化(api client/composable/共享组件/view)。Phase 1=仪表盘+5 监控页+Users;Phase 2=**全部 6 个旧工具已迁**(候选项/数据同步/提名审核/问卷 4 层嵌套编辑器/审计日志/导出)。旧面板 `/admin-ui-legacy` 暂留兜底。**待:①视觉验收后删 legacy**(dir+挂载+nav 入口);②几个无 UI 端点补上(用户详情钻取/建合并/ranking preview) | 🟢 验收后清理 legacy;无 UI 端点可选补 | [design](./superpowers/specs/2026-07-17-admin-console-vue-security-monitoring-design.md) / [backend plan](./superpowers/plans/2026-07-17-admin-console-security-monitoring-backend.md) |
| **B-050** ⚡ | **计票系统大重写** —— ✅ **v1 完成 (2026-07-18)**:计票已改读真实提交表 `raw_*`(取每 `vote_id` 最新、排除 `invalidated`);按角色/音乐 id 归票 + 白名单丢未知 id;CP 改无序 multiset(顺序/主动方不进 key)+ 主动率 + 组合票数 1 不计;名次口径对齐权威文档(票数→本命数→系统ID,同票数同名次虚位);`RankingEntity` schema 补 `id`/`favorite_percentage_of_all`。删死表 vote_data 已完成(2026-07-17)。**v1 后补子项：1/4/8 已在 `feat/result-graphql-compat` 分支完成(2026-07-19,见下),2/3/5/6 仍开放**。 | 🟡 中（核心闭环已修复,后补项非阻塞） | — | **[设计稿:纯 id 记票重写](./superpowers/specs/2026-07-18-result-recount-id-based-design.md)**(§九 v1 实现落地);`compute_dao.py`/`compute.py`/`compute_service.py`/`whitelist.py`;数据落点见 B-049 |
| **B-050-后补2** | trend 投票演进:需先把 `raw_*` 改造成 **append-only** 存储(当前 `SubmitDAO._upsert` 是"删旧插新"覆盖式,见 `src/apps/submit/dao.py`,改票会丢历史行);现有 `trend`/`trend_first` 字段只是按"最新提交时间"分桶的近似值,非真实演进曲线。**仍开放**——`queryQuestionnaireTrend`/`queryCharacterTrend` 等契约字段本轮已就位但内容退化(问卷 trend 恒为空序列,角色/音乐 trend 是近似值),需此项落地才有真实演进曲线 | 中(需先改存储层) | 🟡 需先定 append-only 方案 | 同上设计稿 §9.4 |
| **B-050-后补3** | 上届对比:需历史 `final_ranking` 表有数据,且 `compute_dao.load_historical` 的 key 是 name、与 id-based 归票路径未对齐(现 `compute_service.py` 传空 `{}`)。**仍开放**——本轮契约层 `RankingEntry`/`CPRankingEntry` 的 8 个 `*_last_1`/`*_last_2` 历史字段已按 brief 要求固定填 0(见契约层 `_ranking_entry_from_dict` docstring 的"移除条件"),此项落地后需同步把契约层从硬编码 0 改成读 `rank[1]`/`rank[2]` 快照 | 低 | 🟢 可独立做 | 同上设计稿 §9.4 |
| **B-050-后补5** | 高级搜索("从投票中筛选",交叉引用 + 指令语言)。**关键发现(2026-07-19)**：DSL **不是"过滤已算好的榜"，而是"换一个投票子集重算榜"**——即 `chars:["x"]` 这类约束要先圈出满足条件的 `vote_id` 子集，再对这个子集重新跑一遍 `compute_ranking`/`compute_cp_ranking` 等聚合，而不是对现成 Redis 榜单做后置过滤（后置过滤会得到错误的百分比/名次基数）。需要**按需子集重算能力**（不能预算全部子集组合），且与 C1 分段统计**共用同一份 `vote_id → {题code: [选项code]}` 索引**（"筛选"和"切分"是同一个原语：用投票/问卷回答约束投票集合）。本轮契约层的 `query` 参数已接住此参数并在非空时明确报 `ADVANCED_SEARCH_NOT_IMPLEMENTED`（不静默返回未筛选的全量榜） | 低 | 🟢 可独立做(与 B-053 同组，共用索引) | 同上设计稿 §8.2；本设计稿 §五「C1.2」/§九「BACKLOG」 |
| **B-053** | 通用"任意问卷题 × 投票结果"交叉分析 API + 前端（与 B-050-后补5 高级搜索同组，共用 `vote_id → {题code: [选项code]}` 索引）：本轮只落地了"性别"这一个特例分段(经配置指定的固定题)，通用查询(任选一道问卷题作为切分轴，交叉任意投票结果)与配套前端本轮未做——全题目预聚合会撑爆 Redis 榜单(244 角色 × 32 题 × 40 选项)，应按需算 | 低 | 🟢 可独立做(与 B-050-后补5 同组) | 本设计稿 §五「C1.2」/§九「BACKLOG」 |
| **B-054**（运营） | 录入真实问卷内容并回填 `question_def`/`option_def` 的 `code` 列：线上问卷结构是占位文案 + 非语义自增 id(问卷 id=1,2,3/组 id=1,2/题 id=1,2,3/选项 id=1,2)，**在此之前性别票（B-050-后补1）与问卷结果（B-050-后补4）的统计管道虽已就绪，数字恒为 0**。前端 legacy `Touhou-Vote/packages/shared/data/questionnaire.ts` 含真实问卷内容 + 真实 7 位 id，是现成的导入源，不必手敲 | 高（阻塞两个契约层字段出真实数据） | ⏸ **等出题方**（2026-08-13 用户确认：只能等） | 本设计稿 §四「B」；`Touhou-Vote/packages/shared/data/questionnaire.ts` |
| **B-055**（前端，Touhou-Vote 仓库） | Task 7 验收时勘察 `packages/result/src` 发现的前端已知缺口(与本仓库后端无关，记录以便跨仓库跟踪)：① `characterConnect.vue`/`MusicConnect.vue` 是"维护中"占位页(covote 契约本轮已修好，但无消费方)；② `Doujin.vue` 总票数硬编码字面量 `1272`，无 GraphQL 查询；③ CP 部门只有 `Couple`/`CoupleDetail`/`CoupleSingleDetail`/`CoupleReason` 四页，缺角色/音乐都有的 compare/evolution 页；④ `router.ts` 里 `/test` → `Test.vue` 调试路由无条件注册在生产路由表 | 低（另一仓库，不阻塞本仓库任何工作） | — | `Touhou-Vote/packages/result/src/{pages/characterConnect.vue,pages/MusicConnect.vue,pages/Doujin.vue,router.ts}` |
| **B-056** | 迁移编号约定漂移：zfq_dev 的 voteable/work 重构引入 autogenerate 哈希名迁移 `12a5f2e6dbed_voteable_cross_year_stable_id`（约定应为 `00XX` 顺延）。测试库 `alembic_version` 已记录该 id，**改名需 stamp 修正、不建议轻动**——文档化现状即可；`0015` 已重接其后成单链（`0014→12a5f2e6dbed→0015`），**后续新迁移从 `0016` 顺延、down_revision 指 `0015`**。与 zfq 同步一下命名约定，避免下次再产生哈希名 | 低 | 🟢 纯约定沟通 | `alembic/versions/12a5f2e6dbed_*.py`；[[branch-ownership-zfq-dev]] 约定见 CLAUDE.md §9 |
| **B-057** | voteable/work 重构收尾清单（2026-07-23 合入盘点发现）：① `GET /admin/voteables`（设计 §4.6）设计有实现无（404），admin 编辑 voteable.workId 缺入口；② admin import 的 work 按 name 匹配/自动建 work（Task 5，计划内 tech-debt）；③ 上届 `final_ranking`(year=11) 导入未执行（会议结论要求"只导上届"）；④ 前端 Task 8/9（characterList/musicList 过滤逻辑、专辑名反查）+ **提交侧切 candidateId**（前置 B-050-后补6 已于 08-13 解除；**前端=我方负责**）；⑤ 设计稿/plan 的 checkbox 与状态维护（与 zfq 沟通） | 中 | 🟢 ①②③可独立；④前置已解除，入我方前端队列 | [work 统一设计稿](./superpowers/specs/2026-07-21-work-table-unified-design.md)；[实施计划](./superpowers/plans/2026-07-21-work-table-unified.md)；CHANGELOG 2026-07-23 条目 |
| **B-059** | 后端 Nacos 不可达时**静默回退**默认配置(localhost DB)再崩——08-13 事故中真实根因(Nacos auth 500)被掩埋在 asyncio 未回收异常里,排障绕了一圈。改法:`NACOS_ENABLED=true` 且拉取失败时 fail-fast 抛明确错误(带"检查 mynacos 容器"提示),不要带默认值起跑。与 B-017(热更新限制)同域 | 中（排障成本,已有 CI 前置检查兜一层） | 🟢 可立即做 | `src/common/nacos.py`/`config.py`；事故记录 `docs/operations/nacos-config-center.md` §八 |
| **B-058** | dependabot 9 个 npm 告警(3 高 6 中,2026-08-13 push 时发现):全部位于 `admin-ui/` 构建链(vite≤6.4.2 fs.deny 绕过/路径穿越、esbuild dev-server、nanoid、postcss)。**均为 dev/构建期依赖,不进运行时**(admin-ui 走 commit-dist);风险=开发者本机跑 `pnpm dev/build` 时。修法:`cd admin-ui && pnpm update vite esbuild postcss nanoid` + 重建 dist | 低（构建期,非线上面） | 🟢 可立即做 | https://github.com/PatchyVideo/thvote-be-re/security/dependabot |
| **B-046** | 反机器人特征：User-Agent（服务端取）+ 浏览器环境（tz/screen/lang，前端采）落 `raw_*.client_env`（单 JSON 列 migration 0013）。只取证不拦截 | 🟡 **后端已合并已部署** (0013 已在测试库,2026-08-13 盘点确认在 main);前端(Touhou-Vote `4b89a23`)状态需在前端仓核对。待:①前端侧确认已推+真人验证 ②Phase 2 聚类纳入 | — | [design](./superpowers/specs/2026-07-17-submit-timing-signal-design.md) |
| **B-045** | 反机器人时序特征：提交耗时 `fill_duration_ms`（客户端挂载→提交,新列 migration 0012）+ 服务端 `attempt` 改票计数（复用死列,首次=1/改票≥2）。只取证不拦截;"耗时短=可疑"只对首次生效,改票豁免（根治改票假阳性） | 🟡 **后端已合并已部署** (0012 已在测试库,2026-08-13 盘点确认在 main,07-24 tally 系列还补了首填耗时防洗白);前端(Touhou-Vote `f59585a`)状态需在前端仓核对。待:①前端侧确认已推+真人验证 ②Phase 2 管理端多信号聚类 | — | [design](./superpowers/specs/2026-07-17-submit-timing-signal-design.md) |
| **B-044** | 反刷票证据采集：设备 UUID 指纹（注册 + 每票）+ 可信客户端 IP（读 X-Real-IP、CIDR 信任、REST 覆盖）。只取证不拦截,供事后按 IP/设备聚类多账号 | 🟡 **Phase 0 已联调验证** (2026-07-17):后端(0011+deviceId落库+IP修复,355 passed,已部署)+前端(Touhou-Vote `4b9f4c5`,已部署:8082)+Nacos `TRUSTED_PROXY_IPS` 已配;真人投票实测:新票记真实公网 IP(对照旧票 nginx 内网 172.18.0.7)+设备指纹已落 raw_*。待:①Phase 1 FingerprintJS(+ HTTP 兜底改 crypto.getRandomValues) ②Phase 2 管理端聚类视图 ③投票记录 append-only 评估 ④admin 端点暴露 register_device_id/投票指纹(现仅 CSV 出 user_ip) | — | [design](./superpowers/specs/2026-07-17-anti-vote-farming-design.md) |
| **B-042** | 测试环境配置硬化（2026-07-14 联调准备中实测发现）：①✅ **已解决**(2026-07-17)——Nacos `thvote_be` 已配 `ADMIN_SECRET`(测试弱值 `abc123`,公开前换强值),`require_admin` fail-closed(secret+IP 白名单)已覆盖 `/api/v1/admin/*` 两路由 **+ `main.py` 三个 ops 端点**(`reload-config`/`discover*`),admin 不再裸奔;② scraper **Pixiv 凭据仍未配**(`Pixiv authentication failed`),二创提名刮削 Pixiv 源不可用,**上线前必须配**(配完需重启容器,B-017) | 低（仅剩 Pixiv 配置项，且 2026-08-13 用户示意**可能不再需要 Pixiv**） | ⏸ 等上游/待定（若确认不用 Pixiv 即可关闭本项） | Nacos 控制台见 `docs/operations/nacos-config-center.md` |

---

## ⏸ 等外部 / 上游（2026-08-13 用户确认：只能等，我方不排期）

- **B-028** prod 部署通道——等上游拍板部署形态
- **B-054** 真实问卷录入 + code 回填——等出题方定稿（性别票/问卷统计出真实数字的唯一阻塞）
- **B-042②** Pixiv 凭据——等上游；且**可能不再需要 Pixiv**，若确认不用即可关闭
- **B-043 尾项** 切公家验证码账户——等上游（海外网络加载实测可自行随时做）

## 🎨 前端队列（Touhou-Vote 仓，我方负责，2026-08-13 确认）

按依赖顺序：

1. **提交侧切 candidateId**（B-057④）——后端前置(B-050-后补6)已于 08-13 解除，需与 zfq 协调切换时点
2. **B-039** questionnaireV2 改拉后端结构（一次性切换）
3. **B-040** 角色/音乐/CP 投票对象改拉后端 `/vote-objects/*`
4. **B-041** 问卷前端消费数组契约
5. **B-037** 安全块前端（提名校验交互）
6. 核对 **B-045**(`f59585a`)/**B-046**(`4b89a23`) 两个前端 commit 是否已推已部署
7. **B-055** 已知缺口（connect 占位页、Doujin 硬编码 1272、`/test` 调试路由）

## 🟢 后端可立即做（10 项）

按建议优先级排序：

| 编号 | 一句话 | 估时 |
|---|---|---|
| **B-059** | Nacos 不可达时 fail-fast（08-13 事故教训，取代静默回退 localhost DB） | 半天 |
| **B-026** | DB 治理纪律：PR 模板 + CI `alembic check`（防 B-051 类漂移复发） | 半天 |
| **B-057①③** | `GET /admin/voteables` 补实现；上届 final_ranking(year=11) 导入 | 各半天 |
| **B-008** | MongoDB → PG 数据回填脚本**实现**（设计稿已写，`scripts/` 仍空，不动主代码） | 1-3 天 |
| **B-020** | mypy 接入 CI（现状:lint job 只 pip install 了 mypy 但从未运行），先清告警再当门禁 | 半天-1 天 |
| **B-058** | admin-ui 构建链 9 个 npm 告警：`pnpm update` + 重建 dist | 1 小时 |
| **B-022** | CI PG-only 契约测试：partial unique index 行为验证 | 1 小时 |
| **B-023** | `importorskip` → 硬 import | 5 分钟 |
| **B-031** | Nacos 配置约束为标准 JSON 后删除 `_parse_config_content` 容错分支 | 1 小时（视上游配置是否能改） |
| **B-011** | 移除 `at_least_one_identifier` CHECK 约束；需新 migration（编号从 **0017** 起） | 1 小时 |

## 🟡 需要判断 / 等条件成熟

- **B-010** 覆盖率门禁切 `fail_under=80`（依赖模块运行 1-2 sprint 稳定后再切）
- **B-013** 邮件/短信发送幂等性（低优先级，发送链路已稳定后做）
- **B-019** 错误响应 `{"detail"}` → 与 Rust `{"error","service"}` 统一（等前端反馈是否需要）
- **B-024** `UserDAO.save()` 加 `session.merge()`（防御性加固）
- **B-033** 删除 legacy-compat 路由层（移除条件：Rust gateway 下线 + 前端迁 `/api/v1` 新 shape；与 B-019 同属契约收敛，详见 `docs/migration/legacy-rest-compat.md`）
- **B-050-后补2/3/5 + B-053** 记票深水区（trend 需 append-only 存储改造；上届对比依赖 B-057③ 数据；高级搜索/交叉分析共用"子集重算"原语）——适合打包出一份设计稿再动手
- **B-049 尾项** admin-ui legacy 面板视觉验收后删除；无 UI 端点可选补
- **B-047** IP→ASN 机房归属取证（可独立，属反作弊 Phase 2）
- **B-056** 迁移命名约定与 zfq 沟通（顺带同步：下一个迁移编号 **0017**、down=0016）

## 🟢 模块功能缺口（不在 B 编号体系内）

- **autocomplete CP 搜索**：`src/apps/autocomplete/dao.py` 的 `search_cps()` 仍 `return []`（角色/音乐已实现）；需从已提交 `cp.cp_list` JSON 提取唯一 CP 名
- **`GET /server-time` 端点**：旧 gateway 有，Python 侧未移植（低优先级）
- **scraper 测试**：18 站点全部移植但无测试（外部 HTTP 依赖，需 mock）

---

## 推荐的下一步

- **前端（我方）**：candidateId 切换打头——同时解锁 B-057④ 与计票全链路真实数据，是当前唯一不受外部阻塞的高价值主线。
- **后端穿插**：`B-059 + B-026` 打包一个"配置/DB 韧性"小 PR（都是 08-13 事故与 B-051 的直接教训）；暖手 `B-023`（5 分钟）、`B-058`（1 小时）。
- **等外部的四项**不排期，条件一到再捡。

---

## 维护规则

- **新发现 follow-up：** 写进对应主题的源文档；在本表加一行；编号顺延 B-028, B-029...
- **某项完成：** 先把"严重度"改为 ✅ 已完成 + 完成日期 + commit hash / PR #；再把整行**移入 [BACKLOG-archive.md](./BACKLOG-archive.md)**（原文保留），保持本表只有活项
- **三个状态分组**（🟢🟡🔴）随完成情况调整：依赖项落地后，相关项可以从 🔴 升到 🟡 或 🟢
- 本表过 50 项时考虑分类拆文件（按主题：security backlog / schema backlog / test backlog 等），但目前规模够小不必拆
