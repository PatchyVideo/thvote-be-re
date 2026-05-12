# Result 查询模块设计规格

> 创建日期：2026-05-13
> 最后更新：2026-05-13
>
> 关联：`src/apps/result/`、`src/apps/admin/`、`src/db_model/candidate.py`
> 实施报告：待写（`2026-05-13-result-query-implementation-report.md`）

---

## 一、背景与目标

`apps/result` 目前有完整路由和服务骨架，但 DAO 层 9 个方法全部 `raise NotImplementedError`。本规格描述如何从零完整实现 result 查询模块，包括：

1. 新增候选参考表（`candidate_character` / `candidate_music`）和历史排名表（`final_ranking`）
2. 改造 `vote_data` 的 schema（`character_list` 改为富对象）
3. 实现预聚合计算管道（`ComputeService`），结果写 Redis
4. 实现 9 个 result 端点（纯 Redis 读取）
5. 新增 3 个 admin 端点（触发计算、导入候选、存档排名）

### 与旧 Rust 后端的对应关系

| Rust 组件 | Python 对应 |
|---|---|
| `all_chars` / `all_musics` MongoDB 集合 | `candidate_character` / `candidate_music` PG 表 |
| `chars_entry_cache_coll` 等 MongoDB 缓存集合 | Redis JSON blobs |
| `final_ranking_char` / `final_ranking_music` | `final_ranking` PG 表 |
| 独立离线聚合脚本 | `POST /admin/compute-results` 触发的 `ComputeService` |
| `result-query` 服务 | `apps/result/dao.py`（Redis 读取）|

---

## 二、新增数据库表（Migration 0003）

### `candidate_character`

```sql
CREATE TABLE candidate_character (
    id               SERIAL PRIMARY KEY,
    vote_year        INTEGER NOT NULL,
    name             VARCHAR(255) NOT NULL,  -- 与 character_list.id 一致
    name_jp          VARCHAR(255) NOT NULL DEFAULT '',
    origin           TEXT NOT NULL DEFAULT '',  -- 所属作品，逗号分隔多作品
    type             VARCHAR(64) NOT NULL DEFAULT '',  -- 旧作/新作/游戏/专辑/出版物/其他
    first_appearance VARCHAR(16) DEFAULT NULL,  -- 年份字符串，如 "2008"
    UNIQUE (vote_year, name)
);
```

### `candidate_music`

```sql
CREATE TABLE candidate_music (
    id               SERIAL PRIMARY KEY,
    vote_year        INTEGER NOT NULL,
    name             VARCHAR(255) NOT NULL,
    name_jp          VARCHAR(255) NOT NULL DEFAULT '',
    type             VARCHAR(64) NOT NULL DEFAULT '',
    first_appearance VARCHAR(16) DEFAULT NULL,
    album            VARCHAR(255) DEFAULT NULL,
    UNIQUE (vote_year, name)
);
```

### `final_ranking`（历史存档，供下届对比）

```sql
CREATE TABLE final_ranking (
    id               SERIAL PRIMARY KEY,
    vote_year        INTEGER NOT NULL,
    category         VARCHAR(16) NOT NULL,  -- "character" / "music" / "cp"
    rank             INTEGER NOT NULL,
    name             VARCHAR(255) NOT NULL,
    vote_count       INTEGER NOT NULL,
    first_vote_count INTEGER NOT NULL,
    UNIQUE (vote_year, category, rank)
);
```

### 类型映射（KIND_MAPPING，对齐旧 Rust 逻辑）

```python
KIND_MAPPING = {
    "old": "旧作", "new": "新作", "CD": "专辑",
    "book": "出版物", "others": "其他", "other": "其他", "game": "游戏"
}
```

---

## 三、vote_data Schema 改造

### 新增富对象类型（`src/apps/vote_data/schemas.py`）

```python
class CharacterVoteItem(BaseModel):
    id: str
    first: bool = False
    reason: str | None = None

class MusicVoteItem(BaseModel):
    id: str
    first: bool = False
    reason: str | None = None

class CpVoteItem(BaseModel):
    id_a: str
    id_b: str
    id_c: str | None = None
    active: str | None = None
    first: bool = False
    reason: str | None = None
```

