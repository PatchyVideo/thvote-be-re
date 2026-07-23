# Work 表 + 前后端统一设计

> 创建日期：2026-07-21
> 最后更新：2026-07-21
> 状态：**后端主体已实现并合入 main，前端部分完成**（zfq_dev/zfq_dev_fe 2026-07-20~21 实现，2026-07-23 合入 main）。已落地：work 表+种子/voteable 重构/新 vote-objects 契约(groups+filterMeta)/admin works CRUD+WorksView/前端 Task 6-7；未完：§4.6 `GET /admin/voteables`(404)、Task 5 import work 匹配、前端 Task 8/9、提交侧切 candidateId（前置=B-050-后补6）。盘点见 `docs/CHANGELOG.md` 2026-07-23 条目与 `docs/BACKLOG.md` B-057
> 前置 spec：2026-07-20-voteable-cross-year-stable-id-design.md

## 一、背景

### 1.1 现状

- `voteable_character` 有 `origin` VARCHAR 字段（角色登场作品名）
- `voteable_music` 有 `album` VARCHAR 字段（音乐所属专辑名）
- 前端投票页用 `origin`/`album` 做分组展示和筛选，同时依赖静态 `work.ts`（42 条）和 `music.ts albumList`（110 条）补充作品类型（kind）元数据
- `origin` 和 `album` 的取值存在大量重叠（如"蓬莱人形"既是角色出处也是音乐专辑），当前散落在两个 VARCHAR 列中，无约束、难管理

### 1.2 目标

1. 新增统一的 `work` 表，收敛角色和音乐的作品/专辑引用
2. `voteable_character.origin` → `work_id` FK
3. `voteable_music.album` → `work_id` FK
4. 后端 API 返回 `filterMeta`（作品的类型、名称等元数据），前端缓存后纯客户端筛选
5. 后端 admin 新增 work CRUD 管理页面
6. 当前 1:1（一个 voteable 关联一个 work），响应结构预留数组，未来可低成本扩展 1:N（筛选用多归属）

### 1.3 不纳入范围

- compute（结果统计/记票）模块：提交链路传 candidateId（int），与 work_id 无关，不动
- CP 投票：无 work 概念，不动
- 问卷模块：不动

---

## 二、数据模型

### 2.1 新增 `work` 表

```sql
CREATE TABLE work (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR(255) NOT NULL,
    type       VARCHAR(16)  NOT NULL CHECK (type IN ('old','new','CD','book','others')),
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_work_name ON work (name);
```

type 取值（与前端 work.ts 的 kind 对齐）：

| type | 含义 | 示例 |
|---|---|---|
| `old` | PC-98 旧作游戏 | 东方灵异传、东方封魔录… |
| `new` | Windows 新作游戏 | 东方红魔乡、东方兽王园… |
| `CD` | 音乐 CD / OST | 蓬莱人形、莲台野夜行、幻想曲拔萃… |
| `book` | 书籍 | 东方求闻史纪、东方三月精… |
| `others` | 其他 | 跨媒体、联动活动等 |

### 2.2 修改 `voteable_character`

```diff
- origin       VARCHAR(255) NOT NULL DEFAULT ''
+ work_id      INTEGER REFERENCES work(id)
```

### 2.3 修改 `voteable_music`

```diff
- album        VARCHAR(255)
+ work_id      INTEGER REFERENCES work(id)
```

work_id 允许 NULL：回填时匹配不上的暂为空，后续 admin 手动补充。

### 2.4 ER

```
work ──1:N── voteable_character (work_id)
     ──1:N── voteable_music     (work_id)

未来扩展（1:N 筛选多归属）：
work ──1:N── voteable_work_filter ──N:1── voteable_character
```

---

## 三、迁移

### 3.1 整体策略

`12a5f2e6dbed_voteable_cross_year_stable_id.py` 尚未在数据库执行。**重写该 migration**，一次性完成：

1. CREATE work + seed → 2. CREATE voteable_*（用 work_id）→ 3. 回填 voteable → 4. candidate 加 voteable_id 并删旧列 → 5. final_ranking 加 voteable_id

