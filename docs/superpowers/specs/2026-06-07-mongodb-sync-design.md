# MongoDB 全量历史数据同步 — 设计稿

> 创建日期：2026-06-07
> 最后更新：2026-06-07

## 一、背景与目标

thvote 后端已从 Rust + MongoDB 迁移至 Python + PostgreSQL。用户账号（`thvote_users.voters`）的迁移方案（B-008）已有设计稿，但未实现，且范围仅覆盖用户表。

本文档将迁移范围扩展为**全量**：3 个 MongoDB 数据库、24 个集合中与历史年度投票相关的数据全部同步至 PostgreSQL，并在管理端提供可视化触发与进度追踪。

### 数据来源

| MongoDB 数据库 | 说明 |
|---|---|
| `thvote_users` | 用户账号、审计日志 |
| `submits_v1` | 历史原始投票提交 |
| `submits_v1_final` | 历史最终排名、候选项列表 |

### 同步范围（A/B/C/D 四类）

| 类别 | MongoDB 集合 | PostgreSQL 表 |
|---|---|---|
| A 用户账号 | `thvote_users.voters` | `user` |
| B 原始提交 | `submits_v1.raw_character/music/cp/work/paper/dojin` | `raw_character/music/cp/work/paper/dojin` |
| C 最终排名 | `submits_v1_final.final_ranking_char/music` | `final_ranking` |
| D 候选项 | `submits_v1_final.chars/musics` | `candidate_character/music` |

**不迁移**：`voter_logs`（格式与现有 `activity_log` 不兼容）、所有 `cache_*`/`covote_*`/`global_stats`/`completion_rates`/`paper_result` 集合（均可从原始数据重算）。

---

## 二、架构设计

### 模块布局

```
src/apps/admin/
  sync/
    __init__.py
    runner.py        # 各集合的映射函数 + 批次写入逻辑
    progress.py      # Redis 进度读写（已处理数 / 总数 / 错误数）
    checkpoint.py    # 断点记录与恢复（Redis 存 last_id per collection）
  service.py         # 新增 SyncService（启动 / 取消 / 状态查询）
  models.py          # 新增 SyncRunLog ORM 模型

scripts/
  sync_from_mongodb.py   # CLI 入口，复用 runner.py 逻辑，支持离线运行
```

### 执行流程

```
POST /admin/sync/start
  │
  ├─ 校验 MONGODB_URI 已配置，否则 503
  ├─ 创建 SyncRunLog（status=running，生成 run_id UUID）
  ├─ 写 Redis sync:current_run = run_id
  └─ 启动 FastAPI BackgroundTask
       │
       ├─ 依次处理各集合（按 A→B→C→D 顺序）
       │    ├─ 读 checkpoint Redis key 获取 last_id（续跑时跳过已处理数据）
       │    ├─ 批次查询 MongoDB（{ _id: { $gt: last_id } }，按 _id 升序）
       │    ├─ 映射字段 → 批量 INSERT … ON CONFLICT DO NOTHING
       │    ├─ 更新 Redis progress（processed / total / errors）
       │    ├─ 更新 checkpoint last_id
       │    └─ 轮询 Redis 取消信号，若收到则 status=cancelled 退出
       │
       └─ 更新 SyncRunLog（status=completed/failed，写统计数字）
```

### 断点重试

- 每个集合的断点：`sync:checkpoint:{run_id}:{collection}` = 上批最后 `_id` hex
- `POST /admin/sync/retry/{run_id}` 读断点后继续，从中断位置重跑
- 所有插入使用 `ON CONFLICT DO NOTHING` / `ON CONFLICT (uq_key) DO NOTHING`，重跑绝对安全

---

## 三、Schema 变更（migration 0006）

### 3.1 各 raw 表新增 `legacy_mongo_id` 列

适用于：`raw_character`, `raw_music`, `raw_cp`, `raw_paper`, `raw_dojin`

