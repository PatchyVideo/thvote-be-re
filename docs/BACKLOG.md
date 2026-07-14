# 后续开发 BACKLOG（单一仪表盘）

> 创建日期：2026-04-27
> 最后更新：2026-07-14（zfq_dev 合并进 main：B-039/B-040/B-041 后端全部进主线；三项前端仍待做）

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
| **B-032** ⚡ | 删除（或收紧）`alembic/env.py` 的 `_maybe_baseline_existing_schema`。它只按"表是否存在"自动 stamp、**不校验列是否匹配**，会**掩盖 schema 漂移**——2026-05-31 测试库 `user` 表缺 `phone_verified` 等列、登录全挂就是它造成的（残缺旧表被 stamp 成 0001，0001 的正确建表从未执行）。B-025 已移除 init_db 后门,该 shim 已无存在必要。**首选直接删除**(让 `alembic upgrade head` 老实从 0001 跑)+ 空库重建一次清除残留漂移;次选 stamp 前校验列匹配、不匹配则报错而非闷头 stamp。归属 B-025/B-026 DB 治理。 | 中 | 🟢 可立即做（B-025 已完成,前置解除） | `alembic/env.py:48-94` |

---

> **2026-05-30 对账说明：** `feat/user-and-verify` 已全部合入 `main`，原先「🟡 等本 PR merge」的依赖前提消失。下面按「现在还开放的项」重新分组，不再用「等 PR」维度。已完成项保留在上方状态表（标 ✅ + commit）。

## 🟢 现在可立即做（10 项，全部已解除阻塞）

按建议优先级排序：

| 编号 | 一句话 | 估时 |
|---|---|---|
| **B-028** ⚡ | 确认/补齐 prod 部署通道（当前 `deploy-test.yml` 是孤本，main push 也只到 test） | 1 天（视真实部署现状而定） |
| **B-032** ⚡ | 删除/收紧 `_maybe_baseline_existing_schema`（按表存在 stamp、不校验列，掩盖 schema 漂移；2026-05-31 登录全挂的根因）+ 空库重建清残留 | 半天（含空库重建验证） |
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