### 3.2 迁移步骤

```
1. CREATE TABLE work
2. INSERT work 种子数据（来自前端 work.ts + music.ts albumList，去重后约 120 条）
3. CREATE TABLE voteable_character (work_id, …)
4. CREATE TABLE voteable_music (work_id, …)
5. INSERT INTO voteable_character SELECT … LEFT JOIN work ON work.name = candidate.origin
6. INSERT INTO voteable_music … 同上
7. ALTER candidate_* ADD voteable_id → 回填 → DROP 旧列 → ADD UNIQUE 约束
8. ALTER final_ranking ADD voteable_id → 回填
```

### 3.3 种子数据

work 表种子来源于三个前端静态文件的并集：

| 来源 | 条数 | type 映射 |
|---|---|---|
| `work.ts` workList | 42 | kind 直接映射 |
| `music.ts` albumList | 110 | game→new(Windows)/old(PC-98)，CD→CD，book→book，others→others |
| `character.ts` 中未被上述覆盖的 work 名 | 少量 | 人工标注 |

去重键：work.name。

完整种子 SQL 见附录 A。

---

## 四、API 契约

### 4.1 `GET /vote-objects/characters?vote_year=N`

Response `200`：

```typescript
{
  voteYear: number;
  groups: VoteGroup[];           // 按 work.name 分组
  filterMeta: FilterMeta;        // ★ 新增，前端缓存此对象做筛选
  aliasMap: Record<string, number>;
}

interface FilterMeta {
  kinds: KindInfo[];             // 当前年份下存在的作品类型
  works: WorkInfo[];             // 当前年份下存在的作品列表
}

interface KindInfo {
  type: string;                  // "old" | "new" | "CD" | "book" | "others"
  label: string;                 // "游戏旧作" | "游戏新作" | "CD" | "书籍" | "其他"
}

interface WorkInfo {
  workId: number;
  name: string;                  // "东方红魔乡"
  type: string;                  // "new"
}

interface VoteItem {
  candidateId: number;
  name: string;
  nameJp: string;
  type: string;
  firstAppearance: string | null;
  workIds: number[];             // ★ 取代 origin 字符串，预留数组扩展
  workTypes: string[];           // ★ 从 workIds 推导，前端直接筛选
}
```

groups 按 work.name 分组，`work.name` 为空或 NULL 的归入"未分类"。

### 4.2 `GET /vote-objects/music?vote_year=N`

与 characters 结构相同，VoteItem 中同样用 `workIds`/`workTypes` 替代 `album`。

### 4.3 `GET /vote-objects/{category}/{candidateId}`

Response `200`：

```typescript
{
  candidateId: number;
  voteYear: number;
  name: string;
  nameJp: string;
  type: string;
  firstAppearance: string | null;
  workIds: number[];             // 替代 origin/album
  workTypes: string[];
}
```

### 4.4 `POST /character/` · `POST /music/` · `POST /cp/`

**不变。** 提交 payload 中 `VoteItem.id` 仍然是 candidateId（int），与 work_id 无关。

### 4.5 Admin：Work CRUD

| 方法 | 路径 | Request | Response |
|---|---|---|---|
| `GET` | `/admin/works` | `?q=&type=&page=1&pageSize=50` | `{ items: WorkRow[], total }` |
| `POST` | `/admin/works` | `{ name, type }` | `{ workId }` |
| `POST` | `/admin/works/{id}` | `{ name?, type? }` | `{ ok: true }` |
| `DELETE` | `/admin/works/{id}` | — | `{ ok: true }` 或 409 |

WorkRow：

```typescript
{
  workId: number;
  name: string;
  type: string;
  characterCount: number;       // 关联的 voteable_character 数量
  musicCount: number;           // 关联的 voteable_music 数量
  createdAt: string;
}
```

DELETE 409：有 voteable 引用时返回 `{ "detail": "WORK_IN_USE" }`。

### 4.6 Admin 已有接口适配

**`GET /admin/voteables`** — VoteableRow 中 `origin`/`album` → `workId` + `workName` + `workType`。