```sql
ALTER TABLE raw_xxx ADD COLUMN legacy_mongo_id VARCHAR(24) UNIQUE;
```

- 新后端写入的数据此列为 `NULL`（NULL 不违反 UNIQUE 约束）
- 历史迁移数据写入 MongoDB `_id` hex，用于幂等判断

### 3.2 新增 `raw_work` 表

旧后端 `submits_v1.raw_work` 集合（作品类）在新后端没有对应表，需新建：

```python
class RawWorkSubmit(Base):
    __tablename__ = "raw_work"
    id            # Integer PK autoincrement
    vote_id       # String(255), index
    attempt       # Integer nullable
    created_at    # DateTime(timezone=True)
    user_ip       # String(255)
    additional_fingreprint  # String(1024) nullable
    payload       # JSON
    legacy_mongo_id  # String(24) UNIQUE nullable
```

### 3.3 新增 `sync_run_log` 表

```python
class SyncRunLog(Base):
    __tablename__ = "sync_run_log"
    id            # Integer PK autoincrement
    run_id        # String(36) UNIQUE (UUID)
    started_at    # DateTime(timezone=True)
    completed_at  # DateTime(timezone=True) nullable
    status        # String(16): running / completed / failed / cancelled
    collections   # JSON: list of collection names processed
    total_docs    # Integer
    inserted      # Integer
    skipped       # Integer
    errors        # Integer
    initiated_by  # String(8): "api" or "cli"
```

---

## 四、字段映射

### A. `thvote_users.voters` → `user`

| MongoDB | PostgreSQL | 备注 |
|---|---|---|
| `_id` (ObjectId) | `id` (String) | `str(oid)` |
| `phone` | `phone_number` | |
| `phone_verified` | `phone_verified` | |
| `email` | `email` | |
| `email_verified` | `email_verified` | |
| `password_hashed` | `password_hash` | |
| `salt` | `legacy_salt` | |
| `created_at` | `register_date` | BSON DateTime → aware datetime |
| `signup_ip` | `register_ip_address` | None → `""` |
| `qq_openid` | `qq_openid` | |
| `pfp` | `pfp` | |
| `thbwiki_uid` | `thbwiki_uid` | |
| `removed` | `removed` | None → False |

幂等：`ON CONFLICT (id) DO NOTHING`

### B. `submits_v1.raw_*` → raw 表

适用于全部 6 个 raw 集合：

| MongoDB | PostgreSQL | 备注 |
|---|---|---|
| `_id` | `legacy_mongo_id` | 幂等 key |
| `meta.vote_id` | `vote_id` | |
| `meta.attempt` | `attempt` | |
| `meta.created_at` | `created_at` | |
| `meta.user_ip` | `user_ip` | |
| `meta.additional_fingreprint` | `additional_fingreprint` | |
| `doc.characters` / `doc.music` / 等 | `payload` (JSON) | 直接存数组 |
| `doc.papers_json` | `papers_json` (Text) | 仅 raw_paper |

幂等：`ON CONFLICT (legacy_mongo_id) DO NOTHING`

每条 MongoDB 文档是一次提交（含 attempt），逐条插入，保留全部历史 attempt。

### C. `submits_v1_final.final_ranking_char/music` → `final_ranking`

| MongoDB | PostgreSQL | 备注 |
|---|---|---|
| `name` | `name` | |
| `vote_year` | `vote_year` | |
| `rank` | `rank` | |
| `vote_count` | `vote_count` | |
| `first_vote_count` | `first_vote_count` | |
| `first_vote_percentage` | ❌ 丢弃 | PG 表无此列 |
| `vote_percentage` | ❌ 丢弃 | 可从 vote_count/total 重算 |
| collection 名 | `category` | `_char` → "character"，`_music` → "music" |

幂等：`ON CONFLICT (vote_year, category, rank) DO NOTHING`

### D. `submits_v1_final.chars/musics` → `candidate_character/music`

