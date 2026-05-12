# 数据库 Schema 管理 — 现状与演进路线图

> 创建日期：2026-04-27
> 最后更新：2026-04-27
>
> 触发：本次 PR (`feat/user-and-verify`) 引入 Alembic，但只覆盖 user + activity_log，与既有 `init_db()` create_all 共存，状态混杂。本文记录现状、目标态、和分阶段演进 TODO。

---

## 一、现状（混杂，**临时**）

```
        ┌─────────────────────────────────┐
        │  src/db_model/*.py  (Base)      │ ← schema 真理
        └─────────────────────────────────┘
                    │
        ┌───────────┴────────────┐
        ▼                        ▼
  Alembic 0001              init_db() create_all
  ─────────────             ─────────────────────
  user                      所有 model 里的表
  activity_log              （含 user 的副本路径）
        │                        │
        ▼                        ▼
  生产 / CI 部署             仅 DEBUG=true 时跑
                             （本地开发后门）
```

**这是有意识的折中**——把全部表纳入 Alembic 是独立工作，不在用户与认证 PR 范围内。

---

## 二、目标态（行业惯例）

**Alembic 单一真理，应用永不动 schema。**

```
开发者首次进项目：
  alembic upgrade head     ← 唯一的 schema 命令
  uvicorn ...

每次改 model：
  alembic revision --autogenerate -m "..."
  # 审 migration 文件
  alembic upgrade head
  git add alembic/versions/...

CI / Deploy：
  alembic upgrade head → start backend
  应用代码：从不调 create_all
```

测试代码用 `Base.metadata.create_all` 是**唯一例外**（in-memory sqlite 一次性 fixture，不进生产路径）。

---

## 三、演进 TODO（按阶段，每阶段独立 PR）

> 🎯 阶段 2/3/4 在 [`docs/BACKLOG.md`](../BACKLOG.md) 里编号为 **B-001** / **B-025** / **B-026**，配有依赖关系与并行度。本表保留每阶段的详细操作步骤。

### 阶段 1 ✅ 已完成（本 PR `feat/user-and-verify`）
- [x] `user` + `activity_log` 写入 Alembic baseline `0001`
- [x] CI test job 在 pytest 之前 `alembic upgrade head`
- [x] CI deploy job 在启动 backend 之前 `docker-compose run --rm backend alembic upgrade head`
- [x] Dockerfile bundle `alembic/` + `alembic.ini`
- [x] `init_db()` 默认不再调用，仅 `DEBUG=true` 时为本地开发保留（`src/main.py` lifespan）
- [x] CHECK 约束放宽允许软删行同时 NULL email/phone

### 阶段 2 🟡 待做（spec §九 F-impl-5）—— 把投票相关表纳入 Alembic

**范围：** `raw_character_submit` / `raw_music_submit` / `raw_cp_submit` / `raw_paper_submit` / `raw_dojin_submit` / `character` / `music` / `cp` / `questionnaire`

**TODO：**
- [ ] 跑 `alembic revision --autogenerate -m "baseline voting tables"` 生成 `0002_*.py`
- [ ] **手工审 autogenerate 生成的 migration**——重点检查：
  - [ ] partial index（`postgresql_where`）有没有正确生成
  - [ ] CHECK 约束有没有
  - [ ] `server_default`（如 `func.now()`）有没有
  - [ ] 列长度（String(N)）有没有跟 model 对齐
  - [ ] FK 关系是否正确
- [ ] 在测试 PG 上**先做 `alembic stamp 0001` 后再 `alembic upgrade head`** 验证已有部署的升级路径不会冲突
- [ ] 写一份 release note 给 ops：「升级到 0002 之前必须 `alembic stamp 0001`」
- [ ] 更新 `docs/migration/user-manager.md` 标记 F-impl-5 完成
- [ ] 更新本文 §三阶段 2 状态为 ✅

**风险点：** 已有 raw_* 表里有真实投票数据。`alembic upgrade head` 不能盲跑，必须先 stamp。

