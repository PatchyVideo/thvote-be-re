# 后续开发 BACKLOG（单一仪表盘）

> 创建日期：2026-04-27
> 最后更新：2026-07-23（main 快进同步 zfq_dev 的 voteable/work 重构、#25 契约层随后合并；0015 重接 12a5f2e6dbed 消双头；新增 B-056 迁移命名漂移；双仓开出 renko_dev 工作分支）

把散落在 5 份文档里的 follow-up 收拢到这里。**这是仪表盘，不是真理来源**——每项的上下文还在原文档里，本表只给一行摘要 + 跳转。

如果新发现 follow-up，**两件事都要做**：（1）写进对应主题的源文档；（2）在本表加一行。

---

## 状态总览（B-001..B-033）

| 编号 | 主题 | 严重度 | 可并行做？ | 源文档 |
|---|---|---|---|---|
| **B-001** | ~~把 `raw_*` / character / music / cp / questionnaire 纳入 Alembic（baseline `0002`）~~ | ✅ 已完成 (2026-05-12) | — | `alembic/versions/0002_voting_tables.py` |
| **B-002** | ~~submit 模块 `prefix="/v1"` 路径 bug（导致 `/api/v1/v1/...`）~~ | ✅ 已完成 (2026-05-12) | — | `src/apps/submit/router.py` prefix 改为 `""` |
| **B-003** | ~~submit 端点改用真 `vote_token` 校验（当前仅靠 `meta.vote_id` 加锁，存在鉴权空洞）~~ | ✅ 已完成 (2026-05-13, `8724e39`) | — | vote_token subject 改 user_id + JWT 校验 |
| **B-004** | ~~祖传 L-1：CORS `allow_origins=["*"]` + `allow_credentials=True`，未来改 reflected origin 即变 CSRF 入口~~ | ✅ 已完成 (2026-05-15, `9684643`) | — | env `CORS_ALLOWED_ORIGINS` 显式域名列表 |
| **B-005** | ~~祖传 L-2：`rate_limit.py` 非原子，登录 5/60s 限流可被并发绕过~~ | ✅ 已完成 (2026-05-12) | — | `INCR+EXPIRE` 原子计数替换三步 GET/检查/DECR |
| **B-006** | ~~祖传 L-3：`logging.basicConfig` 重复调用（merge 残留）~~ | ✅ 已完成 (2026-05-12) | — | 删除 `src/main.py` 第 24-30 行重复块 |
| **B-007** | ~~thbwiki / qq / patchyvideo SSO 接入；落地后 VoterFE 的 `thbwiki/patchyvideo` 字段切真值~~ | ✅ 已完成 (2026-05-17, `19d659f`..`e19d941`) | — | QQ + THBWiki OAuth，6 SSO 端点 + Redis LoginSession + migration 0004。注：patchyvideo SSO 暂未含 |
| **B-008** | MongoDB → PostgreSQL 历史用户数据回填脚本 | 中（**设计稿已写，实现未做**；`scripts/` 仍空） | 🟢 可立即做（独立 scripts/ 目录） | [medium-priority-backlog-design](./superpowers/specs/2026-05-16-medium-priority-backlog-design.md) |
| **B-009** | ~~trusted proxies / `X-Forwarded-For` 处理（`get_client_ip` 当前只信 `request.client.host`）~~ | ✅ 已完成 (2026-05-15, `9684643`) | — | env `TRUSTED_PROXY_IPS`，`apps/user/deps.py` |
| **B-010** | 测试覆盖率门禁切到 `fail_under=80` | 低 | 🟡 待模块稳定 1-2 sprint | [design §九 F6](./superpowers/specs/2026-04-27-user-auth-design.md) / spec §九 |
| **B-011** | SSO 落地后移除 `User.at_least_one_identifier` CHECK 约束（约束仍在 `src/db_model/user.py:49` + migration 0001） | 低 | 🟢 可立即做（**阻塞已解除**：B-007 已完成） | [design §九 F7](./superpowers/specs/2026-04-27-user-auth-design.md) |
| **B-012** | ~~`update-password` 单独限流（per user_id 5 req/300s）；当前与其他 update-* 共用桶，弱密码可日均 7200 次爆破~~ | ✅ 已完成 (2026-05-15, `9684643`) | — | update-password 专用限流桶 |
| **B-013** | 邮件/短信发送的"已发送"幂等性（避免阿里云调用成功但写日志失败造成的双发） | 低 | 🟡 低优先级，待发送链路稳定 | [design §九 F9](./superpowers/specs/2026-04-27-user-auth-design.md) |
| **B-014** | ~~`vote_token` 签发 3 个集成场景测试（已验证/未验证 × 投票期内/外）~~ | ✅ 已完成 (2026-05-15, `581102f`) | — | `tests/integration/test_vote_token_and_me.py` |
| **B-015** | ~~`GET /me` 端点 TestClient 集成测试~~ | ✅ 已完成 (2026-05-15, `581102f`) | — | 同上文件 |
| **B-016** | ~~bcrypt → argon2 升级路径端到端集成测试~~ | ✅ 已完成 (2026-05-15, `581102f`) | — | 同上文件 |
| **B-017** | ~~Nacos 热更新与 `lru_cache` 客户端不兼容——`nacos.py` 注册了 listener 但 `get_pnvs_client` / `get_dm_smtp_client` / `get_*_code_service` 全 `lru_cache(maxsize=1)`，hot reload 触达不到这些缓存实例。文档化「改 Aliyun 配置必须重启容器」~~ | ✅ 已完成 (2026-05-16, `ab7a642`) | — | `docs/architecture/nacos-hot-reload-limits.md` |
| **B-018** | ~~`_safe_log` 失败无可见性——加 `audit_log_failures_total` 计数器 + `/health` degraded 状态~~ | ✅ 已完成 (2026-05-17, `fe993e4`) | — | `/health` 暴露审计失败计数 |
| **B-019** | 错误响应 `{"detail":"..."}` 与 Rust 的 `{"error":"...","service":"..."}` 不一致 | 低 | 🟡 等前端反馈是否需要 | [open-issues §三 U-11](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-020** | mypy 在 CI 不是硬门禁；先清现存告警，再去掉 `\|\| true` | 低 | 🟢 可立即做 | [open-issues §三 U-12](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-021** | Pydantic V1 弃用 API（`Field(..., env="X")`）→ V2（`SettingsConfigDict` + `validation_alias`） | 低 | 🟢 可立即做 | [open-issues §三 U-13](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-022** | 给 CI 加 PG-only 契约测试：插两行同 email 的 user，断言 partial unique index 抛 IntegrityError | 低 | 🟢 可立即做 | [open-issues §三 U-14](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-023** | `tests/integration/conftest.py` 的 `pytest.importorskip("fakeredis")` 改为硬 `import` | 低 | 🟢 可立即做 | [open-issues §三 U-15](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-024** | `UserDAO.save()` 加 `session.merge()` 防 detached instance 静默 no-op | 低 | 🟢 可立即做（防御性加固） | [open-issues §三 U-18](./superpowers/specs/2026-04-27-user-auth-open-issues.md) |
| **B-025** | ~~移除 `init_db()` 与 DEBUG 后门，改为启动时 DB 连通性检查失败立即 raise~~ | ✅ 已完成 (2026-05-17, `76facaa`) | — | 移除 init_db DEBUG 后门 + 加连通性检查（`init_db()` 函数体仍保留但不再自动调用） |
| **B-026** | DB 治理纪律：PR 模板 model 改动提示 / CI `alembic check` / `db_model 改动必须有 migration` 检查 | 低 | 🟢 可立即做（**阻塞已解除**：B-025 已完成） | [schema-mgmt §三阶段 4](./architecture/database-schema-management.md) |
| **B-027** | ~~`pylint.yml` 与 `deploy-test.yml` lint 重复，删一个 + 把另一个改硬失败；`deploy-test.yml` 内 `flake8 \|\| true` 软门禁改硬~~ | ✅ 已完成 (2026-05-17, `6d73de6`) | — | flake8 违规清零 + CI 门禁改硬失败 |
| **B-028** ⚡ | `.github/workflows/deploy-test.yml` 当前唯一的部署 workflow 没有 prod 路径——main 分支推送也只触发部署到 test 环境（镜像 tag 区分为 `prod` vs `test`，但部署目标都是 TEST_SERVER_HOST）。需要确认是否真的没有 prod 发布通道，或补一个 `deploy-prod.yml`。**注：2026-05-19 的 3 个 `fix(ci)` 提交只是修 deploy-test.yml 的 YAML/包发现 bug，未补 prod 通道，此项仍开放** | 高 | 🟢 可立即做 | [cicd-pipeline §二](./operations/cicd-pipeline.md) |
| **B-029** | ~~deploy 步骤里 `docker-compose up -d redis` / `docker exec thvote-postgres` 依赖部署机上**仓库外**维护的 `docker-compose.yml`（`docker/` 目录已从仓库删除）。这层耦合需要文档化~~ | ✅ 已完成 (2026-05-16, `0e340e9`) | — | `docs/operations/deploy-server-setup.md` |
| **B-030** | ~~Nacos 接入有一个**模块加载期阻塞调用**：`src/common/config.py` 顶层执行 `_load_nacos_sync()`，import config 即触发同步网络调用——Nacos 不可达时 import 全挂~~ | ✅ 已完成 (2026-05-17, `fce832a`) | — | 改为首次 `get_settings()` 时 lazy load |
| **B-031** | `src/common/nacos.py` 的 `_parse_config_content` 自带 JS 风格 JSON 容错解析（正则提取），属于隐式技术债——上游 Nacos 配置应该写标准 JSON，让解析器走 `json.loads`。如果是为了兼容某个老 dataId，需文档化该 dataId 的写法约束 | 低 | 🟢 可立即做 | `src/common/nacos.py:29-97` |
| **B-034** | ~~MongoDB 全量历史数据同步（A/B/C/D 四类 + migration 0006 + CLI+API 双入口）~~ | ✅ 已完成 (2026-06-07) | — | 11 collections, batch runner, checkpoint/resume, CLI + API |
| **B-035** | ~~管理端扩展（用户管理 + 统计 + 候选项 + 审计日志 + 导出 + Web UI）~~ | ✅ 已完成 (2026-06-07, afdc091) | — | 12 个新端点 + 单文件 Web UI + StaticFiles 挂载 |
| **B-036** | ~~候选项管理增强：CSV/JSON 导入(dry-run 预览) + 单条编辑 + 列表/详情完善 + 管理端改白色主题~~ | ✅ 已完成 (2026-06-08) | — | 3 端点(fields/import/edit) + 后端解析校验 + 白色主题 + 导入/编辑弹窗 |
| **B-037** | 安全块：二创提名校验(域名/发布时间/udid去重)+ 人工审核队列 + 提名时间窗 + 投票问卷门禁(弱校验) | 🟡 后端+管理端已完成 (2026-06-08)；前端待做 | — | 后端✅[plan](./superpowers/plans/2026-06-08-security-backend.md)：配置/模型0007/纯校验/DAO/编排+门禁/GraphQL/管理端审核UI/公开查询;前端[plan](./superpowers/plans/2026-06-08-security-frontend.md)待实施 |
| **B-038** | ~~作品投票全链路~~ | ⛔ 已废弃 (2026-06-08)：官方作品投票本届确认不做 | — | 文档存档于 specs/plans,标记废弃,不实施 |
| **B-039** | 问卷结构化系统(Block 3A)：后端 4 结构表 + admin 整树导入 + structure 查询 + 结构化答题 + 完成校验升级；前端 questionnaireV2 改从后端拉(一次性切换) | 🟡 后端已完成 (2026-06-08, 已合并 main 2026-07-14)；前端待做 | — | 后端✅：模型0008/assembler/completion/domain/graphql submitPaperV2/门禁升级/整树导入+UI；前端[plan](./superpowers/plans/2026-06-08-questionnaire-frontend.md)待做 |
| **B-040** | 投票对象迁后端(Block 3B)：角色/音乐 merged_into 去重合并(自动+admin手调) + /vote-objects/characters\|music\|{id} 分类查询；前端角色/音乐/CP 改从后端拉 | 🟡 后端已完成 (2026-06-08, 已合并 main 2026-07-14)；前端待做 | — | 后端✅：merged_into 0009/detect_merges/merge端点/compute归并/vote-objects端点/合并UI；前端[plan](./superpowers/plans/2026-06-08-vote-objects-frontend.md)待做 |
| **B-041** | 问卷管理增强：自由问卷列表(去年份,持续迭代) + 全层级 CRUD(问卷/题组/题/选项) + 自研嵌套编辑器；契约改问卷数组(migration 0010);取代 B-039 的 admin/契约部分 | 🟡 后端+管理端已完成 (2026-06-09, 已合并 main 2026-07-14)；投票前端待做 | — | 后端✅：模型重塑+0010/assembler数组/importer数组/completion required/结构端点去年份/扁平答案/13 CRUD端点/自研嵌套编辑器UI；前端[plan](./superpowers/plans/2026-06-08-questionnaire-admin-frontend.md)待做 |
| **B-043** | 注册防刷：发验证码前强制人机验证（阿里云验证码 2.0,service 层双入口收口,默认 fail-closed）+ 补齐发码端点 per-IP 限流与短信 per-号码守卫（当前发码端点**无任何后端限流**,2026-07-16 勘探发现） | 🟡 **人机验证已通真人验收** (2026-07-17):后端壳+Nacos(ENABLED=true,fail-closed)+前端 widget(Touhou-Vote `11a7630`,含 getInstance 触发时机修复)全链路打通,浏览器实测弹窗→过验→倒计时→收码正常;剩:①~~发码 per-IP 限流+短信 per-号码守卫~~✅已做(2026-07-17,service 层 per-IP 30/60s@captcha前 + 短信 per-号码 1/60s@captcha后,367 passed) ②海外网络加载实测 ③上线前切公家账户(手册§六) | — | [design](./superpowers/specs/2026-07-16-captcha-anti-abuse-design.md) / [接入手册](./operations/captcha-onboarding.md) |
| **B-048** | 拦脚本：让变更请求尽量来自真人浏览器。① 服务端 Origin/Referer 校验（对 GraphQL mutation + REST 提交/发码/登录要求带浏览器头,不带→403）② 端口收口（`:18000` 直连关闭,走 nginx） | 🟡 ①**已实现待部署** (2026-07-17,`REQUIRE_BROWSER_ORIGIN` 默认关,373 passed,PR 待合并);②**待办**（阻塞:前端 codegen 直连 :18000,收口前须先改走 nginx 代理） | 🟢 ①可独立;②需先改前端 codegen | [design](./superpowers/specs/2026-07-17-block-scripts-design.md) |
| **B-047** | 反机器人特征 IP→ASN/数据中心归属：投票/注册 IP 富化出 ASN、标记机房/代理 IP（阿里云 ECS/AWS 等机房 IP 投票=高度可疑）。写入时或离线查;或用数据中心 IP 段名单。只取证不拦截 | ⏳ 待办（用户 2026-07-17 指定放待办） | 🟢 可独立做（依赖 B-044 可信 IP，已具备） | [反机器人特征清单见 submit-timing/anti-vote-farming 设计] |
| **B-049** | 管理端安全监控台：`require_admin` 统一闸门(secret 常量时间比较 + IP 白名单,fail-closed) + 监控 API(概览/IP·设备聚类/可疑打分/投票浏览器/账号钻取) + 处置动作(单条投票作废/恢复、账号人工复核，仅记录) | 🟡 **后端 Plan 1 已实现** (2026-07-17)：migration `0014`(`raw_*.invalidated` + 索引 + `voter_review` 表) + `src/apps/admin/monitor/`(只读查询 + 处置端点，401 passed，flake8 clean)。**处置动作仅写标记/行，不接入排名计算**——排名效果推迟到 B-050。①✅ `main.py` 三个 ops 端点(`reload-config`/`discover*`)已纳入 `require_admin` 闸门(2026-07-17,勘察确认无内部/自动调用方,唯一调用方是带 secret 的 admin UI)；②前端 Plan 2 **Phase 1+2 已实现** (2026-07-18)：`admin-ui/` Vue3+Vite+TS 模块化(api client/composable/共享组件/view)。Phase 1=仪表盘+5 监控页+Users;Phase 2=**全部 6 个旧工具已迁**(候选项/数据同步/提名审核/问卷 4 层嵌套编辑器/审计日志/导出)。旧面板 `/admin-ui-legacy` 暂留兜底。**待:①视觉验收后删 legacy**(dir+挂载+nav 入口);②几个无 UI 端点补上(用户详情钻取/建合并/ranking preview) | 🟢 验收后清理 legacy;无 UI 端点可选补 | [design](./superpowers/specs/2026-07-17-admin-console-vue-security-monitoring-design.md) / [backend plan](./superpowers/plans/2026-07-17-admin-console-security-monitoring-backend.md) |
| **B-051** | ~~**审计日志端点在真实测试库 500**~~ ✅ **已解决 (2026-07-18)**：真因确诊——真实库 `activity_log` **表根本不存在**(`to_regclass`=None),但 `alembic_version` 却是 0014(stamp 未真跑,init_db/stamp 漂移,B-026)。**修法=全量重建**:dump 保留数据(候选 244+612、问卷 8/24/32/40、user 2、raw_*)→ `DROP` 全部表 → `alembic upgrade head` 从空跑通 0001..0014 → reload + 重置序列 → reload-config 刷引擎。activity-logs 现 200。(`login_session` 缺失是误报:SSO 会话在 Redis,本就无此 PG 表。)**遗留原始条目↓**：`GET /api/v1/admin/activity-logs` 在测试机真实库恒 500(sqlite 测试库正常,411 passed 覆盖不到)。已诊断为**查询层失败**(空结果查询也 500),已排除:行数据序列化、被移除的审计列(已改为只 SELECT 5 核心列仍 500,2026-07-18 `f6adc9a`)、null `created_at`(已兜底)。**强假设:真实 `activity_log` 表缺某核心列或表异常**(早期 init_db/stamp 建表遗留,与 B-026 schema 治理同源)。写入侧走 `_safe_log` 吞异常静默失败故长期未暴露。影响:新旧面板"审计日志"页均不可用(仅此一项;其余 5 工具已迁移且 200)。**修复需 DB 直连 introspect `\d activity_log`(对比 `db_model/activity_log.py` 11 列)或容器 docker logs traceback**——本机无 DB 密码/SSH。定位后:补幂等 `ADD COLUMN IF NOT EXISTS` migration 对齐,或修表名 | 中（仅审计日志页,非核心投票链路） | 🟡 需 DB 访问/服务器日志 | `src/apps/admin/service.py:list_activity_logs`；`db_model/activity_log.py`；[[nacos-config-center-access]] |
| **B-050** ⚡ | **计票系统大重写** —— ✅ **v1 完成 (2026-07-18)**:计票已改读真实提交表 `raw_*`(取每 `vote_id` 最新、排除 `invalidated`);按角色/音乐 id 归票 + 白名单丢未知 id;CP 改无序 multiset(顺序/主动方不进 key)+ 主动率 + 组合票数 1 不计;名次口径对齐权威文档(票数→本命数→系统ID,同票数同名次虚位);`RankingEntity` schema 补 `id`/`favorite_percentage_of_all`。删死表 vote_data 已完成(2026-07-17)。**v1 后补子项：1/4/8 已在 `feat/result-graphql-compat` 分支完成(2026-07-19,见下),2/3/5/6 仍开放**。 | 🟡 中（核心闭环已修复,后补项非阻塞） | — | **[设计稿:纯 id 记票重写](./superpowers/specs/2026-07-18-result-recount-id-based-design.md)**(§九 v1 实现落地);`compute_dao.py`/`compute.py`/`compute_service.py`/`whitelist.py`;数据落点见 B-049 |
| **B-050-后补1** | ~~性别男女票:需 `raw_paper` 问卷按性别题 `q11011` join 每个 `vote_id`;v1 的 `compute_gender_map` 读的是死表 `Questionnaire`(恒空),性别恒为 `unknown`~~ ✅ **管道已解决 (2026-07-19)**:`ComputeDAO.load_questionnaire_votes` 改读 `paper_answer`(B-039 结构化表),经 `question_def`/`option_def` 的 `code` 列翻译成语义码;`compute_gender_map`→`build_segment_map`(性别泛化为"配置指定题的分段"),按 `gender_question_code`/`gender_*_option_code` 定位。⚠️ **实际数字仍是 0**:线上问卷是占位内容+非语义自增 id,尚未回填 `code`——见新增 **B-054**(运营录题)，此项解除前性别票不会有真实值 | 低（基础设施已完成,剩纯数据录入） | 🟢 可独立做(等 B-054) | 同上设计稿 §9.4；本设计稿 §五「C1」 |
| **B-050-后补2** | trend 投票演进:需先把 `raw_*` 改造成 **append-only** 存储(当前 `SubmitDAO._upsert` 是"删旧插新"覆盖式,见 `src/apps/submit/dao.py`,改票会丢历史行);现有 `trend`/`trend_first` 字段只是按"最新提交时间"分桶的近似值,非真实演进曲线。**仍开放**——`queryQuestionnaireTrend`/`queryCharacterTrend` 等契约字段本轮已就位但内容退化(问卷 trend 恒为空序列,角色/音乐 trend 是近似值),需此项落地才有真实演进曲线 | 中(需先改存储层) | 🟡 需先定 append-only 方案 | 同上设计稿 §9.4 |
| **B-050-后补3** | 上届对比:需历史 `final_ranking` 表有数据,且 `compute_dao.load_historical` 的 key 是 name、与 id-based 归票路径未对齐(现 `compute_service.py` 传空 `{}`)。**仍开放**——本轮契约层 `RankingEntry`/`CPRankingEntry` 的 8 个 `*_last_1`/`*_last_2` 历史字段已按 brief 要求固定填 0(见契约层 `_ranking_entry_from_dict` docstring 的"移除条件"),此项落地后需同步把契约层从硬编码 0 改成读 `rank[1]`/`rank[2]` 快照 | 低 | 🟢 可独立做 | 同上设计稿 §9.4 |
| **B-050-后补4** | ~~问卷结果页:`compute_paper_results` 仍是占位,读死表 `Questionnaire`;需接入 B-039 结构化问卷表(`raw_paper`/`paper_answer`)~~ ✅ **已解决 (2026-07-19)**:`compute_paper_results` 现读 `ComputeDAO.load_questionnaire_votes` 产出的 `paper_answer` 数据,按答案形状(list→选项计数,字符串→收集)分派,附带每题/每选项的性别交叉(`total_male`/`total_female`/`male_votes`/`female_votes`)。⚠️ 数字仍受 B-054(运营录题)阻塞 | — | — | 同上设计稿 §9.4；本设计稿 §五「C1」 |
| **B-050-后补5** | 高级搜索("从投票中筛选",交叉引用 + 指令语言)。**关键发现(2026-07-19)**：DSL **不是"过滤已算好的榜"，而是"换一个投票子集重算榜"**——即 `chars:["x"]` 这类约束要先圈出满足条件的 `vote_id` 子集，再对这个子集重新跑一遍 `compute_ranking`/`compute_cp_ranking` 等聚合，而不是对现成 Redis 榜单做后置过滤（后置过滤会得到错误的百分比/名次基数）。需要**按需子集重算能力**（不能预算全部子集组合），且与 C1 分段统计**共用同一份 `vote_id → {题code: [选项code]}` 索引**（"筛选"和"切分"是同一个原语：用投票/问卷回答约束投票集合）。本轮契约层的 `query` 参数已接住此参数并在非空时明确报 `ADVANCED_SEARCH_NOT_IMPLEMENTED`（不静默返回未筛选的全量榜） | 低 | 🟢 可独立做(与 B-053 同组，共用索引) | 同上设计稿 §8.2；本设计稿 §五「C1.2」/§九「BACKLOG」 |
| **B-052** | ~~result 前端 ↔ 后端 GraphQL **契约层断裂**：前端 12 个 `query*` 字段名与后端旧 9 个 JSON 标量查询完全不同名、不同形状，测试机 `queryCharacterRanking` 直接 `Cannot query field` —— 结果页一个都跑不起来~~ ✅ **已解决 (2026-07-19)**：新增 `ResultCompatQuery`(`src/api/graphql/resolvers/result_compat.py`)，12 个 `query*` 字段全部落地并复用 `types.py` 现成类型；旧 JSON 查询保留(加法式)。SDL 与真实前端源码(14 个 `.vue` 文件)逐字段核对零漂移；`voteYear`/`query` DSL/`rank` 单条查询/错误处理四项行为约定均按设计稿实现 | — | — | [设计稿](./superpowers/specs/2026-07-19-result-graphql-compat-design.md)；`src/api/graphql/resolvers/result_compat.py` |
| **B-053** | 通用"任意问卷题 × 投票结果"交叉分析 API + 前端（与 B-050-后补5 高级搜索同组，共用 `vote_id → {题code: [选项code]}` 索引）：本轮只落地了"性别"这一个特例分段(经配置指定的固定题)，通用查询(任选一道问卷题作为切分轴，交叉任意投票结果)与配套前端本轮未做——全题目预聚合会撑爆 Redis 榜单(244 角色 × 32 题 × 40 选项)，应按需算 | 低 | 🟢 可独立做(与 B-050-后补5 同组) | 本设计稿 §五「C1.2」/§九「BACKLOG」 |
| **B-054**（运营） | 录入真实问卷内容并回填 `question_def`/`option_def` 的 `code` 列：线上问卷结构是占位文案 + 非语义自增 id(问卷 id=1,2,3/组 id=1,2/题 id=1,2,3/选项 id=1,2)，**在此之前性别票（B-050-后补1）与问卷结果（B-050-后补4）的统计管道虽已就绪，数字恒为 0**。前端 legacy `Touhou-Vote/packages/shared/data/questionnaire.ts` 含真实问卷内容 + 真实 7 位 id，是现成的导入源，不必手敲 | 高（阻塞两个契约层字段出真实数据） | 🟢 可独立做(数据录入，不改代码) | 本设计稿 §四「B」；`Touhou-Vote/packages/shared/data/questionnaire.ts` |
| **B-055**（前端，Touhou-Vote 仓库） | Task 7 验收时勘察 `packages/result/src` 发现的前端已知缺口(与本仓库后端无关，记录以便跨仓库跟踪)：① `characterConnect.vue`/`MusicConnect.vue` 是"维护中"占位页(covote 契约本轮已修好，但无消费方)；② `Doujin.vue` 总票数硬编码字面量 `1272`，无 GraphQL 查询；③ CP 部门只有 `Couple`/`CoupleDetail`/`CoupleSingleDetail`/`CoupleReason` 四页，缺角色/音乐都有的 compare/evolution 页；④ `router.ts` 里 `/test` → `Test.vue` 调试路由无条件注册在生产路由表 | 低（另一仓库，不阻塞本仓库任何工作） | — | `Touhou-Vote/packages/result/src/{pages/characterConnect.vue,pages/MusicConnect.vue,pages/Doujin.vue,router.ts}` |
| **B-056** | 迁移编号约定漂移：zfq_dev 的 voteable/work 重构引入 autogenerate 哈希名迁移 `12a5f2e6dbed_voteable_cross_year_stable_id`（约定应为 `00XX` 顺延）。测试库 `alembic_version` 已记录该 id，**改名需 stamp 修正、不建议轻动**——文档化现状即可；`0015` 已重接其后成单链（`0014→12a5f2e6dbed→0015`），**后续新迁移从 `0016` 顺延、down_revision 指 `0015`**。与 zfq 同步一下命名约定，避免下次再产生哈希名 | 低 | 🟢 纯约定沟通 | `alembic/versions/12a5f2e6dbed_*.py`；[[branch-ownership-zfq-dev]] 约定见 CLAUDE.md §9 |
| **B-050-后补6** | candidate 表迁移 `object_id`(以 id 白名单快照为权威源迁到 DB 表,见设计稿 §四"目标④") | 低 | 🟢 可独立做 | 同上设计稿 §四/§五 |
| **B-050-后补7** | ~~**死代码清理**:`compute_dao.py` 的 `load_char_candidates`/`load_music_candidates`/`load_merge_name_map`/`load_historical` 四个方法在新 id 白名单管线接线后已无任何调用方(纯死方法,只剩自身定义);`compute.py::CandidateMeta` 与 `whitelist.py::_KIND_MAPPING`/`compute.py::KIND_MAPPING` 重复(同一份映射两处维护),可随死方法一并清理~~ | ✅ 已完成(2026-07-18,fix-wave):四个死方法 + `CandidateMeta`/`compute.KIND_MAPPING` 已删,grep 确认 `src/`+`tests/` 零引用(除 `whitelist.py` 自身 `_KIND_MAPPING`) | — | `src/apps/result/compute_dao.py`、`src/apps/result/compute.py` |
| **B-050-后补8** | ~~`compute_covote` 当前输出原始 8-hex id(而非人名),且未过白名单过滤——直接拿去拼结果页会显示乱码 id、也可能混入未上白名单的脏 id;需补 id→name 映射(复用 `Whitelist.name_of`)+ 白名单过滤后才可接入结果页~~ ✅ **已解决 (2026-07-19)**:`compute_covote` 新增 `whitelist` 参数,先按白名单过滤再配对,输出 `a`/`b` 改用 `Whitelist.name_of()` 转人名;`cs`/`mi` 两个相关性/互信息字段本轮仍置 0(未实现,无消费方)。⚠️ 诚实提示:前端 `characterConnect`/`MusicConnect` 页仍是"维护中"占位(见 **B-055**),接口修好不代表前端立刻可看 | — | — | `src/apps/result/compute.py::compute_covote`、`src/apps/result/whitelist.py` |
| **B-046** | 反机器人特征：User-Agent（服务端取）+ 浏览器环境（tz/screen/lang，前端采）落 `raw_*.client_env`（单 JSON 列 migration 0013）。只取证不拦截 | 🟡 **已实现待部署** (2026-07-17):后端(0013 + client_env 落库,377 passed)PR 叠在 #11 上待合并;前端(Touhou-Vote `4b89a23`,已 commit 待推)。待:①合 #11 再合本 PR→部署→推前端→验证 ②Phase 2 聚类纳入 | — | [design](./superpowers/specs/2026-07-17-submit-timing-signal-design.md) |
| **B-045** | 反机器人时序特征：提交耗时 `fill_duration_ms`（客户端挂载→提交,新列 migration 0012）+ 服务端 `attempt` 改票计数（复用死列,首次=1/改票≥2）。只取证不拦截;"耗时短=可疑"只对首次生效,改票豁免（根治改票假阳性） | 🟡 **已实现待部署** (2026-07-17):后端(0012 + `_upsert` 算 attempt + fill_duration 落库,369 passed)PR 待合并;前端(Touhou-Vote `f59585a`,已 commit 待推)。待:①后端合并部署→推前端→真人验证 ②Phase 2 管理端多信号聚类 | — | [design](./superpowers/specs/2026-07-17-submit-timing-signal-design.md) |
| **B-044** | 反刷票证据采集：设备 UUID 指纹（注册 + 每票）+ 可信客户端 IP（读 X-Real-IP、CIDR 信任、REST 覆盖）。只取证不拦截,供事后按 IP/设备聚类多账号 | 🟡 **Phase 0 已联调验证** (2026-07-17):后端(0011+deviceId落库+IP修复,355 passed,已部署)+前端(Touhou-Vote `4b9f4c5`,已部署:8082)+Nacos `TRUSTED_PROXY_IPS` 已配;真人投票实测:新票记真实公网 IP(对照旧票 nginx 内网 172.18.0.7)+设备指纹已落 raw_*。待:①Phase 1 FingerprintJS(+ HTTP 兜底改 crypto.getRandomValues) ②Phase 2 管理端聚类视图 ③投票记录 append-only 评估 ④admin 端点暴露 register_device_id/投票指纹(现仅 CSV 出 user_ip) | — | [design](./superpowers/specs/2026-07-17-anti-vote-farming-design.md) |
| **B-042** | 测试环境配置硬化（2026-07-14 联调准备中实测发现）：①✅ **已解决**(2026-07-17)——Nacos `thvote_be` 已配 `ADMIN_SECRET`(测试弱值 `abc123`,公开前换强值),`require_admin` fail-closed(secret+IP 白名单)已覆盖 `/api/v1/admin/*` 两路由 **+ `main.py` 三个 ops 端点**(`reload-config`/`discover*`),admin 不再裸奔;② scraper **Pixiv 凭据仍未配**(`Pixiv authentication failed`),二创提名刮削 Pixiv 源不可用,**上线前必须配**(配完需重启容器,B-017) | 低（仅剩 Pixiv 配置项） | 🟢 配置项,随时可做 | Nacos 控制台见 `docs/operations/nacos-config-center.md` |
| **B-032** | ~~删除（或收紧）`alembic/env.py` 的 `_maybe_baseline_existing_schema`。它只按"表是否存在"自动 stamp、**不校验列是否匹配**，会**掩盖 schema 漂移**——2026-05-31 测试库 `user` 表缺 `phone_verified` 等列、登录全挂就是它造成的（残缺旧表被 stamp 成 0001，0001 的正确建表从未执行）。B-025 已移除 init_db 后门,该 shim 已无存在必要。**首选直接删除**(让 `alembic upgrade head` 老实从 0001 跑)+ 空库重建一次清除残留漂移;次选 stamp 前校验列匹配、不匹配则报错而非闷头 stamp。归属 B-025/B-026 DB 治理。~~ | ✅ 已完成 (2026-07-14) | — | 已删 shim,连带移除其配套的"清残留事务"补丁,env.py 恢复标准写法;空库全链路由 CI 迁移烟雾测试(每次 push 对空 PG 跑 upgrade head)持续覆盖 |

---

> **2026-05-30 对账说明：** `feat/user-and-verify` 已全部合入 `main`，原先「🟡 等本 PR merge」的依赖前提消失。下面按「现在还开放的项」重新分组，不再用「等 PR」维度。已完成项保留在上方状态表（标 ✅ + commit）。

## 🟢 现在可立即做（9 项，全部已解除阻塞）

按建议优先级排序：

| 编号 | 一句话 | 估时 |
|---|---|---|
| **B-028** ⚡ | 确认/补齐 prod 部署通道（当前 `deploy-test.yml` 是孤本，main push 也只到 test） | 1 天（视真实部署现状而定） |
| **B-008** | MongoDB → PG 数据回填脚本**实现**（设计稿已写，`scripts/` 仍空，不动主代码） | 1-3 天（看数据量与边界） |
| **B-020** | mypy 在 CI 改硬门禁前先清告警 | 半天-1 天（看现存告警量） |
| **B-021** | Pydantic V1→V2 配置迁移（清 deprecation 告警） | 半天 |
| **B-022** | CI PG-only 契约测试：partial unique index 行为验证 | 1 小时 |
| **B-023** | `importorskip` → 硬 import | 5 分钟 |
| **B-026** | DB 治理纪律：PR 模板 + CI `alembic check`（B-025 已完成，阻塞解除） | 半天 |
| **B-031** | Nacos 配置约束为标准 JSON 后删除 `_parse_config_content` 容错分支 | 1 小时（视上游配置是否能改） |
| **B-011** | 移除 `at_least_one_identifier` CHECK 约束（B-007 SSO 已落地，阻塞解除）；需新 migration | 1 小时 |

> ⚡ = 当前最高优先级

## 🟡 需要判断 / 等条件成熟（5 项）

- **B-010** 覆盖率门禁切 `fail_under=80`（依赖模块运行 1-2 sprint 稳定后再切）
- **B-013** 邮件/短信发送幂等性（低优先级，发送链路已稳定后做）
- **B-019** 错误响应 `{"detail"}` → 与 Rust `{"error","service"}` 统一（等前端反馈是否需要）
- **B-024** `UserDAO.save()` 加 `session.merge()` 防 detached instance（防御性加固）
- **B-034** MongoDB 全量历史数据同步实现（A/B/C/D 四类；断点重试；migration 0006；CLI+API 双入口）。**设计稿已写，实现未做**。见 [mongodb-sync-design](./superpowers/specs/2026-06-07-mongodb-sync-design.md)
- **B-035** 管理端扩展：用户管理 + 统计 + 候选项 + 审计日志 + 导出 + 简单 Web UI。**设计稿已写，实现未做**。见 [admin-panel-design](./superpowers/specs/2026-06-07-admin-panel-design.md)
- **B-033** 删除 legacy-compat 路由层 `src/api/rest/legacy/`（2026-05-31 新增，保留旧 Rust gateway 扁平契约 `/user-token-status`，供与 Rust 部署共享的前端无改动对接 Python 后端，修复登录后 bounce 回登录页）。**移除条件**：① Rust gateway 下线（无部署再依赖扁平契约）且 ② 前端 REST 调用迁移到原生 `/api/v1/...` + 新响应 shape。与 B-019（错误响应 shape 统一）、`/server-time` 缺口同属 Rust→Python REST 契约收敛，宜一并处理。详见 `docs/migration/legacy-rest-compat.md`。

## 🟢 模块功能缺口（不在 B 编号体系内）

- **autocomplete CP 搜索**：`src/apps/autocomplete/dao.py` 的 `search_cps()` 仍 `return []`（角色/音乐已实现）；需从已提交 `cp.cp_list` JSON 提取唯一 CP 名
- **`GET /server-time` 端点**：旧 gateway 有，Python 侧未移植（低优先级）
- **scraper 测试**：18 站点全部移植但无测试（外部 HTTP 依赖，需 mock）

---

## 推荐的下一个 PR

**首选 `B-028` prod 部署通道**——当前最高优先级：main 推送也只部署到 TEST 环境，没有真正的生产发布路径，这是上线前的硬阻塞。先确认部署现状（是否人工发布 / 是否真没有 prod），再决定补 `deploy-prod.yml` 还是文档化现状。

**次选 `B-008` MongoDB → PG 回填脚本实现**——设计稿已就绪（`docs/superpowers/specs/2026-05-16-medium-priority-backlog-design.md`），独立 `scripts/` 目录不动主代码，是历史数据上线的前置。

**暖手任务**：`B-023`（5 分钟）、`B-022`（1 小时）、`B-011`（1 小时）适合在大 PR 之间穿插。

---

## 维护规则

- **新发现 follow-up：** 写进对应主题的源文档；在本表加一行；编号顺延 B-028, B-029...
- **某项完成：** 不删除——把"严重度"改为 ✅ 已完成 + 完成日期 + commit hash / PR #
- **三个状态分组**（🟢🟡🔴）随完成情况调整：依赖项落地后，相关项可以从 🔴 升到 🟡 或 🟢
- 本表过 50 项时考虑分类拆文件（按主题：security backlog / schema backlog / test backlog 等），但目前规模够小不必拆