| MongoDB | PostgreSQL（character） | PostgreSQL（music） | 备注 |
|---|---|---|---|
| `name` | `name` | `name` | |
| `origname` | `name_jp` | `name_jp` | |
| `kind[0]` | `type` | `type` | 取第一个元素；`kind` 为空时写 `""` |
| `work[0]` | `origin` | ❌ 无此列 | 取第一个元素 |
| `date` (int) | `first_appearance` (str) | `first_appearance` | `str(date)` |
| `album` | ❌ 无此列 | `album` | |

幂等：`ON CONFLICT (vote_year, name) DO NOTHING`

---

## 五、配置注入

通过环境变量 / Nacos 注入，不写入 `.env.*.example`（属于运维配置）：

```
MONGODB_URI=mongodb://user:pass@host:27017
MONGODB_DB_USERS=thvote_users       # default: thvote_users
MONGODB_DB_SUBMITS=submits_v1       # default: submits_v1
MONGODB_DB_RESULTS=submits_v1_final # default: submits_v1_final
MONGO_BATCH_SIZE=500                # default: 500
```

`Settings` 中新增可选字段（均为 `Optional[str] = None`）。`mongodb_uri` 为 None 时，同步端点返回 `503 MONGODB_NOT_CONFIGURED`。

---

## 六、HTTP 端点

全部需要 `X-Admin-Secret` header。

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/admin/sync/start` | 启动同步；body 指定 `collections`（默认全部）和 `batch_size` |
| `GET` | `/admin/sync/status` | 当前运行进度（Redis 读取） |
| `GET` | `/admin/sync/history` | 历史运行记录（`sync_run_log` 表分页） |
| `POST` | `/admin/sync/retry/{run_id}` | 从断点续跑指定运行 |
| `POST` | `/admin/sync/cancel` | 取消当前运行（写 Redis 取消信号） |

### 进度响应结构（`GET /admin/sync/status`）

```json
{
  "run_id": "uuid",
  "status": "running",
  "current_collection": "raw_character",
  "collections_done": ["voters"],
  "processed": 12500,
  "total": 45000,
  "inserted": 12480,
  "skipped": 15,
  "errors": 5
}
```

---

## 七、CLI 入口

```bash
# 全量同步
MONGODB_URI=... DATABASE_URL=... python scripts/sync_from_mongodb.py

# 仅同步用户
python scripts/sync_from_mongodb.py --collections voters

# 断点续跑
python scripts/sync_from_mongodb.py --resume-run-id <uuid>

# 干跑（不写 PG）
python scripts/sync_from_mongodb.py --dry-run --collections raw_character
```

---

## 八、错误处理

- 单条映射失败：记录到 `migrate_errors.jsonl`（追加写），不中断批次
- 批次连接失败：指数退避重试 3 次，仍失败则标记 `status=failed` 退出
- 取消信号：每批次检查 Redis `sync:cancel:{run_id}` key，存在则 graceful exit

---

## 九、测试策略

| 层次 | 覆盖内容 |
|---|---|
| unit | 每个集合的 `map_*_to_row()` 函数：满字段、缺字段、边界值（None→默认值、BSON DateTime→aware datetime） |
| unit | `progress.py`、`checkpoint.py` 的 Redis 读写（fakeredis mock） |
| unit | CLI 参数解析 |
| integration | `SyncService.start_sync()` 端到端：mock MongoDB cursor + 真实 sqlite，验证插入数量与幂等性 |
| contract | `POST /admin/sync/start` 返回 202；`GET /admin/sync/status` 结构正确 |

---

## 十、关联文档

- B-008 原始方案：[`docs/superpowers/plans/2026-05-16-mongodb-migration.md`](../plans/2026-05-16-mongodb-migration.md)（用户表映射细节）
- 管理端设计：[`docs/superpowers/specs/2026-06-07-admin-panel-design.md`](./2026-06-07-admin-panel-design.md)
- BACKLOG 追踪：[B-008](../../BACKLOG.md)
