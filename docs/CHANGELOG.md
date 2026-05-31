# thvote-be-re CHANGELOG

> 仓库级变更记录，按 CLAUDE.md §4 维护。日期格式 `YYYY-MM-DD`。
>
> 创建日期：2026-04-27
> 最后更新：2026-05-31（PNVS template_param 可配置 + CI 手动触发部署 + 登录配置文档）

## [2026-05-31] PNVS 短信模板参数可配置

### Fixed
- PNVS 之前写死 `template_param='{"code":"##code##"}'`,对含额外变量(如有效期 `min`)的短信模板会被阿里云判「模板内容与模板参数不匹配」(SMS_SEND_FAILED)。改为可配置 `ALIYUN_PNVS_TEMPLATE_PARAM`(默认仍为 `{"code":"##code##"}`,行为不变)。

### Added
- `Settings.aliyun_pnvs_template_param`(env `ALIYUN_PNVS_TEMPLATE_PARAM`)。模板有 `min` 等变量时填 `{"code":"##code##","min":"5"}`。

### 兼容性
- 向后兼容:未设置时维持原默认值。

---

## [2026-05-31] CI 手动触发部署 + 登录配置清单文档

### Changed
- `deploy-test.yml`:`build-backend` / `deploy-test` 现在也响应 `workflow_dispatch`（之前 deploy 仅限 push）。job `if` 改为显式校验依赖结果，`skip_tests=true` 时仍可构建/部署。
- 部署步骤改 `docker-compose up -d --force-recreate backend`：即使镜像未变也重建容器，使**改完 Nacos 配置后手动触发即可让配置生效**，无需 SSH 上服务器 `docker restart`。

### Added
- `docs/operations/login-config-checklist.md`:登录模块所需 Nacos 配置项**待填清单**（按登录方式分组、必填/可选、JSON 骨架、R-NACOS `:10848` 访问入口、阿里云参数获取指引）。

### Changed（文档）
- `docs/operations/nacos-config-center.md` §四:补 R-NACOS 双控制台（协议口 `:8848` vs 鉴权控制台 `:10848`）访问方式;注明测试环境 dataId 为 `thvote_be`（下划线）。
- `docs/operations/cicd-pipeline.md` §6.2:更新手动触发行为说明。

### 兼容性
- 无破坏:push 触发行为不变;新增的是手动触发可部署的能力。

---

## [2026-05-30] GraphQL 登录 mutation 桥接

### Added
- GraphQL `UserMutation`：`requestPhoneCode` / `requestEmailCode` / `loginPhone` / `loginEmail` / `loginEmailPassword`，包装现有 `UserService`，对齐前端 `LoginBox.vue` 既定契约。
- `LoginResult { user: VoterFE, sessionToken, voteToken }` GraphQL 类型。

### Changed
- `AppException` 增加可选 `error_message` / `upstream_response_string`（向后兼容）。
- PNVS 发送失败时透传阿里云上游 code/message（复刻 Rust `ServiceError` 诊断信息）。
- GraphQL 错误 `extensions` 复刻 Rust shape：`{service,url,error_kind,error_message,human_readable_message,upstream_response_string}`。

### 兼容性
- 纯增量：REST `/user/*` 与 submit/result GraphQL 行为不变。
- GraphQL schema 新增 5 个 mutation 字段，无破坏。

### 已知差异
- `login_email_password` 对"用户不存在"返回 `INCORRECT_PASSWORD`（防枚举），前端 `NOT_FOUND` 分支不触发——刻意保留。
- 老用户密码登录仍依赖 B-008 历史数据回填（未做）。

---

## [2026-05-30] 文档对账：BACKLOG / REFACTOR_TODO 与 main 同步

> 不涉及代码变更，仅修正两份"进度仪表盘"与 `main`（HEAD `d4a3247`，2026-05-19）的偏差。
> 背景：`BACKLOG.md` 停在 2026-05-12、`REFACTOR_TODO.md` 停在 2026-05-13，而 `feat/user-and-verify` 期间（05-13..05-17）完成的一批 backlog 已合入 main 但未回标。

