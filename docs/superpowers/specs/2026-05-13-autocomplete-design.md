# Autocomplete 模块设计规格

> 创建日期：2026-05-13
> 最后更新：2026-05-13
>
> 关联：`src/apps/autocomplete/`、`src/db_model/candidate.py`

---

## 一、背景与目标

`apps/autocomplete` 的路由、服务、DAO 骨架已存在，但 DAO 三个方法全部返回空列表。
本规格描述如何补全 `search_characters` 和 `search_music`，CP 补全暂不实现（旧 Rust 后端同样是空存根）。

---

## 二、数据来源

- **角色**：`candidate_character` 表（migration 0003，字段：`vote_year, name, name_jp, origin, type, first_appearance`）
- **音乐**：`candidate_music` 表（migration 0003，字段：`vote_year, name, name_jp, type, first_appearance, album`）
- **CP**：无候选表，`search_cps` 继续返回 `[]`

查询均按 `vote_year = settings.vote_year` 过滤，只搜索当届候选。

---

## 三、搜索逻辑

### 角色

```sql
SELECT name, name_jp, origin, type
FROM candidate_character
WHERE vote_year = :year
  AND (name ILIKE '%query%' OR name_jp ILIKE '%query%')
LIMIT :limit
```

返回 dict：`{"name": name, "origin": origin, "name_jp": name_jp, "type": type}`

### 音乐

```sql
SELECT name, name_jp, type, album
FROM candidate_music
WHERE vote_year = :year
  AND (name ILIKE '%query%' OR name_jp ILIKE '%query%')
LIMIT :limit
```

返回 dict：`{"name": name, "origin": album or None, "name_jp": name_jp, "type": type}`
（`origin` 字段复用 `album`，与服务层期望的 dict 键保持一致）

---

## 四、服务层调整

`AutocompleteService.search()` 当前将三类结果合并后按 `limit` 截断，会导致角色占满后音乐被排除。

**修改：** 每类各取 `math.ceil(limit / 2)` 条，合并后再截断到 `limit`：

```python
per_cat = math.ceil(request.limit / 2)
characters = await dao.search_characters(q, per_cat)
music      = await dao.search_music(q, per_cat)
# cps 不参与配额分配
results = [...chars, ...music][: request.limit]
```

---

## 五、DAO 依赖注入

DAO 需要知道 `vote_year`。方案：在 DAO 构造函数中新增 `vote_year: int` 参数，由 router 的 dependency 从 `get_settings()` 注入：

```python
class AutocompleteDAO:
    def __init__(self, session: AsyncSession, vote_year: int):
        self.session = session
        self.vote_year = vote_year
```

router dependency：
```python
async def get_autocomplete_service(
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AutocompleteService:
    dao = AutocompleteDAO(session, settings.vote_year)
    return AutocompleteService(dao)
```

---

## 六、响应格式（不变）

```json
{
  "suggestions": [
    {"name": "博丽灵梦", "type": "character", "origin": "东方红魔乡"},
    {"name": "Bad Apple!!", "type": "music",  "origin": "Touhou Lostword OST"}
  ]
}
```

`AutocompleteSuggestion` schema 不需修改（`name`, `type`, `origin: Optional[str]`）。

---

## 七、文件改动范围

| 文件 | 变动 |
|---|---|
| `src/apps/autocomplete/dao.py` | 实现 `search_characters`、`search_music`；构造函数加 `vote_year` |
| `src/apps/autocomplete/router.py` | dependency 注入 `settings.vote_year` |
| `src/apps/autocomplete/service.py` | 修复 limit 分配逻辑（`ceil(limit/2)` per category）|

---

## 八、测试策略

**单元测试（`tests/unit/test_autocomplete_service.py`）**
- mock DAO，验证 limit 分配：limit=10 时每类最多取 5 条
- mock DAO，验证合并截断：chars=5, music=5 → total=10

**集成测试（`tests/integration/test_autocomplete.py`）**
- SQLite + 3 条 `candidate_character` + 2 条 `candidate_music`，搜索 "博" → 断言返回匹配行
- 搜索不存在的词 → 返回空列表
- 搜索 `name_jp` 字段内容 → 也能匹配

**契约测试（现有 `tests/contract/test_router_endpoints.py`）**
- `POST /autocomplete/search` 已在可达性测试中，无需新增契约测试

---

## 九、不在本次范围内

- CP 自动补全（无历史实现，无候选表，暂跳过）
- 分页（`limit` 已满足当前需求）
- 模糊拼音匹配（超出现有 schema 范围）
