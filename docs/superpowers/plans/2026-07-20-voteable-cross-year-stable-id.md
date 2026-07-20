# Voteable 跨年投票对象 — 实现计划

> 创建日期：2026-07-20
> 关联 spec：`docs/superpowers/specs/2026-07-20-voteable-cross-year-stable-id-design.md`
> 关联契约：`docs/api/voteable-api-contract.md`
> 分支：`zfq_dev`

---

## 任务总览

| # | 任务 | 预估 | 依赖 |
|---|---|---|---|
| 1 | Alembic migration | 小 | — |
| 2 | DB Model | 小 | 1 |
| 3 | VoteObjects DAO/Service 改造 | 中 | 2 |
| 4 | Compute 改造 | 大 | 2 |
| 5 | Admin voteable CRUD | 中 | 2 |
| 6 | Admin candidate import 适配 | 中 | 2 |
| 7 | Admin sync 适配 | 小 | 2 |
| 8 | admin_ui 改造 | 大 | 5,6 |
| 9 | 测试 | 中 | 3-7 |

---

## 任务 1：Alembic migration

**文件：** `alembic/versions/NNNN_voteable.py`

**步骤：**

1. `CREATE TABLE voteable_character`（id, name, name_jp, origin, type, first_appearance, aliases JSONB DEFAULT '[]', old_id, created_at）
2. `CREATE TABLE voteable_music`（同上，origin 替换为 album）
3. 回填 voteable：`INSERT INTO voteable_character (name, name_jp, origin, type, first_appearance) SELECT name, name_jp, origin, type, first_appearance FROM candidate_character WHERE merged_into IS NULL GROUP BY name, name_jp, origin, type, first_appearance`
4. 回填 voteable_music 同理
5. `ALTER TABLE candidate_character ADD COLUMN voteable_id INTEGER`
6. `ALTER TABLE candidate_music ADD COLUMN voteable_id INTEGER`
7. 回填 candidate.voteable_id：`UPDATE candidate_character c SET voteable_id = v.id FROM voteable_character v WHERE v.name = c.name`
8. candidate_music 同理
9. `ALTER TABLE candidate_character DROP COLUMN name, DROP COLUMN name_jp, DROP COLUMN origin, DROP COLUMN type, DROP COLUMN first_appearance, DROP COLUMN merged_into`
10. candidate_music 同理（额外 DROP COLUMN album）
11. `ALTER TABLE candidate_character ADD CONSTRAINT uq_candidate_char_year_voteable UNIQUE (vote_year, voteable_id)`
12. candidate_music 同理，同时 DROP 旧约束 `uq_candidate_music_year_name` / `uq_candidate_char_year_name`
13. `ALTER TABLE final_ranking ADD COLUMN voteable_id INTEGER`
14. 回填 final_ranking.voteable_id：`UPDATE final_ranking f SET voteable_id = v.id FROM voteable_character v WHERE v.name = f.name AND f.category = 'character'`（music 同理）

**注意：**
- 回填后检查 `voteable_id IS NULL` 的行，记录日志供后续手动处理
- `downgrade()` 需仔细处理——反向操作会丢数据，建议 downgrade 只做结构回滚不恢复数据

---

## 任务 2：DB Model

**文件：** `src/db_model/voteable.py`（新增）、`src/db_model/candidate.py`（改）

**VoteableCharacter：**

```python
class VoteableCharacter(Base):
    __tablename__ = "voteable_character"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    name_jp = Column(String(255), nullable=False, server_default="")
    origin = Column(String(255), nullable=False, server_default="")
    type = Column(String(64), nullable=False, server_default="")
    first_appearance = Column(String(16), nullable=True)
    aliases = Column(JSONB, nullable=False, server_default="[]")
    old_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

**VoteableMusic：** 同上，`origin` → `album`。

**CandidateCharacter 改：**

```python
class CandidateCharacter(Base):
    __tablename__ = "candidate_character"
    id = Column(Integer, primary_key=True, autoincrement=True)
    vote_year = Column(Integer, nullable=False, index=True)
    voteable_id = Column(Integer, nullable=False, index=True)
    __table_args__ = (
        UniqueConstraint("vote_year", "voteable_id", name="uq_candidate_char_year_voteable"),
    )