### Changed
- **`docs/BACKLOG.md`**：状态表标记以下为 ✅ 已完成（附 commit）：B-003(`8724e39`)、B-004/009/012(`9684643`)、B-007 SSO(`19d659f`..`e19d941`)、B-014/015/016(`581102f`)、B-017(`ab7a642`)、B-018(`fe993e4`)、B-025(`76facaa`)、B-027(`6d73de6`)、B-029(`0e340e9`)、B-030(`fce832a`)。B-011/B-026 阻塞已解除（依赖项 B-007/B-025 完成）→ 移入「可立即做」。重写「🟢/🟡/🔴」分组（去掉已失效的"等 PR merge"维度）。
- **`REFACTOR_TODO.md`**：用户模块补 SSO 已落地；autocomplete 由 ❌ 修正为 ⚠️（角色/音乐已实现 ILIKE，仅 `search_cps()` 仍空）；scraper 头部 ⚠️→✅；migration 表补 0004（SSO 列）；重排「建议实施顺序」并修复一处 markdown 残缺块。

### Fixed（文档准确性）
- 修正 B-008 描述：此前列为"可立即做"，实为**仅设计稿完成、实现未做**（`scripts/` 仍空）。
- 修正 B-028：2026-05-19 的 3 个 `fix(ci)` 提交只是修 `deploy-test.yml` 的 YAML/包发现 bug，**未补 prod 部署通道**，此项仍开放且为当前最高优先级。

### 兼容性
- 无（纯文档）。

---

## [2026-05-12] 合入 zfq_dev 基础设施：Apollo→Nacos、移除 docker/、workflow 精简

> 合并提交：`c8a04d5 merge: bring zfq_dev infrastructure (Nacos + new deploy) into feat`
> 包含 zfq_dev 18 个 commit：`5414a0f` … `2ced1fd`

### Changed
- **配置中心 Apollo → Nacos**：
  - 删除 `src/common/apollo.py`
  - 新增 `src/common/nacos.py`（812 行，含配置中心 + naming service 双功能）
  - 重写 `src/common/config.py`：模块加载期 `_load_nacos_sync()` 同步拉取 Nacos 配置写入 `os.environ`（仅当 key 不存在时），再交给 Pydantic Settings 实例化
  - `Settings` 类新增 13 个 `NACOS_*` 字段（含服务注册的 IP/port/cluster/weight）
- **服务注册接入**：`src/main.py` lifespan 现在会 `start_nacos_watcher` + `register_service_to_nacos`；新增 `/admin/discover/{service_name}` 与 `/admin/discover-self` 两个排障端点
- **依赖管理收敛**：删除 `requirements.txt`，所有依赖统一进 `pyproject.toml`；新增 `nacos-sdk-python>=2.0.0`
- **健康检查降级**：`/health` 现在在 DB 不可用时返回 `db_status=unavailable`（HTTP 200），而非整体 500
- **Nacos 加载本地文件回退**：Nacos 拿不到配置时尝试读 `<repo_root>/<NACOS_DATA_ID>` 同名文件作为应急

### Removed
- `.github/workflows/deploy-prod.yml`（与 Apollo / 仓库内 docker-compose 强耦合的旧 prod workflow）
- `.github/workflows/deploy.yml`（备用 prod workflow，功能与 deploy-test.yml 重叠）
- `.github/workflows/pylint.yml`（软门禁 `--exit-zero` 永不失败，与 deploy-test.yml lint job 重复）
- 整个 `docker/` 目录（compose 文件、apollo SQL 521+464 行、bootstrap 脚本、测试环境脚本）
- 整个 `frontend/` 目录（Dockerfile.prod、nginx 配置）
- `QUICKSTART.md`（内容过时）
- `docs/REFACTOR_TODO.md`（与本次合并冲突，删除态胜出）
- `local_db/dev.db`（不该进 git 的本地 sqlite 文件）
- `requirements.txt`

### Added
- `docs/operations/nacos-config-center.md`：Nacos 接入说明（配置 + 服务注册，含 dataId 写法样例与 lifespan 行为）
- 部署机不再编排本地 postgres 容器，改用阿里云 RDS（仍保留 redis container 在 deploy 流程里）
- `__pycache__/` 加入 `.gitignore`（zfq_dev 误提交了一些 `.pyc`，本次合并时清理）

