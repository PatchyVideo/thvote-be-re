# 跨年稳定投票对象（voteable）— 后端设计稿

> 创建日期：2026-07-20
> 最后更新：2026-07-20
> 状态：**后端 v1 已实现并合入 main**（zfq_dev 2026-07-20~21 实现，2026-07-23 合入；迁移 `12a5f2e6dbed` 已应用于测试库）。落地盘点/遗留项见 `docs/CHANGELOG.md` 2026-07-23 条目与 `docs/BACKLOG.md` B-057；⚠️ 投票传参切 candidateId 的前置约束见 B-050-后补6（记票白名单需先迁 DB voteable，否则计票归零）

## 一、背景与问题

### 1.1 现状

`candidate_music` / `candidate_character` 以 `UNIQUE(vote_year, name)` 为主键约束。同一首歌/角色在不同年份各自一行、各自一个 id。compute 阶段的历史对比（`load_historical`）靠 **name 字符串** 做跨年关联。

### 1.2 问题

- **name 变更即断链**：运营修正名称后，跨年对比失效（因为 `load_historical` 按 name 匹配 `final_ranking`）。
- **ID 不稳定**：同一作品每年一个不同的 candidate id，无法跟踪。
- **同一角色多来源**：角色可能出现在多个作品，导入时每个来源一条 candidate，它们应是同一个投票对象。

### 1.3 会议结论（2026-07-20）

| 决策 | 结论 |
|---|---|
| 方案 | 新增 `voteable_music` / `voteable_character` 表承载跨年实体，candidate 退化为年度关联表 |
| 投票传参 | 前端只传 `candidateId`（int），`voteableId` 是后端内部概念 |
| 旧 ID | `voteable` 表加 `old_id` 字段，供历史数据关联 |
| 角色多来源 | import 时多个来源行可关联到同一个 voteable → 生成多条 candidate 行指向同一 voteable |
| 音乐多版本 | 不同版本/不同专辑 → 不同 voteable（不合并），视作不同投票对象 |
| 别名 | 存在 `voteable.aliases`（JSONB），随 `/vote-objects` 接口返回 `aliasMap` |
| 历史数据 | 只导入上届 `final_ranking`（vote_year=11），不重新计算；用户数据全部重新注册 |
| 前端 | 单独设计，后端提供接口文档 |

---

## 二、数据模型

### 2.1 新增 `voteable_music`

```sql
CREATE TABLE voteable_music (
    id               SERIAL PRIMARY KEY,
    name             VARCHAR(255) NOT NULL,
    name_jp          VARCHAR(255) NOT NULL DEFAULT '',
    type             VARCHAR(64)  NOT NULL DEFAULT '',
    first_appearance VARCHAR(16),
    album            VARCHAR(255),
    aliases          JSONB        NOT NULL DEFAULT '[]',
    old_id           VARCHAR(64),
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);
```

### 2.2 新增 `voteable_character`

```sql
CREATE TABLE voteable_character (
    id               SERIAL PRIMARY KEY,
    name             VARCHAR(255) NOT NULL,
    name_jp          VARCHAR(255) NOT NULL DEFAULT '',
    origin           VARCHAR(255) NOT NULL DEFAULT '',
    type             VARCHAR(64)  NOT NULL DEFAULT '',
    first_appearance VARCHAR(16),
    aliases          JSONB        NOT NULL DEFAULT '[]',
    old_id           VARCHAR(64),
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);
```

### 2.3 精简 `candidate_music`

最终结构（从原来的 7 列业务字段精简为 3 列）：

```
candidate_character / candidate_music:
   id           SERIAL PRIMARY KEY
   vote_year    INTEGER NOT NULL
   voteable_id  INTEGER NOT NULL  FK → voteable_* (id)

   UNIQUE (vote_year, voteable_id)
```

被移除的列（name / name_jp / type / first_appearance / origin / album / merged_into）全部搬到 voteable 表。

`merged_into` 不再需要：candidate 层有 `UNIQUE(vote_year, voteable_id)`，不会出现同一 voteable 同年出现两次；voteable 层的「多来源归于同一投票对象」在 import 时通过 relink 完成。多个 candidate 行指向同一个 voteable_id 即为合併。

