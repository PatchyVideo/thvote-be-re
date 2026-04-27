# CI/CD 流水线说明

> 用途：把仓库内 4 个 GitHub Actions workflow 的职责、触发条件、关键步骤一次说清，并记录最近的改动与遗留问题。
> 关联：[`docs/operations/aliyun-onboarding.md`](./aliyun-onboarding.md)、[`docs/superpowers/specs/2026-04-27-user-auth-implementation-report.md`](../superpowers/specs/2026-04-27-user-auth-implementation-report.md)

---

## 一、Workflow 总览

| 文件 | 触发 | 作用 | 状态 |
|---|---|---|---|
| `.github/workflows/pylint.yml` | 任意 push | 跑 pylint，`--exit-zero`（不会失败） | ⚠️ 与 `deploy-test.yml` 的 lint 重复，建议合并；见 §五 follow-up |
| `.github/workflows/deploy-test.yml` | push 到 `main`/`zfq_dev`/`zfq_dev_pipeline` + PR + 手动 | 测试环境主流水线 | ✅ |
| `.github/workflows/deploy-prod.yml` | release 发布 + 手动 | 生产环境（含前端构建 + 回滚就绪） | ✅ |
| `.github/workflows/deploy.yml` | release + 手动 | "Deploy Backend Only"，与 deploy-prod 部分重叠的备用入口 | ⚠️ 两条 release 路径同时存在，需要确认意图；见 §五 follow-up |

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

## 三、`deploy-prod.yml`（release 触发）

```
confirm ──┬──► build-backend ──┐
          └──► build-frontend ─┴──► deploy-prod ──► rollback-ready
```

特点：
- 触发：`release` 类型 `released` / `published` 或 `workflow_dispatch`
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
| F-cicd-2 | `deploy-prod.yml` 与 `deploy.yml` 都监听 `release`/`workflow_dispatch`，可能并发部署 → 二选一保留 | 高（重复部署风险） |
| F-cicd-3 | `init_db()` 调用 `Base.metadata.create_all` 与 Alembic 并存，存在冲突风险（create_all 会创建 alembic_version 之外的"野表状态"）→ 评估是否在 lifespan 移除 `init_db()` 调用 | 中 |
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