### 兼容性
- **破坏性**：`APOLLO_*` 环境变量不再被读取，必须改用 `NACOS_*`
- **破坏性**：仓库内 `docker/docker-compose*.yml` 不再存在；部署机需自维护 compose 文件（详见 `cicd-pipeline.md` §三）
- **破坏性**：没有独立 prod workflow——main 分支 push 走的也是 `deploy-test.yml`，部署目标仍是 TEST_SERVER_HOST（镜像 tag 区分为 prod vs test）。**这是 follow-up B-028**
- **配置迁移路径**：原 Apollo `application` namespace 里的 `ALIYUN_PNVS_*` / `ALIYUN_DM_*` 17 个字段需要全量复制到 Nacos（`DATA_ID=thvote-be`，`GROUP=DEFAULT_GROUP`），格式建议标准 JSON
- **运行时风险**：`src/common/config.py` 顶层 `_load_nacos_sync()` 是 import-time 阻塞调用——Nacos 故障会让所有 import 链挂掉（B-030）

### CI/CD
- 唯一保留的 workflow `deploy-test.yml` 仍有 `alembic upgrade head` 步骤（test 阶段烟测 + deploy 阶段应用迁移），未受影响
- 部署阶段写入 `.env` 的内容从 `APOLLO_*` 改为 `NACOS_*`

### Docs
- `docs/README.md`：删除 `REFACTOR_TODO.md` 入口；新增 `nacos-config-center.md` 入口
- `docs/CHANGELOG.md`：本节
- `docs/BACKLOG.md`：B-017 重写为 Nacos 视角；新增 B-028（prod workflow 缺失）/ B-029（部署机 compose 归属）/ B-030（Nacos import 阻塞）/ B-031（_parse_config_content 容错），状态总览范围改为 B-001..B-031
- `docs/operations/cicd-pipeline.md`：整篇重写（Workflow 总览从 4 → 1；新增 §三"与部署机的耦合"；§四配置交付从 Apollo 改 Nacos；§七记录本次改动）
- `docs/operations/aliyun-onboarding.md`：§四改写为 Nacos 投递路径；引用 `nacos-config-center.md`
- `docs/architecture/database-schema-management.md`：阶段 2 标 ✅ 已完成；§四操作手册改用 `pip install -e .`（不再 `requirements.txt`）；备注 QUICKSTART.md 已删

### Follow-up
- **B-028**（高）：补 prod 部署通道或确认现状
- **B-029**（中）：部署机 compose 文件归属文档化
- **B-030**（中）：Nacos import-time 阻塞改 lazy
- **B-031**（低）：约束 Nacos 配置写标准 JSON 后删 `_parse_config_content` 容错分支

### Fixed（追加）
- **alembic 首次部署到已有 DB**：`env.py` 加 `_maybe_baseline_existing_schema`，跑迁移前自动检测"已有 managed 表但无 alembic_version"的状态，自动 stamp 到合适的 revision（user 在 → 0001；raw_character 在 → 0002）。`alembic upgrade head` 现在对**任意状态的 DB 都是幂等**的——空 DB、祖传 schema、已托管的 DB 都能直接跑。Sentinel 表与对应 revision 维护在 `_SENTINELS` 元组里，未来加迁移时同步追加

---

## [2026-05-12] 重构进度整理 + 四项 BACKLOG bug 修复

### docs
- 新建 `REFACTOR_TODO.md`：全项目重构进度总览，含各模块移植状态（✅/⚠️/❌）、测试空白、建议实施顺序及与 BACKLOG 的交叉引用

---

## [2026-05-12] 四项 BACKLOG bug 修复 + 文档同步

### Fixed
- **B-006**：删除 `src/main.py` 中重复的 `logging.basicConfig` 块（第 24-30 行是第 14-20 行的完整拷贝）
- **B-002**：`src/apps/submit/router.py` `prefix="/v1"` 改为 `prefix=""`，消除与 `api_router`(`prefix="/api/v1"`) 叠加产生的 `/api/v1/v1/...` 异常路径；submit 端点现在正确挂载在 `/api/v1/character/` 等路径下