### 2.4 `final_ranking` 加 `voteable_id`

```sql
ALTER TABLE final_ranking ADD COLUMN voteable_id INTEGER;
```

历史回填：已有数据按 name 匹配 voteable。新数据由 compute 写入。

### 2.5 ER

```
voteable_music                         candidate_music
┌──────────────────────┐   1:N         ┌──────────────────┐
│ id (PK)              │ ◄────────── │ voteable_id (FK) │
│ name                 │              │ vote_year        │
│ name_jp              │              │ id (PK)          │
│ type                 │              └──────────────────┘
│ first_appearance     │
│ album                │              final_ranking
│ aliases (JSONB)      │              ┌──────────────────┐
│ old_id               │              │ voteable_id      │
│ created_at           │              │ vote_year        │
└──────────────────────┘              │ ...              │
                                      └──────────────────┘
```

---

## 三、迁移与数据回填

### 3.1 Migration 步骤

```
1. CREATE TABLE voteable_music
2. CREATE TABLE voteable_character
3. 回填 voteable：INSERT INTO voteable_* (name, name_jp, ...)
      SELECT DISTINCT name, name_jp, ... FROM candidate_* GROUP BY name
4. ALTER TABLE candidate_* ADD COLUMN voteable_id
5. 回填 candidate.voteable_id：
      UPDATE candidate_* SET voteable_id = voteable.id
      FROM voteable WHERE voteable.name = candidate.name
6. ALTER TABLE candidate_*
      DROP COLUMN name, DROP COLUMN name_jp, ...（已搬到 voteable 的列）
      DROP COLUMN merged_into
      ADD CONSTRAINT uq_candidate_*_year_voteable UNIQUE (vote_year, voteable_id)
7. ALTER TABLE final_ranking ADD COLUMN voteable_id
8. 回填 final_ranking.voteable_id：按 name 匹配 voteable
```

### 3.2 数据安全

- 所有被 DROP 的 candidate 列，数据已完整复制到 voteable 表
- candidate 行数不变（一行也不删）
- 旧数据若 name 匹配失败 → voteable_id 可为 NULL（后续手动 relink）

---

## 四、API 契约

**规范：**
- 所有 JSON key 使用 camelCase
- 所有响应包在 `{ ... }` 对象中，无裸数组
- 错误响应格式：`{ "detail": "<message>" }`
- 分页参数：`page` 从 1 开始，`pageSize` 默认 50

**缓存：** `GET /vote-objects/{category}` 响应缓存在 Redis，key = `vote_objects:{category}:{vote_year}`，TTL 3600s。admin 编辑 voteable（含别名）时主动 DEL 该 key。

---

### 4.1 公开接口（前端投票页）

#### `GET /vote-objects/characters?vote_year=2025`

Query:

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `vote_year` | int | 否 | 默认取当前 vote_year（由服务端配置决定） |

Response `200`:

```typescript
interface VoteObjectsResponse {
  voteYear: number;
  groups: VoteGroup[];
  aliasMap: Record<string, number>;
}

interface VoteGroup {
  group: string;        // 角色=origin，音乐=album；空字符串归入"未分类"
  items: VoteItem[];
}

interface VoteItem {
  candidateId: number;  // 前端投票提交时作为 id 回传
  name: string;
  nameJp: string;
  origin: string;       // 仅 character
  type: string;
  firstAppearance: string | null;
}
```

#### `GET /vote-objects/music?vote_year=2025`

Query 同上。

Response `200`:

```typescript
interface VoteObjectsMusicResponse {
  voteYear: number;
  groups: MusicGroup[];
  aliasMap: Record<string, number>;
}

interface MusicGroup {
  group: string;        // album，空字符串归入"未分类"
  items: MusicItem[];
}

interface MusicItem {
  candidateId: number;
  name: string;
  nameJp: string;
  type: string;
  firstAppearance: string | null;
  album: string | null;
}
```

#### `GET /vote-objects/{category}/{candidateId}`

Path:

| 参数 | 类型 | 说明 |
|---|---|---|
| `category` | `"character" \| "music"` | |
| `candidateId` | int | |

Response `200`:

