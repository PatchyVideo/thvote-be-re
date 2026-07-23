# Work Table 重构 — 测试修复交接文档

> 创建日期：2026-07-21
> 交接对象：后端 agent
> 前置 spec：`docs/superpowers/specs/2026-07-21-work-table-unified-design.md`
> 前置 plan：`docs/superpowers/plans/2026-07-21-work-table-unified.md`

## 一、背景

已完成的代码改动：

| 改动 | 文件 | commit |
|---|---|---|
| Migration 重写 | `alembic/versions/12a5f2e6dbed_voteable_cross_year_stable_id.py` | `b8e64c7` |
| Work 模型 + voteable work_id FK | `src/db_model/work.py`, `voteable.py`, `__init__.py` | `3b357a9` |
| VoteObjects DAO — JOIN work + filterMeta | `src/apps/vote_objects/dao.py` | `b9ab141` |
| Admin Work CRUD + 缓存 | `src/apps/admin/work_service.py`, `router.py` | `879e4da` |
| Admin UI WorksView | `admin-ui/src/views/WorksView.vue`, `api/works.ts`, `router.ts` | `d965e3c` |
| AutocompleteDAO — JOIN voteable + work | `src/apps/autocomplete/dao.py` | `1da35c6` |
| ComputeDAO 适配 — voteable_id/name→join | `src/apps/result/compute_dao.py` | `1da35c6` |
| Candidate service 适配 | `src/apps/admin/candidate_service.py` | `1da35c6` |
| 所有测试更新 | `tests/**` | `1da35c6` |

## 二、数据模型现状

迁移 **尚未在数据库执行**。`create_all` 创建的是新 schema：

```
work: id, name, type, created_at
voteable_character: id, name, name_jp, type, first_appearance, work_id(FK→work), aliases, old_id, created_at
voteable_music:     id, name, name_jp, type, first_appearance, work_id(FK→work), aliases, old_id, created_at
candidate_character: id, vote_year, voteable_id(FK→voteable_character)
candidate_music:     id, vote_year, voteable_id(FK→voteable_music)
final_ranking:       id, vote_year, category, rank, name, vote_count, first_vote_count, voteable_id
```

**关键：candidate_* 表只有 `id, vote_year, voteable_id`。`name`, `origin`, `album`, `name_jp`, `type`, `first_appearance`, `merged_into` 全部删除/搬到 voteable。**

## 三、已知的代码问题

### 3.1 compute.py — 使用旧 CandidateMeta 字段

`src/apps/result/compute.py:161-165`:

```python
"origin": (meta.origin if meta else "") or "未知",
"album": (meta.album if meta else "") or "",
"name_jp": (meta.name_jp if meta else "") or "",
```

`CandidateMeta` dataclass 需要检查：`meta.origin` / `meta.album` 是否存在？如果存在，这些值从哪里来？

### 3.2 compute_dao.py — load_char_candidates / load_music_candidates

需要确认这两个函数是否 JOIN voteable 获取 name/origin/album。如果没 JOIN，`CandidateMeta` 构建会失败。

### 3.3 compute_dao.py — load_historical

使用 `FinalRanking.name` 匹配，但历史对比现在应该用 `FinalRanking.voteable_id`。

### 3.4 compute_dao.py — save_final_ranking

第 121 行: `FinalRanking.name == entry["name"]` — 仍然按 name 去重。可以保持（name 列还在 final_ranking 表），但应考虑是否应该用 voteable_id。

### 3.5 result/service.py

`query.category, query.name, query.vote_year` — query 对象可能有 `.name` 属性，需确认 Query schema 是否仍然有 name 字段。

### 3.6 测试中可能还有旧列引用

用以下命令搜索所有测试文件中对已删除列的引用：

```bash
grep -rn "\.origin\|\.album\|\.name_jp\|\.merged_into\|CandidateCharacter(\|CandidateMusic(" tests/
grep -rn "name.*origin\|origin.*name" tests/ | grep -v "origin_guard"
```

## 四、执行步骤

1. **先拉取最新代码**
```bash
git checkout zfq_dev
git pull origin zfq_dev
```

2. **运行全部测试看现状**
```bash
pytest tests/ -x --tb=short 2>&1 | tail -80
```

3. **按优先级修复**

- 优先级 1：`test_vote_objects.py` — 核心接口（应已通过）
- 优先级 2：`test_autocomplete.py` — DAO（应已通过）
- 优先级 3：`test_candidate_*.py` — admin 候选管理
- 优先级 4：`test_sync_mapping.py` — MongoDB 同步
- 优先级 5：compute 相关测试
- 优先级 6：其他合约测试

4. **修复原则**

- 测试中需要插入数据时：先建 work → 再建 voteable → 再建 candidate（用 voteable_id）
- 断言中不要引用 `origin`/`album`（已删除），改用 `workIds`/`workTypes`/`filterMeta`
- `candidate_field_specs()` 现在只返回 `voteable_id`
- `validate_items()` 校验 `voteable_id` 不再校验 `name`- ORM 模型 `CandidateCharacter`/`CandidateMusic` 不再能通过 `r.name`/`r.origin` 访问

## 五、数据库连接

（请补充 RDS 连接信息，以便本地直连测试）

```
DB_HOST=
DB_PORT=
DB_NAME=
DB_USER=
DB_PASSWORD=
```

## 六、结果

修复完成后：
```bash
pytest tests/ -v --tb=short
```

预期：全部 PASS。flake8 也应通过：
```bash
flake8 src/ --max-line-length=88
```