Field specs（`candidate_field_specs()`）从 voteable 模型 + work 表联合推导。

**`POST /admin/voteables/{id}`** — 可编辑 `workId`（前端下拉选择 work）。

**`POST /admin/candidates/import`** — CSV 中 origin/album 列按 name 匹配 work；无匹配则自动创建 work（type 默认 others，admin 后续可改）。

---

## 五、缓存

```
GET /vote-objects/{category} 响应
  → Redis key: vote_objects:{category}:{voteYear}
  → TTL: 3600s
  → 内容: groups + filterMeta + aliasMap

以下操作触发缓存清除 (DEL vote_objects:* )：
  - POST /admin/works (新增/编辑/删除)
  - POST /admin/voteables/{id} (编辑 workId)
  - POST /admin/candidates/import
  - POST /admin/candidates/{id}/relink
```

filterMeta 与 vote-objects 数据同一生命周期，同一 Redis key 存储，无需额外缓存层。

---

## 六、前端改动

### 6.1 数据获取层：`voteObjectsDataSource.ts`

```diff
interface BackendCharacterItem {
  id: number; name: string; name_jp: string;
- origin: string;
+ workIds: number[];
+ workTypes: string[];
  first_appearance: string | null;
}

interface BackendMusicItem {
  id: number; name: string; name_jp: string;
- album: string;
+ workIds: number[];
+ workTypes: string[];
  first_appearance: string | null;
}

+ export const filterMeta = ref<FilterMeta>({ kinds: [], works: [] });
```

`loadVoteObjects()` 解析响应中 `filterMeta` 并缓存。`enrichCharacter()` / `enrichMusic()`：
- `work` / `kind` 从 `filterMeta.works` + `item.workTypes` 推导，不再依赖静态 `work.ts`
- `album` 展示文本从 `filterMeta.works` 反查 `workId → name`

### 6.2 筛选组件：`workList.ts` / `albumList.ts`

```
kinds:           filterMeta.kinds → SelectList[]
worksList:       filterMeta.works → SelectList[]
workNameToSelectList: 直接从 filterMeta.works 取 name + type
```

不再 import 静态 `@touhou-vote/shared/data/work`。

### 6.3 列表过滤：`characterList.ts` / `musicList.ts`

```diff
- list.filter(c => c.work.includes(selectedWork))
+ list.filter(c => c.workIds.includes(selectedWorkId))
```

kind 过滤同理，用 `item.workTypes` 替代 `item.kind`。

### 6.4 展示组件

`VoteMusic.vue` / `MusicSelect.vue` / `MusicHonmeiCard.vue` 中显示专辑名：
```diff
- {{ item.album }}
+ {{ getWorkName(item.workIds[0]) }}   // 从 filterMeta.works 查找
```

### 6.5 缓存策略

- 首次加载 → `fetch()` → 解析 `filterMeta` → `sessionStorage.setItem()`
- 后续加载 → `sessionStorage.getItem()` 优先，stale-while-revalidate
- 用户切换 voteYear → `force=true` 重新拉取并替换缓存

### 6.6 前端文件变更清单

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `packages/vote/src/common/lib/voteObjectsDataSource.ts` | 改 | 接口类型 + filterMeta 解析 + enrich 逻辑 |
| `packages/vote/src/vote-character/lib/workList.ts` | 改 | 从 filterMeta 构建 kinds/worksList |
| `packages/vote/src/vote-music/lib/albumList.ts` | 改 | 同上 |
| `packages/vote/src/vote-character/lib/characterList.ts` | 改 | 过滤改用 workIds.includes() |
| `packages/vote/src/vote-music/lib/musicList.ts` | 改 | 同上 |
| `packages/vote/src/vote-music/VoteMusic.vue` | 改 | album 展示从 filterMeta 反查 |
| `packages/vote/src/vote-music/components/MusicSelect.vue` | 改 | 同上 |
| `packages/vote/src/vote-music/components/MusicHonmeiCard.vue` | 改 | 同上 |

---

## 七、admin_ui 改动

### 7.1 新增 `WorksView.vue`

路由：`/works`