### Changed
- **B-005**：`src/common/middleware/rate_limit.py` 替换非原子限流实现（旧：`GET last_reset → GET tokens → 判断 → DECR`，存在 TOCTOU 竞态）为原子 `INCR + EXPIRE` 固定窗口计数器；Redis key 格式从 `rate-limit-{uid}-tokens` / `rate-limit-{uid}-last-reset` 统一为 `rate-limit-{uid}`

### Added
- **B-001**：`alembic/versions/0002_voting_tables.py`，把投票相关表纳入 Alembic 版本管理：
  - 活跃表：`raw_character`、`raw_music`、`raw_cp`、`raw_paper`、`raw_dojin`（含复合索引）
  - 遗留表：`character`、`music`、`cp`、`questionnaire`（仍在 db_model/ 但已不写入）

### 兼容性
- **B-002**：submit REST 端点路径变更（`/api/v1/v1/...` → `/api/v1/...`），若有直接调用旧路径的客户端需更新；GraphQL 调用不受影响（resolver 直接调用 service 层）
- **B-005**：Redis key 格式变更，旧限流状态自然失效；已有部署升级后当前窗口内的限流计数重置（无安全风险）
- **B-001**：已有部署（表已存在）首版本要求 `alembic stamp 0002`，**已在 2026-05-12 后续修复中自动化**（`alembic/env.py:_maybe_baseline_existing_schema` 自动检测并 stamp，无需手工 stamp）

### docs
- `docs/CHANGELOG.md`：`[Unreleased]` → `[2026-04-27]`，更新日期
- `docs/BACKLOG.md`：更新日期，各条目经代码核查均保持原状（B-001~B-027 均未完成）
- `docs/migration/user-manager.md`：更新日期，checkbox 经代码核查属实
- `docs/REFACTOR_TODO.md`：顶部加醒目过时警告，指向 BACKLOG、CHANGELOG、migration 文档

---

## [2026-04-27] feat/user-and-verify 分支（已合入主干）

> 工作期间：2026-04-27
> 包含 commits：`45d75b7` … `c75f552`（共 16 个）
> 判断依据（2026-05-12 核查）：`src/apps/user/` 目录已有完整源文件（router/service/dao/deps/schemas/models/utils），表明该分支内容已合入主干。

### Added
- 用户与认证模块（feat/user-and-verify 分支）
  - 接入阿里云号码认证服务（PNVS）作为短信验证码全托管方案
  - 接入阿里云邮件推送 DirectMail（SMTP）作为邮件验证码投递通道
  - `EmailCodeService`：本地 6 位码生成 + Redis 存取 + guard 防刷（120s）
  - `SmsCodeService`：薄封装 PNVS 的 `SendSmsVerifyCode` / `CheckSmsVerifyCode`
  - 11 个对齐 Rust 的认证端点 + 1 个 `GET /me` 替代旧 `GET /{user_id}`
  - `ActivityLog` 9 类事件落库（best-effort，不阻断主请求）
  - 登录成功签发 `vote_token`（投票期内 + 已验证 phone 或 email）
  - Alembic 数据库迁移工具引入，baseline migration 把 User + ActivityLog 纳入版本管理
  - 设计文档 `docs/superpowers/specs/2026-04-27-user-auth-design.md`

### Changed
- `vote_token` JWT 主体由 `vote_id` 改为 `user_id`，对齐 Rust 行为；`audience` 保持 `vote`
- 用户敏感端点接入既有速率限制中间件（5 req/60s 按 IP 或 user_id 配比，详见设计文档 §7.4）

### Removed
- 半成品旧端点：`POST /api/v1/user/login`、`POST /api/v1/user/login/email`、`POST /api/v1/user/register`、`GET /api/v1/user/{user_id}`、`DELETE /api/v1/user/{user_id}`
- 历史遗留目录 `src/app/`（仅有 .pyc，无源文件）
- 历史遗留空壳 `src/models/__init__.py`（实际模型在 `src/db_model/`）