### 请求体改造

```python
# 改前
class CharacterVoteRequest(BaseModel):
    character_list: list[str]

# 改后
class CharacterVoteRequest(BaseModel):
    character_list: list[CharacterVoteItem]
```

`MusicVoteRequest` / `CpVoteRequest` 同理。`QuestionnaireVoteRequest` 不变。

### 数据库列兼容性

`character_list` 列类型仍为 JSON，无需 DDL migration。计算管道读取旧格式 `list[str]` 数据时降级处理（`first=False, reason=None`），不报错。

### 需同步更新的文件

- `src/apps/vote_data/schemas.py` — 新增三个 VoteItem 类，改 Request 类型
- `src/apps/vote_data/service.py` — 存储时调用 `item.model_dump()` 而非直接存 str
- `src/apps/vote_data/router.py` — 无需改动（类型通过 Pydantic 透传）
- `src/apps/result/router.py` — 依赖注入改变：`ResultDAO(session)` → `ResultDAO(redis, settings)`；需移除 `get_db_session` 依赖，改注入 `get_redis`
- `tests/` — 更新相关 fixture 和断言

---

## 四、新增配置（`src/common/config.py`）

```python
VOTE_YEAR: int = 2025                  # 当届届次
GENDER_QUESTION_ID: str = "q11011"    # 问卷中性别题 ID
GENDER_MALE_VALUE: str = "male"       # 性别题"男"的答案值
GENDER_FEMALE_VALUE: str = "female"   # 性别题"女"的答案值
```

---

## 五、文件结构

```
src/apps/result/
  router.py       ← 已有，小改：加 vote_year 参数，加 503 翻译
  service.py      ← 已有，调 ResultDAO
  dao.py          ← 重写：纯 Redis 读取，替换 NotImplementedError
  schemas.py      ← 已有，小改：各 Query 类加 vote_year: int | None
  compute.py      ← 新增：ComputeService + 各 compute_* 函数
  compute_dao.py  ← 新增：ComputeDAO（读 PG 原始数据，供 ComputeService）

src/apps/admin/
  __init__.py     ← 新增
  router.py       ← 新增：3 个 /admin/* 端点
  service.py      ← 新增：AdminService（调 ComputeService）
  schemas.py      ← 新增：ImportCandidatesRequest 等

src/db_model/
  candidate.py    ← 新增：CandidateCharacter + CandidateMusic + FinalRanking

src/api/rest/v1/__init__.py  ← 注册 admin router

alembic/versions/
  0003_candidate_and_final_ranking.py  ← 新增

tests/unit/
  test_compute.py            ← 新增

tests/integration/
  test_result_compute.py     ← 新增

tests/contract/
  test_result_endpoints.py   ← 新增
```

---

## 六、计算管道（`src/apps/result/compute.py`）

### ComputeService 接口

```python
class ComputeService:
    def __init__(self, compute_dao: ComputeDAO, redis: Redis, settings: Settings): ...

    async def compute_all(self, vote_year: int) -> dict:
        """触发全量计算，写 Redis。返回 {duration_seconds, counts}。"""
```

### 计算步骤（串行，单分布式锁保护）