- 顶栏：搜索框 `?q=` + 类型下拉 `?type=` + "新增作品"按钮
- 表格列：ID | 名称 | 类型（tag） | 关联角色数 | 关联音乐数 | 操作（编辑/删除）
- 新增/编辑弹窗：name 输入框 + type 下拉选择
- 删除前 confirm：提示关联的 voteable 数量
- API 调用：`src/api/works.ts`

### 7.2 已有页面适配

`VoteablesView.vue`：显示 `workName`/`workType` tag 替代 origin/album 文本；编辑弹窗中 workId 改为下拉选择。

### 7.3 admin_ui 文件变更清单

| 文件 | 变更类型 |
|---|---|
| `admin-ui/src/views/WorksView.vue` | 新增 |
| `admin-ui/src/api/works.ts` | 新增 |
| `admin-ui/src/views/VoteablesView.vue` | 改 |
| `admin-ui/src/router.ts` | 改（加 /works 路由） |

---

## 八、后端文件变更清单

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `alembic/versions/12a5f2e6dbed_*.py` | **重写** | 合并 work 建表 + voteable 建表 |
| `src/db_model/work.py` | 新增 | Work ORM 模型 |
| `src/db_model/voteable.py` | 改 | origin→work_id, album→work_id |
| `src/db_model/__init__.py` | 改 | 导出 Work |
| `src/apps/vote_objects/dao.py` | 改 | JOIN work，构建 filterMeta，workIds/workTypes |
| `src/apps/vote_objects/service.py` | 改 | 透传新结构 |
| `src/apps/admin/work_service.py` | 新增 | Work CRUD 业务逻辑 |
| `src/apps/admin/work_router.py` | 新增 | Work admin 路由 |
| `src/apps/admin/router.py` | 改 | 注册 work router |
| `src/apps/admin/candidate_service.py` | 改 | import 映射 work；field_specs 适配 |
| `src/apps/admin/sync/runner.py` | 改 | sync 映射 work_id |
| `tests/` | 改 | fixture + 断言适配 |

---

## 九、1:N 扩展路径

| | 现在 | 以后 |
|---|---|---|
| 数据 | `voteable.work_id` 直接取值 | 加 `voteable_work_filter` 中间表，多行 JOIN |
| 响应 | `workIds: [1]` | `workIds: [1, 2, 3]` |
| 前端 | `item.workIds.includes(id)` | **不变** |
| 迁移 | 无中间表 | `CREATE TABLE voteable_work_filter`，不回填已有数据 |

唯一成本：未来加一张中间表 + 改后端 DAO 的 JOIN，API 和前端零改动。

---

## 十、测试策略

| 层 | 内容 |
|---|---|
| **unit** | filterMeta 构建（kinds/works 去重排序）；work CRUD service 逻辑 |
| **integration** | migration 正确回填 work_id；JOIN 查询 work 字段；import 自动创建 work；DELETE 被引用 work 返回 409 |
| **contract** | `/vote-objects/*` response 含 filterMeta + workIds/workTypes（无 origin/album）；admin work CRUD 端点可达 |

---

## 附录 A：work 表种子 SQL

种子数据来源：
1. `thvote-fe/packages/shared/data/work.ts` — 42 条（type: old/new/CD/book/others）
2. `thvote-fe/packages/shared/data/music.ts` albumList — 110 条（type: game/CD/book/others）
3. 两者按 name 去重，type 冲突时以 work.ts 为准

