# CI/CD 流水线说明

> 用途：把仓库内 4 个 GitHub Actions workflow 的职责、触发条件、关键步骤一次说清，并记录最近的改动与遗留问题。
> 关联：[`docs/operations/aliyun-onboarding.md`](./aliyun-onboarding.md)、[`docs/superpowers/specs/2026-04-27-user-auth-implementation-report.md`](../superpowers/specs/2026-04-27-user-auth-implementation-report.md)

---

## 一、Workflow 总览

> ⚠️ YAML 里的「触发条件」与团队**实际工作约定**有差异，详见 §七。

| 文件 | YAML 触发 | 实际使用方式 | 作用 |
|---|---|---|---|
| `.github/workflows/pylint.yml` | 任意 push | 自动 | 跑 pylint，`--exit-zero`，**永不失败**——见 §五 F-cicd-1 计划清理 |
| `.github/workflows/deploy-test.yml` | push 到 `main`/`zfq_dev`/`zfq_dev_pipeline` + 这些分支的 PR + `workflow_dispatch` | **自动**（push/PR 落到上述分支即触发） | 测试环境主流水线 |
| `.github/workflows/deploy-prod.yml` | GitHub Release `released`/`published` + `workflow_dispatch` | **手动**（按团队约定不发 Release，仅靠 GitHub UI 的 "Run workflow" 触发） | 生产环境主流水线（含前端构建 + 回滚就绪） |
| `.github/workflows/deploy.yml` | GitHub Release `released`/`published` + `workflow_dispatch`（带 `environment=prod\|test` 选项） | **手动备用**（同上，只在 `deploy-prod.yml` 不适用时由 ops 手动触发） | "Deploy Backend Only"，与 deploy-prod 部分重叠 |

---

## 二、`deploy-test.yml`（测试环境主流水线）

### 2.1 Job 拓扑
```
lint  ──►  test  ──►  build-backend  ──►  deploy-test  ──►  notify
                          (push only)        (main/zfq_dev*)
```

### 2.2 关键步骤

| Job | 关键内容 |
|---|---|
| **lint** | Python 3.12 + flake8（`max-line-length=120`，当前 `\|\| true` 软门禁，**只会提示不会挡 PR**） |
| **test** | 起 `postgres:15-alpine` + `redis:7-alpine` service container，注入 `DATABASE_URL` / `REDIS_URL` / `JWT_SECRET_KEY` / `VOTE_*_ISO`；先跑 `alembic upgrade head` 把迁移真接 Postgres 烟测一遍，再跑 `pytest --cov=src` |
| **build-backend** | 多阶段 Dockerfile 的 `production` target → 推到 `ghcr.io/patchyvideo/thvote-backend:test`；启用 GHA cache |
| **deploy-test** | SSH 到测试服务器；写 `.env`；首次部署或检测到老 compose 时重写 `docker-compose.yml`；先 `up -d postgres redis` 等就绪，再 `docker-compose run --rm backend alembic upgrade head` 应用迁移，最后 `up -d backend` |
| **notify** | 简单回显成功/失败 |

### 2.3 测试环境环境变量（CI 注入到 `.env`）
来自 GitHub Secrets / Variables：

```env
POSTGRES_DB=thvote_test
POSTGRES_USER=thvote_test
POSTGRES_PASSWORD=${{ secrets.TEST_DB_PASSWORD }}
JWT_SECRET_KEY=${{ secrets.TEST_JWT_SECRET || 'dev-secret' }}
APOLLO_ENABLED=yes
APOLLO_META=${{ vars.APOLLO_META || 'http://apollo-configservice:8080' }}
APOLLO_ENV=fat
APOLLO_CLUSTER=fat
APOLLO_APP_ID=thvote-backend
APOLLO_ACCESS_KEY=${{ secrets.APOLLO_ACCESS_KEY_TEST }}
APOLLO_NAMESPACES=application
BACKEND_IMAGE=ghcr.io/patchyvideo/thvote-backend:test
```

`ALIYUN_PNVS_*` / `ALIYUN_DM_*` **不在 `.env` 里**——它们由 Apollo `application` namespace 提供，详见 §四。

---

## 三、`deploy-prod.yml`（生产环境主流水线，按约定手动触发）

```
confirm ──┬──► build-backend ──┐
          └──► build-frontend ─┴──► deploy-prod ──► rollback-ready
```

特点：
- 触发：YAML 写了 `release` 类型 `released` / `published` 与 `workflow_dispatch`；**团队约定不发 Release，实际仅靠 `workflow_dispatch`**（详见 §七）
- 多了**版本确认 + 前端构建 + 回滚就绪**步骤
- 前端从 `https://github.com/PatchyVideo/Touhou-Vote.git` clone 后构建
- 部署机器上把 secret 落盘到 `docker/secrets/{db_user,db_password,jwt_secret_key}.txt`，配合 Docker Secrets 使用
- **部署前先 backup PG**：`docker exec thvote-postgres-prod pg_dump ... > backup_pre_*.sql`
- 应用迁移：`docker-compose run --rm backend-prod alembic upgrade head`，**在 `up -d backend-prod` 之前**

---

## 四、Aliyun + Apollo 配置交付

我们的代码读取顺序：环境变量 / `.env` → Apollo namespace 覆盖（`src/common/apollo.py:load_apollo_overrides`）→ `Settings()` 实例化（`src/common/config.py`）。

**`ALIYUN_PNVS_*` 与 `ALIYUN_DM_*` 14 个字段** 应该写到 Apollo `application` namespace 里：

