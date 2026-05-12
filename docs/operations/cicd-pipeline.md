# CI/CD 流水线说明

> 创建日期：2026-04-27
> 最后更新：2026-05-12（合入 zfq_dev：删除 `deploy-prod.yml` / `deploy.yml` / `pylint.yml`；Apollo→Nacos；移除仓库内 `docker/`）
>
> 用途：说清当前 GitHub Actions workflow 的职责、触发条件、关键步骤，并记录最近的改动与遗留问题。
> 关联：[`operations/aliyun-onboarding.md`](./aliyun-onboarding.md)、[`operations/nacos-config-center.md`](./nacos-config-center.md)、[`superpowers/specs/2026-04-27-user-auth-implementation-report.md`](../superpowers/specs/2026-04-27-user-auth-implementation-report.md)

---

## 一、Workflow 总览

> ⚠️ **重大变更（2026-05-12）**：原 4 个 workflow（`pylint.yml` / `deploy-test.yml` / `deploy-prod.yml` / `deploy.yml`）被精简为**只剩 1 个** `deploy-test.yml`。同时移除仓库内 `docker/` 目录、`requirements.txt`、Apollo 接入；改用 Nacos 配置中心。

| 文件 | 触发 | 作用 |
|---|---|---|
| `.github/workflows/deploy-test.yml` | push 到 `main` / `zfq_dev` + 这些分支的 PR + `workflow_dispatch` | **唯一**部署流水线（lint → test → build-backend → deploy-test → notify） |

**没有独立的 prod workflow** —— 见 §五 B-028（这是需要确认/补齐的事项）。

---

## 二、`deploy-test.yml`（当前唯一的部署流水线）

### 2.1 Job 拓扑

```
lint  ──►  test  ──►  build-backend  ──►  deploy-test  ──►  notify
                          (push only)        (main 或 zfq_dev 才部署)
```

### 2.2 关键步骤

| Job | 关键内容 |
|---|---|
| **lint** | Python 3.12 + flake8（`max-line-length=120`，仍是 `\|\| true` 软门禁 → 见 §五 B-027） |
| **test** | 起 `postgres:15-alpine` + `redis:7-alpine` service container，注入 `DATABASE_URL` / `REDIS_URL` / `JWT_SECRET_KEY` / `VOTE_*_ISO`；先跑 `alembic upgrade head` 把迁移用真 Postgres 烟测一遍，再跑 `pytest --cov=src` |
| **build-backend** | 多阶段 Dockerfile 的 `production` target → 推到 `ghcr.io/patchyvideo/thvote-backend:<tag>`；`<tag>` 为 `prod`（main 分支）或 `test`（zfq_dev 分支） |
| **deploy-test** | SSH 到测试服务器；`sparse-checkout` 拉部署机本地的 `docker/` 配置；写 `.env` 注入 Nacos 配置；启动 redis container、等 Postgres 就绪；`docker-compose run --rm backend alembic upgrade head` 应用迁移；最后 `docker-compose up -d backend` |
| **notify** | 简单回显成功/失败 |

### 2.3 部署阶段写入的 `.env`

CI 阶段从 GitHub Secrets / Variables 拼出来，落到部署机的 `$DEPLOY_DIR/.env`：

```env
# Nacos 接入（取代原 Apollo）
NACOS_ENABLED=true
NACOS_SERVER_ADDRS=${{ secrets.NACOS_SERVER_ADDRS }}
NACOS_NAMESPACE=${{ secrets.NACOS_NAMESPACE }}
NACOS_GROUP=${{ secrets.NACOS_GROUP || 'DEFAULT_GROUP' }}
NACOS_DATA_ID=thvote-be
NACOS_ACCESS_KEY=${{ secrets.NACOS_ACCESS_KEY }}
NACOS_SECRET_KEY=${{ secrets.NACOS_SECRET_KEY }}

# 服务注册（让其他服务通过 Nacos naming service 发现本服务）
NACOS_SERVICE_NAME=thvote-be
NACOS_SERVICE_IP=...        # 一般用部署机内网 IP
NACOS_SERVICE_PORT=8000

# DB（Aliyun RDS，仓库内不再有 postgres 容器编排）
POSTGRES_DB=thvote_test
POSTGRES_USER=thvote_test
POSTGRES_PASSWORD=${{ secrets.TEST_DB_PASSWORD }}

# JWT
JWT_SECRET_KEY=${{ secrets.TEST_JWT_SECRET || 'dev-secret' }}

# 镜像
BACKEND_IMAGE=ghcr.io/patchyvideo/thvote-backend:test
```

`ALIYUN_PNVS_*` / `ALIYUN_DM_*` **不在 `.env` 里**——它们由 Nacos 配置中心提供，详见 §四 与 `operations/nacos-config-center.md`。