```

**CandidateMusic 改：** 同上。

**`src/db_model/__init__.py`：** 导出 `VoteableCharacter, VoteableMusic`。

---

## 任务 3：VoteObjects DAO/Service 改造

**文件：** `src/apps/vote_objects/dao.py`、`src/apps/vote_objects/service.py`

**3.1 DAO 改动：**

`list_characters(vote_year)`：
```python
# 改为 JOIN voteable
stmt = (
    select(CandidateCharacter, VoteableCharacter)
    .join(VoteableCharacter, CandidateCharacter.voteable_id == VoteableCharacter.id)
    .where(CandidateCharacter.vote_year == vote_year)
    .order_by(VoteableCharacter.name)
)
# 返回结构含 candidateId + voteable 字段
```

`list_music(vote_year)`：同理 JOIN VoteableMusic。

新增 `_build_alias_map(rows)` 辅助函数：
```python
def _build_alias_map(rows) -> dict[str, int]:
    """遍历 rows，从 voteable.aliases 构建 {alias: candidateId}"""
    alias_map = {}
    for candidate_id, aliases in rows:
        for alias in aliases or []:
            alias_map[alias] = candidate_id
    return alias_map
```

**3.2 Service 改动：**

返回结构适配新字段名（camelCase），附加 `aliasMap`。

**3.3 Router：** 无需改动（response 由 service 决定）。

---

## 任务 4：Compute 改造

**文件：** `src/apps/result/compute.py`、`src/apps/result/compute_dao.py`

**4.1 CandidateMeta 改动：**

```python
@dataclass
class CandidateMeta:
    candidate_id: int       # 新增
    voteable_id: int        # 新增
    name: str
    name_jp: str
    origin: str
    type: str
    first_appearance: str | None
    album: str | None = None
```

**4.2 ComputeDAO 改动：**

`load_char_candidates(vote_year)`：
- 改为 JOIN voteable_character
- 返回 `dict[int, CandidateMeta]`（key = candidate_id，不再用 name）

`load_music_candidates(vote_year)`：同理。

`load_historical(vote_year, category)`：
- `WHERE vote_year = N-1/N-2` 不变
- 若后续 final_ranking 有 voteable_id 则以此为 key
- 过渡期：先查 candidate WHERE vote_year = vote_year-1 → 拿到 name → voteable_id 映射，再做关联

`load_merge_name_map()`：废弃，不再需要。

**4.3 compute_ranking() 改动：**

- `name = item.get("id", "")` → `candidate_id = int(item.get("id", 0))`
- `vote_count[name]` → `vote_count[candidate_id]`
- `meta = candidates.get(name)` → `candidates.get(candidate_id)`
- 排名输出加 `voteableId = meta.voteable_id`
- `historical.get(name)` → `historical.get(meta.voteable_id)`

**4.4 compute_cp_ranking()：** CP 不涉及 candidate 表，不改。

---

## 任务 5：Admin Voteable CRUD

**文件：** `src/apps/admin/voteable_service.py`（新增）、`src/apps/admin/voteable_router.py`（新增）

**5.1 VoteableDAO（放在 `compute_dao.py` 或独立文件）：**

| 方法 | 说明 |
|---|---|
| `list_voteables(category, q, page, page_size)` | ILIKE name 搜索，分页，附带 candidateYears |
| `get_voteable(category, voteable_id)` | 单条查询 |
| `update_voteable(category, voteable_id, fields)` | insertSelective 更新 |
| `get_candidate_years(category, voteable_id)` | 查询 candidate 表中的年份列表 |

**5.2 Router：**

```python
router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/voteables")
async def list_voteables(category, q, page, page_size): ...