```
Redis SETNX "compute_lock:{vote_year}" → 若已有锁返回 409

1. load_candidates(vote_year)
   → {name: CandidateMeta} for chars
   → {name: CandidateMeta} for musics

2. load_char_votes() → list[(user_id, submit_dt, list[CharacterVoteItem])]
   load_music_votes() → 同上
   load_cp_votes() → list[(user_id, submit_dt, list[CpVoteItem])]
   load_questionnaire_votes() → list[(user_id, submit_dt, list[dict])]

3. compute_gender_map(questionnaire_votes)
   → {user_id: "male"|"female"|"unknown"}
   实现：遍历 questionnaire_list，找 item["id"] == GENDER_QUESTION_ID
         取 item["answer"][0]，对比 GENDER_MALE_VALUE / GENDER_FEMALE_VALUE
   假设问卷 dict 结构（待实际数据确认）：
     {"id": "q11011", "answer": ["male"], "answer_str": null}
     或 {"id": "q11011", "answer": null, "answer_str": "male"}
   若两个字段都为 null，或 id 不匹配，则为 "unknown"

4. load_historical_rankings(vote_year)
   → {(category, name): {rank_1, votes_1, first_1, rank_2, votes_2, first_2}}
   来自 final_ranking 表 WHERE vote_year IN (vote_year-1, vote_year-2)

5. compute_char_ranking(char_votes, candidates, gender_map, historical)
   → list[RankingEntry]（含 trend, reasons, male/female counts）

6. compute_music_ranking(...)
7. compute_cp_ranking(...)
8. compute_global_stats(char_votes, music_votes, cp_votes, questionnaire_votes, gender_map)
9. compute_completion_rates(...)
10. compute_paper_results(questionnaire_votes)
    → {q_id: {answers_cat, answers_str, total, trend}}
11. compute_covote(char_votes, music_votes, top_k=100)

12. Redis pipeline：批量 SET 所有键，值为 JSON，无过期时间

Redis DEL "compute_lock:{vote_year}"
```

### 排名计算核心（以角色为例）

```python
# vote_start 来自 settings.VOTE_START_ISO（解析为 datetime）
# 趋势分桶粒度：1 小时

# 聚合
vote_count: dict[str, int]        # name → 总票数
first_count: dict[str, int]       # name → 本命票数
reasons: dict[str, list[str]]     # name → [理由列表]
male_count: dict[str, int]
female_count: dict[str, int]
trend: dict[str, list[int]]       # name → 按小时分桶的票数列表（桶数 = 总投票时长小时数）

for user_id, submit_dt, items in char_votes:
    gender = gender_map.get(user_id, "unknown")
    for item in items:
        vote_count[item.id] += 1
        if item.first:
            first_count[item.id] += 1
        if item.reason:
            reasons[item.id].append(item.reason)
        if gender == "male":
            male_count[item.id] += 1
        elif gender == "female":
            female_count[item.id] += 1
        hour_bucket = int((submit_dt - vote_start).total_seconds() / 3600)
        trend[item.id][hour_bucket] += 1

# 本命加权公式（待运营确认）：first_count_weighted = first_count * 3 + vote_count
#   此公式系参照旧 Rust 代码注释推测，实施前需与运营确认是否沿用
# 排序：primary=first_count_weighted DESC，secondary=vote_count DESC
# display_rank：跳过并列（1,1,3,3,5...）
```

### 共投计算（covote）

```python
# 仅对 top_k 名以内的实体计算（控制 O(k²) 复杂度）
for name_a, name_b in combinations(top_k_names, 2):
    voters_a = set(user_id for ... if name_a in voted_names)
    voters_b = set(user_id for ... if name_b in voted_names)
    m11 = len(voters_a & voters_b)
    m10 = len(voters_a - voters_b)
    m01 = len(voters_b - voters_a)
    m00 = total_voters - m11 - m10 - m01
    cv = m11 / (m11 + m10 + m01) if (m11 + m10 + m01) > 0 else 0
    # 存储 CovoteItem(a, b, m00, m01, m10, m11, cv)
```

---

## 七、ResultDAO 重写（`src/apps/result/dao.py`）

所有方法从 `NotImplementedError` 改为 Redis 读取：

```python
class ResultDAO:
    def __init__(self, redis: Redis, settings: Settings): ...

    async def get_ranking(self, query: RankingQuery) -> list[RankingEntry]:
        year = query.vote_year or settings.VOTE_YEAR
        key = f"result:{year}:{query.category}:ranking"
        raw = await self.redis.get(key)
        if raw is None:
            raise ResultNotComputedError()
        data = json.loads(raw)
        if query.names:
            data = [e for e in data if e["name"] in query.names]
        return [RankingEntry(**e) for e in data]

    # reasons / trends / single → 读 ranking JSON 后内存过滤
    # global_stats / completion_rates → 独立 key
    # questionnaire → result:{year}:paper:{q_id}
    # covote → result:{year}:covote:{category}
```