### 2.4 镜像 tag 规则

`BACKEND_TAG = main 分支 ? 'prod' : 'test'`：

- push 到 `main` → 推 `ghcr.io/patchyvideo/thvote-backend:prod`
- push 到 `zfq_dev` → 推 `ghcr.io/patchyvideo/thvote-backend:test`

⚠️ 但**部署目标始终是 TEST_SERVER_HOST**（即使 tag 是 `prod`）。要么是历史遗留，要么 prod 部署其他途径完成 → B-028 待确认。

---

## 三、与部署机的耦合

仓库内不再维护 `docker/docker-compose*.yml`，但 deploy job 仍调用：

- `docker-compose up -d redis`
- `docker exec thvote-postgres pg_isready ...`（不要被名字误导：实际指向阿里云 RDS 还是本地 container，取决于部署机的 compose）
- `docker-compose run --rm backend alembic upgrade head`（对任何状态的 DB 都幂等——`env.py` 会自动 baseline 祖传 schema，详见 `architecture/database-schema-management.md`）
- `docker-compose up -d backend`

这些 `docker-compose` 命令读取的是**部署服务器上 `$DEPLOY_DIR` 目录里手工维护的 compose 文件**——不在仓库版本控制中。

**含义：**
- 仓库 push 不会带 compose 改动到部署机
- compose 文件谁来改、谁来同步是部署机维护者的责任
- 这是有意识的解耦（让生产敏感配置不进 git），但需要文档化 → 见 §五 B-029

---

## 四、配置交付路径（Nacos）

代码读取顺序：
```
环境变量 / .env  →  Nacos 配置中心（src/common/nacos.py:load_nacos_config）  →  Settings() 实例化（src/common/config.py）
```

> ⚠️ Nacos 加载发生在 **import time**：`src/common/config.py:46` 顶层调用 `_load_nacos_sync()`，会在 import 期阻塞做网络请求 → Nacos 故障会让全部 import 链挂掉。见 BACKLOG B-030。

**`ALIYUN_PNVS_*` 与 `ALIYUN_DM_*` 17 个字段**应写到 Nacos 配置中（`DATA_ID=thvote-be`，`GROUP=DEFAULT_GROUP` 或自定义）：

| Key（环境变量风格） | 值来源 |
|---|---|
| `ALIYUN_PNVS_ACCESS_KEY_ID` | RAM 子账号 |
| `ALIYUN_PNVS_ACCESS_KEY_SECRET` | RAM 子账号 |
| `ALIYUN_PNVS_ENDPOINT` | `dypnsapi.aliyuncs.com` |
| `ALIYUN_PNVS_REGION_ID` | `cn-hangzhou` |
| `ALIYUN_PNVS_SCHEME_NAME` | 阿里云控制台「认证方案管理」 |
| `ALIYUN_PNVS_SMS_SIGN_NAME` | 系统赠送签名 |
| `ALIYUN_PNVS_SMS_TEMPLATE_CODE` | 系统赠送模板 |
| `ALIYUN_PNVS_CODE_LENGTH` | `6` |
| `ALIYUN_PNVS_VALID_TIME` | `300` |
| `ALIYUN_PNVS_INTERVAL` | `120` |
| `ALIYUN_DM_ACCOUNT_NAME` | `noreply@<your-domain>` |
| `ALIYUN_DM_FROM_ALIAS` | `THVote` |
| `ALIYUN_DM_TAG_NAME` | （可选） |
| `ALIYUN_DM_SMTP_HOST` | `smtpdm.aliyun.com` |
| `ALIYUN_DM_SMTP_PORT` | `465` |
| `ALIYUN_DM_SMTP_USERNAME` | 同 `ACCOUNT_NAME` |
| `ALIYUN_DM_SMTP_PASSWORD` | 阿里云控制台单独设置 |

具体接入步骤见 [`aliyun-onboarding.md`](./aliyun-onboarding.md)；Nacos 自身的配置写法见 [`nacos-config-center.md`](./nacos-config-center.md)。

> ⚠️ 不要把 `*_ACCESS_KEY_SECRET` 与 `*_SMTP_PASSWORD` 写进仓库内的 `.env.test.example` / `.env.prod.example`，必须放 Nacos 加密命名空间或 GitHub Secrets。CLAUDE.md §5 强制要求。

---

## 五、Follow-up（仍待处理）

> 🎯 全部 follow-up 在 [`docs/BACKLOG.md`](../BACKLOG.md) 里有对应编号。本表保留 CI/CD 视角的细节。

