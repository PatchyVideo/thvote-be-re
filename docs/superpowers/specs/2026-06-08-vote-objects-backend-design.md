# Block 3B 投票对象迁后端 — 后端(含管理端)设计稿

> 创建日期：2026-06-08
> 最后更新：2026-06-08
> 配套前端设计稿：[`2026-06-08-vote-objects-frontend-design.md`](./2026-06-08-vote-objects-frontend-design.md)

## 一、背景与目标

角色/音乐的投票对象列表当前 bundle 在前端 `@touhou-vote/shared/data/{character,music}`。需求要求后端管理投票对象(初始化、去重合并、分类查询、详情)。本块把**角色/音乐**迁到后端管理 + 前端从后端拉。

## 二、关键决策(brainstorm 结论)

| 决策 | 选定 |
|---|---|
| 数据源 | 后端 candidate_character/music 成投票页**唯一真相源** |
| 去重合并 | **导入时自动合并 + admin 可手调**(重名角色合并、同曲名不同专辑合并) |
| 分类查询 | `/vote-objects/{category}`:角色按首登作品、音乐按专辑 |

## 三、数据模型(migration 0010)

复用现有 `candidate_character`(有 origin/first_appearance)、`candidate_music`(有 album)。新增**合并规范化**字段:

```python
# 给 candidate_character / candidate_music 各加:
merged_into  # Integer nullable index  — 指向规范化主候选 id;NULL = 自身即规范化
```
- `merged_into` 非空的行视为"已被合并到主候选",投票列表/计算只取规范化主候选(`merged_into IS NULL`)。
- 被合并行保留(留痕 + admin 可拆)。

## 四、去重合并

### 自动合并(导入时)
导入候选时,按规则探测重复并设 `merged_into`:
- **重名角色合并**:同 `vote_year` 同 `name` 的角色 → 合并到最早/指定主候选。
- **同曲名不同专辑合并**:同 `vote_year` 同 `name`、`album` 不同的音乐 → 合并到主候选(保留各专辑信息于主候选的附加字段或被合并行)。
- 规则封装为纯函数 `detect_merges(category, rows) -> list[(dup_id, canonical_id)]`,可单测。

### admin 手调
| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/admin/candidates/{id}/merge-into/{target_id}` | 手动合并(设 merged_into) |
| `POST` | `/admin/candidates/{id}/unmerge` | 拆分(清 merged_into) |
| `GET` | `/admin/candidates/merges?category=&vote_year=` | 查看合并关系 |

> 管理端候选 Tab 加"合并关系"视图 + 合并/拆分操作。

## 五、投票对象查询端点

公开只读,供前端投票页:
| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/vote-objects/characters?vote_year=` | 角色,按**首登作品**(origin/first_appearance)分组;只含规范化主候选 |
| `GET` | `/vote-objects/music?vote_year=` | 音乐,按**专辑**(album)分组;只含规范化主候选 |
| `GET` | `/vote-objects/{category}/{id}` | 单个投票对象详情(character/music) |

返回形状:`{ vote_year, groups:[{group, items:[...]}] }`。
> character/music 统一为同一套 `/vote-objects/*` 端点族,前端复用同一数据加载封装。

## 六、对计算的影响

- ComputeService 读候选/计票时,过滤 `merged_into IS NULL`(只算规范化主候选);被合并候选的票归并到主候选。
- 需在 `load_*_candidates` 与计票聚合处统一处理合并映射。

## 七、复用

- 候选管理(schema 驱动)已支持 character/music 的导入/编辑;本块加合并字段 + 合并端点 + 分类查询。
- `/vote-objects/characters` 与 `/vote-objects/music` 是同族端点,共用一套分组组装逻辑。

## 八、测试策略

| 层 | 覆盖 |
|---|---|
| unit | `detect_merges`:重名角色、同曲名不同专辑、无重复 |
| unit | 分组逻辑(按首登作品/专辑) |
| integration | 导入触发自动合并;手动 merge/unmerge;`/vote-objects/characters|music` 分组只含主候选 |
| integration | ComputeService 合并后计票:被合并票归并到主候选 |
| contract | `/vote-objects/*` shape;merge 端点 403/404 |

## 九、文件变更一览

| 文件 | 操作 |
|---|---|
| `src/db_model/candidate.py` | character/music 加 merged_into |
| `alembic/versions/0010_candidate_merge.py` | 新建 migration |
| `src/apps/admin/candidate_merge.py` | 新建:detect_merges 纯逻辑 |
| `src/apps/admin/{service,router,schemas}.py` | 合并端点 + 导入时自动合并接线 |
| `src/apps/result/compute_dao.py` / compute_service | 计票过滤/归并 merged_into |
| `src/apps/<vote_objects>/router.py` | /vote-objects/characters|music|{id} |
| `src/admin_ui/index.html` | 候选 Tab 合并关系视图 |
| `tests/...` | 新建 |

## 十、依赖

- 本块自建 `/vote-objects/characters|music|{id}` 端点族(无外部前置)。
- 前端角色/音乐投票页改从后端拉,依赖本块端点合并。

## 十一、关联

- 前端设计稿:[`2026-06-08-vote-objects-frontend-design.md`](./2026-06-08-vote-objects-frontend-design.md)
- BACKLOG:B-040