---

## 八、Admin 端点

### `POST /admin/compute-results`

```
Query: vote_year: int（默认 settings.VOTE_YEAR）
Auth: X-Admin-Secret header 对比 settings.ADMIN_SECRET（与 /admin/reload-config 保持一致）
返回: {ok: true, vote_year: 2025, duration_seconds: 12.3, counts: {...}}
错误: 409 COMPUTE_IN_PROGRESS（锁已存在）
```

### `POST /admin/import-candidates`

```
Body: {
  vote_year: int,
  category: "character" | "music",
  items: [
    {name, name_jp, origin, type, first_appearance, album?}
  ]
}
行为: UPSERT ON CONFLICT (vote_year, name) DO UPDATE
返回: {ok: true, imported: 123}
```

### `POST /admin/finalize-ranking`

```
Query: vote_year: int
行为: 从 Redis ranking JSON 提取 rank/name/vote_count/first_vote_count
      UPSERT INTO final_ranking
返回: {ok: true, vote_year: 2025, saved: 300}
错误: 503 RESULT_NOT_COMPUTED（Redis 无对应 key）
```

---

## 九、错误体系

```python
class ResultNotComputedError(AppException):
    """Redis 缓存未就绪，需先触发 /admin/compute-results"""
    # → router 翻译为 HTTP 503，code="RESULT_NOT_COMPUTED"

class ComputeInProgressError(AppException):
    """已有计算任务在进行"""
    # → HTTP 409，code="COMPUTE_IN_PROGRESS"

class EntityNotFoundError(AppException):
    """在已计算结果中找不到指定实体"""
    # → HTTP 404，code="ENTITY_NOT_FOUND"
```

---

## 十、测试策略

### 单元测试（`tests/unit/test_compute.py`）

| 测试函数 | 验证内容 |
|---|---|
| `test_compute_char_ranking_basic` | 3 用户投票，断言 vote_count / first_count / 排序 |
| `test_compute_gender_map` | 从 questionnaire_list 正确提取 male/female/unknown |
| `test_compute_historical_delta` | final_ranking 有数据时，rank_last_1 正确填充 |
| `test_compute_covote` | m11 / m10 / m01 / cv 计算正确 |
| `test_compute_completion_rates` | 各类别完成率计算 |
| `test_display_rank_ties` | 并列时 display_rank 正确跳号（1,1,3）|

### 集成测试（`tests/integration/test_result_compute.py`）

- 真实 SQLite + fakeredis
- Fixture：写候选数据 + 写 character/music/questionnaire 投票
- 触发 `ComputeService.compute_all()`
- 断言 Redis 中 ranking JSON 正确

### 契约测试（`tests/contract/test_result_endpoints.py`）

- 未 compute 时：9 个端点均返回 503
- compute 后：ranking 返回 200，字段类型匹配 schema
- `vote_year` 参数不存在时：返回当届默认值

---

## 十一、与现有代码的刻意差异

| 项目 | 旧 Rust | Python 重构 |
|---|---|---|
| 缓存存储 | MongoDB 各 cache 集合 | Redis JSON blobs |
| 候选数据存储 | MongoDB `all_chars` / `all_musics` | PostgreSQL `candidate_character` / `candidate_music` |
| 计算触发 | 独立离线脚本 | `POST /admin/compute-results` 同步 HTTP |
| 查询 DSL | Pest grammar（`query.pest`）| 不实现，直接参数化 |
| 历史届次数据 | MongoDB `final_ranking_*` 集合 | PostgreSQL `final_ranking` 表 |

---

## 十二、不在本次规格范围内

- Autocomplete 模块（候选表就绪后可共享，但独立 PR）
- GraphQL ResultQuery（result DAO 完成后再做）
- 异步/队列化的计算任务（当前规模不需要）
- `POST /admin/compute-results` 的 webhook 通知