### 兼容性
- **破坏性**：上述移除的旧端点如有外部调用方需切换到新端点
- **数据库**：首次部署需运行 `alembic upgrade head`；已有部署字段已对齐，无需回填
- **配置**：要求 `ALIYUN_PNVS_*` 与 `ALIYUN_DM_*` 环境变量就位（Apollo / .env），未配置时调用对应端点会得到 `ALIYUN_NOT_CONFIGURED`
- **依赖新增**：`alembic`、`alibabacloud_dypnsapi20170525`、`alibabacloud_tea_openapi`、`alibabacloud_tea_util`；测试依赖 `freezegun`、`fakeredis`
- **DB 约束变更**：`user.at_least_one_identifier` CHECK 约束放宽为 `removed = TRUE OR phone_number IS NOT NULL OR email IS NOT NULL`，以支持 `remove-voter` 软删除时清空 email/phone（Rust 行为对齐）。已有部署执行 `alembic upgrade head` 即可。

### Operations
- 新增 `docs/operations/aliyun-onboarding.md`：从零到上线的阿里云 PNVS + DirectMail 接入手册（账号/RAM/认证方案/域名验证/SMTP/smoke 验证 + 常见坑）
- 新增 `docs/operations/cicd-pipeline.md`：CI/CD 流水线说明（4 个 workflow 拓扑、Aliyun/Apollo 配置交付路径、follow-up）
- 新增 `docs/superpowers/specs/2026-04-27-user-auth-open-issues.md`：用户与认证模块已知问题与待办（U-1..U-15），按 PR 前已修复 / PR 前待修 / PR 后再做分组
- 新增 `docs/architecture/database-schema-management.md`：数据库 schema 管理现状诊断 + 4 阶段演进路线图（阶段 1 已完成 ✅；阶段 2 把投票相关表纳入 Alembic；阶段 3 移除 init_db 后门；阶段 4 持续纪律）

### Fixed
- **U-1**：`init_db()` 与 Alembic 并存导致 schema 漂移 — 默认部署不再调用 `Base.metadata.create_all`，仅 `DEBUG=true` 时为本地开发保留。生产/测试环境必须靠 `alembic upgrade head`（CI 已就位）
- **U-4**：`remove-voter` 软删除现在同步清除 `password_hash` 与 `legacy_salt`，避免被删用户的密码哈希残留在 DB 里成为撞库素材
- **U-V1**：`_maybe_sign_vote_token` 配置错误从 `logger.warning` 升到 `logger.error`，避免 `VOTE_*_ISO` 打错时所有用户静默拿空 vote_token、submit 全挂但运维无信号
- **U-16**：`EmailCodeService.send` 用 `SET NX EX` 原子化 guard，并发同邮箱不再发两封邮件
- **U-17**：mutation 端点（`update-*` / `remove-voter`）在 token 解码前先做 IP 级限流（30 req/60s），堵住"刷 garbage token 拿快速 401"绕过 per-user 限流的路径
- **U-19**：`pnvs_client` check 失败的错误码从 `SMS_SEND_FAILED` 改为 `SMS_VERIFY_FAILED`，语义对齐

### CI/CD
- `deploy-test.yml` test job 在 `pytest` 之前新增 `alembic upgrade head` 步骤，把 0001 baseline 用真 Postgres service 烟测
- `deploy-test.yml` / `deploy-prod.yml` / `deploy.yml` 三处部署步骤都加 `docker-compose run --rm backend alembic upgrade head`，并在执行前等待 Postgres 健康
- `Dockerfile` 的 development + production stage 都 `COPY alembic/` 与 `alembic.ini`，使容器内可执行迁移
- `deploy-test.yml` 测试依赖加 `fakeredis`（与 requirements.txt 保持一致）

### 兼容性补充
- 首次部署到已有数据库的实例：`alembic upgrade head` 会在 `alembic_version` 表不存在时尝试 `CREATE TABLE user`，**与既有 `user` 表冲突**。需要先 `alembic stamp head` 把现有 schema 标记为最新，再走后续 migration。详见 `docs/operations/cicd-pipeline.md` §五 F-cicd-3。

### Follow-up
见 `docs/superpowers/specs/2026-04-27-user-auth-design.md` §九 F1-F9。