```sql
INSERT INTO work (name, type) VALUES
  -- === 来自 work.ts (42条) ===
  ('东方灵异传', 'old'),
  ('东方封魔录', 'old'),
  ('东方梦时空', 'old'),
  ('东方幻想乡', 'old'),
  ('东方怪绮谈', 'old'),
  ('东方红魔乡', 'new'),
  ('东方妖妖梦', 'new'),
  ('东方萃梦想', 'new'),
  ('东方永夜抄', 'new'),
  ('东方花映塚', 'new'),
  ('东方风神录', 'new'),
  ('东方绯想天', 'new'),
  ('东方地灵殿', 'new'),
  ('东方星莲船', 'new'),
  ('东方非想天则', 'new'),
  ('东方文花帖DS', 'new'),
  ('东方神灵庙', 'new'),
  ('东方心绮楼', 'new'),
  ('东方辉针城', 'new'),
  ('东方深秘录', 'new'),
  ('东方绀珠传', 'new'),
  ('东方凭依华', 'new'),
  ('东方天空璋', 'new'),
  ('东方鬼形兽', 'new'),
  ('东方刚欲异闻', 'new'),
  ('东方虹龙洞', 'new'),
  ('东方兽王园', 'new'),
  ('蓬莱人形', 'CD'),
  ('莲台野夜行', 'CD'),
  ('旧约酒馆', 'CD'),
  ('东方文花帖（书籍）', 'book'),
  ('东方求闻史纪', 'book'),
  ('东方三月精', 'book'),
  ('东方儚月抄', 'book'),
  ('东方香霖堂', 'book'),
  ('东方茨歌仙', 'book'),
  ('东方铃奈庵', 'book'),
  ('东方智灵奇传', 'book'),
  ('东方醉蝶华', 'book'),
  ('其他', 'others'),
  ('东方文花帖', 'new'),
  ('弹幕天邪鬼', 'new'),
  ('妖精大战争', 'new'),
  ('秘封噩梦日记', 'new'),
  ('弹幕狂们的黑市', 'new'),
  -- === 来自 music.ts albumList，不在 work.ts 中的 (补充约70条) ===
  ('幻想曲拔萃', 'CD'),
  ('全人类的天乐录', 'CD'),
  ('核热造神非想天则', 'CD'),
  ('暗黑能乐集心绮楼', 'CD'),
  ('深秘乐曲集', 'CD'),
  ('深秘乐曲集·补', 'CD'),
  ('完全凭依唱片名录', 'CD'),
  ('贪欲之兽的音乐', 'CD'),
  ('梦违科学世纪', 'CD'),
  ('卯酉东海道', 'CD'),
  ('幺乐团的历史', 'CD'),
  ('大空魔术', 'CD'),
  ('未知之花 魅知之旅', 'CD'),
  ('鸟船遗迹', 'CD'),
  ('伊奘诺物质', 'CD'),
  ('燕石博物志', 'CD'),
  ('虹色的北斗七星', 'CD'),
  ('东方紫香花', 'book'),
  ('The Grimoire of Marisa', 'book'),
  ('东方外来韦编', 'book'),
  ('秋霜玉', 'new'),
  ('稀翁玉', 'new'),
  ('Torte Le Magic', 'new'),
  ('黄昏酒场', 'new'),
  ('神魔讨绮传', 'new'),
  ('东方幻想麻将', 'new'),
  ('Cradle - 东方幻乐祀典', 'CD'),
  ('8BIT MUSIC POWER FINAL', 'CD'),
  ('INDIE Live Expo', 'others'),
  ('东方音焰火', 'CD');
```

> **注意：** 实际迁移 SQL 中种子数据需与上述表完全一致。若 candidate_* 表中有 origin/album 值未被种子覆盖，回填时对应的 voteable.work_id 将为 NULL，需在 admin 中手动补充。

---

## 附录 B：前后端接口契约对照表

| 数据流 | 生产者 | 消费者 | 接口 | 关键字段 |
|---|---|---|---|---|
| 投票对象列表 | 后端 DAO | 前端 voteObjectsDataSource | `GET /vote-objects/{category}` | groups + filterMeta + aliasMap |
| 投票对象详情 | 后端 DAO | 前端（暂未使用） | `GET /vote-objects/{category}/{id}` | workIds, workTypes |
| 投票提交 | 前端 GraphQL | 后端 compute | `submitCharacterVote` / `submitMusicVote` | id=candidateId（与 work 无关） |
| Work 管理 | admin_ui | 后端 work_router | `/admin/works` CRUD | name, type |
| Voteable 管理 | admin_ui | 后端 voteable_router | `/admin/voteables` | workId |
| 候选导入 | admin_ui | 后端 candidate_service | `/admin/candidates/import` | origin/album → work_id |