| Apollo Key | 值来源 |
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

具体接入步骤见 [`aliyun-onboarding.md`](./aliyun-onboarding.md)。

> ⚠️ 不要把 `*_ACCESS_KEY_SECRET` 与 `*_SMTP_PASSWORD` 写进仓库里的 `.env.test.example` / `.env.prod.example`，必须放 Apollo 的加密命名空间或 GitHub Secrets。CLAUDE.md §5 强制要求。

---

## 五、Follow-up（仍待处理）

| 编号 | 项目 | 优先级 |
|---|---|---|
| F-cicd-1 | `pylint.yml` 与 `deploy-test.yml` 的 lint 重复且都软门禁 → 删除 `pylint.yml`，把 deploy-test 的 `flake8 \|\| true` 改成硬失败 | 中 |
| F-cicd-2 | `deploy-prod.yml` 与 `deploy.yml` 都监听 `release`/`workflow_dispatch`。当前靠**团队约定不发 Release** 来回避并发部署（详见 §七），但 YAML 字面仍是脚枪 → 后续考虑去掉 `release:` 触发器或合并两个 workflow | 中（约定生效期间风险低，但任何人发 Release 即触发） |
| F-cicd-3 | `init_db()` 调用 `Base.metadata.create_all` 与 Alembic 并存。**已修复（2026-04-27）**：`src/main.py` 现在仅在 `DEBUG=true` 时调 `init_db()`，生产/CI 完全靠 `alembic upgrade head` | ✅ 已完成 |
| F-cicd-4 | `flake8` 改硬失败前先把现存告警清掉，避免把整条流水线一次性卡住 | 中 |
| F-cicd-5 | 测试覆盖率切到 `fail_under=80`（spec §九 F6 也提到） | 低 |

---

## 六、最近改动（2026-04-27）

| 改动 | 落点 |
|---|---|
| test job 在 pytest 之前跑 `alembic upgrade head` | `.github/workflows/deploy-test.yml` |
| deploy-test / deploy-prod / deploy 三处部署步骤都加 `docker-compose run --rm backend alembic upgrade head` | 三个 workflow |
| Dockerfile 的 development + production stage 都 `COPY alembic/` 与 `alembic.ini` | `Dockerfile` |
| test job 装 `fakeredis`（与 `requirements.txt` 行为一致，避免本地/CI 行为分裂） | `.github/workflows/deploy-test.yml` |

提交：`feat(ci): wire alembic upgrade head into test and deploy stages` 之后。

---

## 七、触发约定（YAML ≠ 团队工作流程）

> 这一节是**团队约定**的成文记录，不是 YAML 的客观描述。如果改了约定，请同步更新这里。

### 7.1 三个 workflow 的实际使用方式

| Workflow | 谁触发 | 触发方式 | 频率 |
|---|---|---|---|
| `deploy-test.yml` | **GitHub** 自动 | push / PR 落到 `main` / `zfq_dev` / `zfq_dev_pipeline` 时即触发 | 每次相关分支有提交 |
| `deploy-prod.yml` | **人** 手动 | GitHub UI → Actions → 选 workflow → "Run workflow" 按钮（即 `workflow_dispatch`） | 按发版节奏，不定期 |
| `deploy.yml`（备用） | **人** 手动 | 同上，仅在 `deploy-prod.yml` 不适用时使用 | 极少 |

### 7.2 为什么 prod 系列不用 `release` 自动触发

- 团队约定**不发 GitHub Release**——发版节奏由 ops 通过 GitHub UI 上的 "Run workflow" 按钮控制
- 这样可以选择**手动指定要部署的版本号**（`workflow_dispatch` inputs.version）或回滚到任意 commit SHA
- 避免「发了个 Release 当公告，结果两个 prod workflow 同时部署」的事故

### 7.3 YAML 里 `release:` 触发器为什么还留着

- 给将来「希望切换到 Release-driven 部署」留一个回退口子（届时只要团队改约定，YAML 不用动）
- 但**当前留着是个潜在的脚枪**：任何人（或某个自动化机器人）创建一个 GitHub Release 都会同时触发 `deploy-prod.yml` 和 `deploy.yml`，**导致两次并发 prod 部署**
- 见 §五 F-cicd-2

### 7.4 给新成员的明确指引

- ✅ **测试环境部署**：把代码 push 到 `main` / `zfq_dev` / `zfq_dev_pipeline`，自动触发 `deploy-test.yml`
- ✅ **生产环境部署**：去 GitHub → Actions → 选 "Deploy to Production"（即 `deploy-prod.yml`）→ "Run workflow" → 填版本号
- ❌ **不要在 GitHub 发布 Release**——除非你确认团队已经改了部署约定并同步更新了本文档
- ❌ **不要直接选 `deploy.yml`（"Deploy Backend Only"）跑 prod**，除非你确切知道为什么要绕开前端构建
- 紧急回滚见 `deploy-prod.yml` 末尾的 `rollback-ready` job 与 ops runbook（如有）

### 7.5 触发约定与代码不一致的处理

如果将来想让 YAML 与约定**字面一致**（即真正去掉 release 自动触发的脚枪），见 §五 F-cicd-2。改动很小：

```diff
 on:
-  release:
-    types: [released, published]
   workflow_dispatch:
     ...
```

但**改动不可逆**（恢复需要再次 PR）。当前选择**保留 YAML 灵活性 + 靠文档约束**，按团队偏好。