### 阶段 3 🟢 待做（阶段 2 之后）—— 移除 `init_db()` 与 DEBUG 后门

**TODO：**
- [ ] 写一个 `ensure_schema_ready()` 函数替代 `init_db()`：
  - [ ] 检查 `alembic_version` 表存在
  - [ ] 检查 head revision == `ScriptDirectory.from_config(...).get_current_head()`
  - [ ] 不一致就 `raise RuntimeError("Schema not at head: please run alembic upgrade head")`
  - [ ] **不自动建表、不自动迁移**
- [ ] `src/main.py` lifespan 改为调 `ensure_schema_ready()`，删掉 `_is_debug_mode()` 与 `init_db()` 调用
- [ ] `src/common/database.py` 删掉 `init_db()` 函数（或保留为 dev 脚本但不在 lifespan 调用）
- [ ] 更新所有用到 `DEBUG=true` 启动的本地文档（QUICKSTART.md 等）
- [ ] 新增 `docs/operations/first-time-setup.md`：明示「clone → install → alembic upgrade head → start」
- [ ] 更新本文 §三阶段 3 状态为 ✅

**收益：** 应用启动时不再有"自动建表"这个隐藏行为，schema 状态完全由 Alembic 管。

### 阶段 4 🔵 持续纪律（无终点）

**TODO（一次性建好后持续维护）：**
- [ ] PR 模板新增一行：「[ ] 我修改了 model，是否需要 alembic revision？」
- [ ] CI 加一个 check job：跑 `alembic check`（dry-run autogenerate），如果发现 model 与最新 migration 不一致就 fail
- [ ] CI 加一个 check：如果 PR diff 改了 `src/db_model/*.py` 但没新增 `alembic/versions/*.py`，fail
- [ ] 部署文档强调：`alembic upgrade head` 之前先 `pg_dump` 备份（`deploy-prod.yml` 已有，确认 `deploy-test.yml` 也补一份）

---

## 四、给当下新人的临时操作手册

阶段 1 落地后，阶段 2 还没做之前，**首次部署到全新数据库**的步骤：

```bash
# 1. clone & 装依赖
git clone ...
cd thvote-be-re
pip install -r requirements.txt

# 2. 让 Alembic 建 user + activity_log（必须，生产/测试都要做）
alembic upgrade head

# 3. 让 create_all 建剩下的投票相关表（仅本地，临时）
DEBUG=true uvicorn src.main:app --reload   # 启动一次，自动跑 init_db()
# 之后可以关掉 reload，正常跑 DEBUG=false

# 4. 验证
psql ... -c "\dt"   # 应该能看到 user / activity_log / raw_* / character / music / ...
psql ... -c "SELECT version_num FROM alembic_version;"   # 应该是 0001
```

**生产 / 测试 CI 部署：** 不需要 DEBUG=true，因为 raw_* 等表在已有部署里**早就存在**。新一轮发布只是 `alembic upgrade head` 把 user/activity_log 拉到 0001。

阶段 2 落地后，本表第 3 步可以删除，所有表都靠 Alembic。

---

## 五、相关文档

- 本表 §三 阶段 1 详细：[`docs/superpowers/specs/2026-04-27-user-auth-design.md`](../superpowers/specs/2026-04-27-user-auth-design.md) §五.2
- 本表 §三 阶段 2 跟踪：spec §九 F-impl-5
- CI 流水线：[`docs/operations/cicd-pipeline.md`](../operations/cicd-pipeline.md)
- 已知问题清单：[`docs/superpowers/specs/2026-04-27-user-auth-open-issues.md`](../superpowers/specs/2026-04-27-user-auth-open-issues.md) U-1

---

## 六、维护规则

- 每完成一个 TODO 把 `[ ]` 改成 `[x]`，不要删除——保留追溯
- 每完成一个阶段把状态标识从 🟡/🟢/🔵 改成 ✅
- 阶段 2 / 3 的 PR 直接引用本文，避免每次 PR 重新论证 schema 治理思路
- 新发现的 TODO 加进对应阶段；如果是新主题，加阶段 5