```typescript
interface VoteItemDetail {
  candidateId: number;
  voteYear: number;
  name: string;
  nameJp: string;
  origin: string;          // 仅 character
  firstAppearance: string | null;
  album: string | null;    // 仅 music
}
```

Response `404`: `{ "detail": "NOT_FOUND" }`

---

### 4.2 投票提交（不变）

#### `POST /character/` · `POST /music/` · `POST /cp/`

Request:

```typescript
// /character/
interface CharacterSubmitRequest {
  characters: VoteItem[];
  meta: SubmitMeta;
}

// /music/
interface MusicSubmitRequest {
  music: VoteItem[];
  meta: SubmitMeta;
}

interface VoteItem {
  id: number;          // = candidateId
  first: boolean;
  reason: string | null;
}

interface SubmitMeta {
  voteId: string;
  attempt: number | null;
  createdAt: string;   // ISO 8601
  userIp: string;
  additionalFingreprint?: string | null;
}
```

Response `200`: `{ "ok": true }`

---

### 4.3 Admin 接口

#### `POST /admin/candidates/import`

Request:

```typescript
interface CandidateImportRequest {
  voteYear: number;
  category: "character" | "music";
  format: "csv" | "json" | "auto";
  content: string;
  dryRun: boolean;      // true=仅预览不写入
}
```

Response `200`:

```typescript
interface CandidateImportResponse {
  valid: Record<string, string>[];  // dryRun=true 时返回
  validCount: number;
  rejected: { line: number; reason: string }[];
  createdVoteables: number;      // dryRun=false 时返回
  linkedExisting: number;         // dryRun=false 时返回
  imported: number;               // dryRun=false 时返回
}
```

#### `GET /admin/voteables`

Query:

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `category` | `"character" \| "music"` | 是 | |
| `q` | string | 否 | ILIKE 搜索 name |
| `page` | int | 否 | 默认 1 |
| `pageSize` | int | 否 | 默认 50 |

Response `200`:

```typescript
interface VoteableListResponse {
  items: VoteableRow[];
  total: number;
}

interface VoteableRow {
  voteableId: number;
  name: string;
  nameJp: string;
  origin: string;              // character
  type: string;
  firstAppearance: string | null;
  album: string | null;        // music
  aliases: string[];
  oldId: string | null;
  candidateYears: number[];    // 该 voteable 参与过的 vote_year
}
```

#### `POST /admin/voteables/{id}`

Path:

| 参数 | 类型 | 说明 |
|---|---|---|
| `id` | int | voteableId |

Request:

```typescript
interface VoteableUpdateRequest {
  name: string;
  nameJp?: string;
  type?: string;
  firstAppearance?: string | null;
  aliases?: string[];
  // character 专属:
  origin?: string;
  // music 专属:
  album?: string | null;
}
```

Response `200`: `{ "ok": true }`
Response `404`: `{ "detail": "NOT_FOUND" }`

#### `GET /admin/candidates`

Query:

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `category` | `"character" \| "music"` | 是 | |
| `voteYear` | int | 是 | |
| `page` | int | 否 | 默认 1 |
| `pageSize` | int | 否 | 默认 50 |

Response `200`:

```typescript
interface CandidateListResponse {
  items: CandidateRow[];
  total: number;
}

interface CandidateRow {
  candidateId: number;
  voteYear: number;
  voteableId: number;
  name: string;              // FROM voteable
}
```

#### `POST /admin/candidates/{id}/relink`

Path:

| 参数 | 类型 | 说明 |
|---|---|---|
| `id` | int | candidateId |

Request:

```typescript
interface RelinkRequest {
  voteableId: number;
}
```

Response `200`: `{ "ok": true }`
Response `404`: `{ "detail": "NOT_FOUND" }`
Response `409`: `{ "detail": "CONFLICT" }` — 目标 voteable 在同一年已有 candidate

#### `DELETE /admin/candidates/{id}`

Path:

| 参数 | 类型 | 说明 |
|---|---|---|
| `id` | int | candidateId |

Response `200`: `{ "ok": true }`
Response `404`: `{ "detail": "NOT_FOUND" }`

只删除 candidate 行，不删除关联的 voteable。

#### `POST /admin/compute-results`

请求和响应不变。内部逻辑变更见第五节。

---

## 五、算票逻辑变更

### 5.1 当前