@router.post("/voteables/{id}")
async def update_voteable(id, body): ...
```

**5.3 注册路由：** 在 `src/api/rest/v1/__init__.py` 或 admin router 中引入。

---

## 任务 6：Admin Candidate Import 适配

**文件：** `src/apps/admin/service.py`、`src/apps/admin/candidate_service.py`

**6.1 import_candidates_from_content() 改动：**

现有流程：解析 → 校验 → `upsert_candidates(vote_year, category, items)`

新流程：
```python
# 1. 按 name 匹配已有 voteable
for item in valid:
    existing = await find_voteable_by_name(category, item["name"])
    if existing:
        item["voteable_id"] = existing.id
        linked += 1
    else:
        new_voteable = await create_voteable(category, item)
        item["voteable_id"] = new_voteable.id
        created += 1

# 2. upsert candidate (vote_year, voteable_id)
await upsert_candidates(vote_year, category, valid)

# 3. 返回 createdVoteables / linkedExisting
```

**6.2 upsert_candidates() 改动：**

冲突键从 `(vote_year, name)` 变为 `(vote_year, voteable_id)`。

**6.3 candidate_field_specs()：** 字段从 voteable 模型列推导（而非 candidate 模型），排除 `id`、`old_id`、`created_at`。

---

## 任务 7：Admin Sync 适配

**文件：** `src/apps/admin/sync/runner.py`

**map_candidate_character/music：** 拆为两步：
1. `map_voteable(doc)` → voteable 行（含 old_id = doc["_id"]）
2. `map_candidate(doc, voteable_id)` → candidate 行

sync 流程改为：先写 voteable（冲突键 old_id 或 name），再写 candidate（冲突键 vote_year + voteable_id）。

---

## 任务 8：admin_ui 改造

**目录：** `admin-ui/`

**8.1 新增 `src/views/VoteablesView.vue`：**
- 顶栏：category 切换（character/music）、搜索框
- 表格：voteableId、name、type、aliases、参选年份
- 点击行 → 编辑弹窗（Modal）：所有字段可编辑（含 aliases 的增删）
- 弹窗保存 → `POST /admin/voteables/{id}`

**8.2 改造 `src/views/CandidatesView.vue` → 年度对象选择页：**
- 顶栏：category + voteYear 选择器
- 左侧全部 voteable 列表（搜索/分页），已参选的行高亮打勾
- 右侧：本年度已选对象摘要 + "从上一年复制"按钮
- 勾选/取消 → 调 `/admin/candidates` 创建/删除

**8.3 新增 `src/api/voteables.ts`：**

```typescript
export async function listVoteables(category: string, params: { q?, page?, pageSize? }) ...
export async function updateVoteable(id: number, data: VoteableUpdateRequest) ...
```

**8.4 更新路由 `src/router.ts`：**

```typescript
{ path: '/voteables/:category', component: VoteablesView },
{ path: '/candidates/:category', component: CandidatesView },  // 改造
```

---

## 任务 9：测试

**9.1 单元测试：**

| 文件 | 内容 |
|---|---|
| `test_voteable_alias_map.py` | `_build_alias_map()` 正确生成 {alias: candidateId} |
| `test_compute.py`（改） | CandidateMeta 新字段；按 candidate_id 归票；voteable_id 历史关联 |
| `test_sync_mapping.py`（改） | 映射函数适配 |

**9.2 集成测试：**

| 文件 | 内容 |
|---|---|
| `test_voteable_import.py` | import 自动建 voteable + 回填 candidate；字段正确 |
| `test_voteable_admin.py` | voteable CRUD；relink；重复 candidate 409 |
| `test_vote_objects.py`（改） | response 含 aliasMap；camelCase 字段名 |
| `test_result_compute.py`（改） | 跨年历史对比用 voteable_id 而非 name |

**9.3 契约测试：**

| 文件 | 内容 |
|---|---|
| `test_voteable_contract.py` | `/vote-objects/*` response shape 校验 |
| `test_admin_endpoints_ext.py`（改） | admin voteable/candidate 端点可达性 |

---

## 执行顺序

```
任务 1 (migration)
  → 任务 2 (model)
    → 任务 3 (VoteObjects) ──┐
    → 任务 4 (Compute) ──────┤  可并行
    → 任务 5 (Admin CRUD) ───┤
    → 任务 6 (Import) ───────┤
    → 任务 7 (Sync) ────────┘
      → 任务 8 (admin_ui)
        → 任务 9 (测试)
```