| 编号 | 项目 | 优先级 |
|---|---|---|
| **B-027** | `pylint.yml` 已删除；剩下 `deploy-test.yml` 内 `flake8 \|\| true` 软门禁仍需改硬失败 | 中 |
| **B-028** | 没有独立 prod workflow——main push 也只走 `deploy-test.yml` 部署到 TEST_SERVER_HOST。要么补 `deploy-prod.yml`，要么确认 prod 通过其他方式（手工 / Nacos 控制） | **高** |
| **B-029** | 部署机上 `docker-compose.yml` 不在仓库——归属、版本管理、敏感字段处理需文档化 | 中 |
| **B-030** | Nacos import-time 阻塞加载——改成 lazy 或加超时熔断 | 中 |
| **B-031** | Nacos `_parse_config_content` 的 JS 风格 JSON 容错解析是隐式技术债 | 低 |
| **F-cicd-3** | `init_db()` + Alembic 并存。**已修复（2026-04-27）**：`src/main.py` 现在仅在 `DEBUG=true` 时调 `init_db()` | ✅ 已完成 |
| **B-025** | 移除 `init_db()` 后门彻底改 `ensure_schema_ready()`（B-001 已完成，阻塞解除） | 中 |
| **B-010** | 测试覆盖率切到 `fail_under=80` | 低 |

### 5.1 已删除的历史 workflow（仅做归档）

| 文件 | 删除时间 | 原因 |
|---|---|---|
| `.github/workflows/deploy-prod.yml` | 2026-05-12 合入 zfq_dev | 与 Apollo / 仓库内 docker-compose 强耦合，新部署模型不复用 |
| `.github/workflows/deploy.yml` | 2026-05-12 合入 zfq_dev | 同上；功能与 deploy-test.yml 重叠 |
| `.github/workflows/pylint.yml` | 2026-05-12 合入 zfq_dev | 软门禁 `--exit-zero` 永不失败，与 deploy-test.yml 的 lint job 重复 |

如需恢复 prod workflow，应基于当前 `deploy-test.yml` + Nacos 模型重写，**不要**回滚到 Apollo 版本。

---

## 六、触发约定

### 6.1 测试环境部署

push 到 `main` 或 `zfq_dev`（或对这两个分支开 PR）→ 自动触发 `deploy-test.yml` 完整流水线。

push 触发只在改动以下路径时生效：
- `src/**`、`pyproject.toml`、`Dockerfile`、`scripts/**`、`docker/**`（已删但触发器仍写着，无害）、`.github/workflows/deploy-test.yml`

PR 触发：上述分支的 PR 都会跑 lint+test+build，但 **不会** 触发 deploy-test job（job 内 `if` 限制为 push 事件）。

### 6.2 手动触发

`workflow_dispatch` 输入：`skip_tests: false/true`。

用途：紧急部署可以选跳过测试（**不建议**，仅救火）。

### 6.3 生产环境部署

**当前缺失。** B-028 待办。

如需立刻发 prod：
- 选项 A：手动 `docker pull ghcr.io/patchyvideo/thvote-backend:prod` 到 prod 机后手工 `docker-compose up`
- 选项 B：通过 Nacos 改 `DATA_ID=thvote-be` 让运行中的实例热加载（仅限非 schema 变更）

---

## 七、最近改动（2026-05-12 合入 zfq_dev）

| 改动 | 落点 |
|---|---|
| 删除 `pylint.yml` / `deploy-prod.yml` / `deploy.yml` | 不再仓内 |
| Apollo 集成（`src/common/apollo.py`）→ Nacos（`src/common/nacos.py`，812 行，含配置中心 + naming service） | `src/common/` |
| `requirements.txt` 移除，依赖收敛到 `pyproject.toml` | 根目录 |
| `docker/` 目录完全删除（compose / apollo SQL / bootstrap 脚本全部移除） | 不再仓内 |
| 本地 Postgres 容器移除，依赖阿里云 RDS | 部署机维护 |
| 健康检查增加异常处理，DB 不可用返回降级状态而非失败 | `src/main.py` `/health` |
| 启动期 Nacos 加载有本地文件回退 | `src/common/nacos.py` |

## 八、历史改动（2026-04-27 用户与认证 PR）

| 改动 | 落点 |
|---|---|
| test job 在 pytest 之前跑 `alembic upgrade head` | `.github/workflows/deploy-test.yml` |
| Dockerfile development + production stage 都 `COPY alembic/` 与 `alembic.ini` | `Dockerfile` |
| deploy 步骤加 `docker-compose run --rm backend alembic upgrade head` | `deploy-test.yml`（已删 workflow 不再适用） |

提交：`feat(ci): wire alembic upgrade head into test and deploy stages` 及合入 zfq_dev 后的 workflow 删除。