```
vote payload: {"id": <name_string>, ...}
compute:      vote_count[name] += 1
              meta = candidates.get(name)         ← key 是 name
historical:   FinalRanking WHERE name = ...
```

### 5.2 新

```
vote payload: {"id": <candidate_id_int>, ...}
compute:      vote_count[candidate_id] += 1
              voteable_id = candidates[candidate_id].voteable_id
              meta = voteables[voteable_id]       ← 从 voteable 取 name/type 等
historical:   FinalRanking WHERE voteable_id = ...  ← key 是 voteable_id
```

### 5.3 ComputeDAO 改动

| 方法 | 改动 |
|---|---|
| `load_char_candidates()` | JOIN voteable；返回 key 从 name → candidate_id |
| `load_music_candidates()` | 同上 |
| `load_historical()` | WHERE 条件从 name → voteable_id；candidate 无 voteable_id 时需 JOIN |
| `load_merge_name_map()` | 废弃。无需 name→canonical 映射 |

### 5.4 compute_ranking() 改动

- `item.get("id")` 现在解释为 candidate_id（int），不再视为 name
- `candidates.get(name)` → `candidates.get(candidate_id)`
- `historical.get(name)` → `historical.get(voteable_id)`
- 排名输出附带 `voteableId`

---

## 六、admin_ui 改造

源码目录：`admin-ui/`

| 原页面 | 改造为 |
|---|---|
| `CandidatesView.vue` | **年度投票对象选择页**：选 category + voteYear → 从 voteable 池勾选参选对象 → 生成/移除 candidate 行 |
| — 新增 — | `VoteablesView.vue`：voteable 列表 + 编辑弹窗（name/aliases 等） |
| `CandidateImport` 区域 | 保持，内部适配 voteable |

### 年度投票对象选择页流程

```
1. 选 category + voteYear
2. 展示全部 voteable（搜索/分页），已参选的打勾
3. 勾选 → POST 建 candidate (voteYear, voteableId)
4. 取消勾选 → DELETE /admin/candidates/{id}
5. "从上一年复制" → 批量复制 candidate 行
```

---

## 七、同步（MongoDB import）改动

`src/apps/admin/sync/runner.py`：先写 voteable（含 `old_id`），再写 candidate（含 `voteable_id` 引用）。冲突键从 `(vote_year, name)` 变为 `(vote_year, voteable_id)`。

---

## 八、测试策略

| 层 | 内容 |
|---|---|
| **unit** | aliasMap 构建；voteable → candidate 映射；compute 按 candidate_id 归票 |
| **integration** | import 自动建 voteable + 回填 candidate；JOIN 查询；relink；跨年历史对比 |
| **contract** | `/vote-objects/*` response shape（含 aliasMap）；admin voteable CRUD |

---

## 九、文件变更清单

| 文件 | 变更类型 |
|---|---|
| `alembic/versions/NNNN_voteable.py` | 新增 migration |
| `src/db_model/voteable.py` | 新增模型 |
| `src/db_model/candidate.py` | 改：精简列，加 voteable_id |
| `src/apps/vote_objects/dao.py` | 改：JOIN voteable，构建 aliasMap |
| `src/apps/vote_objects/service.py` | 改：适配新返回结构 |
| `src/apps/result/compute.py` | 改：CandidateMeta 加 voteable_id；name → candidate_id 归票 |
| `src/apps/result/compute_dao.py` | 改：candidate JOIN voteable；load_historical 改用 voteable_id |
| `src/apps/admin/service.py` | 改：import 适配；新增 voteable CRUD |
| `src/apps/admin/router.py` | 新增：voteable 路由 |
| `src/apps/admin/candidate_service.py` | 改：字段推导从 voteable |
| `src/apps/admin/sync/runner.py` | 改：映射函数 |
| `src/apps/autocomplete/dao.py` | 不改（前端改用 aliasMap） |
| `admin-ui/src/views/VoteablesView.vue` | 新增 |
| `admin-ui/src/views/CandidatesView.vue` | 改：年度对象选择 |
| `admin-ui/src/api/voteables.ts` | 新增 |
| `admin-ui/src/api/candidates.ts` | 改 |
| 测试文件 | 改：fixture + 断言 |
