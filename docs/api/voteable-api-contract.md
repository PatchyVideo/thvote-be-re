# THVote 后端 API 契约（前端开发用）

> 版本：1.0
> 创建日期：2026-07-20
> Base URL：`/api/v1`
> Content-Type：`application/json`
> 字符编码：UTF-8
> 错误格式：`{ "detail": "<message>" }`
> 分页：`page` 从 1 开始，`pageSize` 默认 50

---

## 目录

1. [公共接口](#一公共接口)
2. [用户与认证](#二用户与认证)
3. [投票提交](#三投票提交)
4. [投票结果](#四投票结果)
5. [问卷](#五问卷)
6. [自动补全](#六自动补全)
7. [爬虫](#七爬虫)
8. [Admin 管理后台](#八admin-管理后台)
9. [改动标记](#九改动标记)

---

## 一、公共接口

### `GET /health`

```
Response 200:
{
  "status": "ok" | "degraded",
  "db_status": "ok" | "unavailable",
  "vote_year": 2025
}
```

---

## 二、用户与认证

### 2.1 发送验证码

#### `POST /user/send-email-code`

```
Request:  { "email": "user@example.com" }
Response 200: { "ok": true }
```

#### `POST /user/send-sms-code`

```
Request:  { "phone": "+8613800000000" }
Response 200: { "ok": true }
```

### 2.2 登录

三种登录方式，响应结构相同：

```
Response 200:
{
  "userToken": "eyJ...",
  "voteToken": "eyJ..." | null,   // 仅在投票窗口内且用户已验证手机/邮箱时返回
  "voter": { ... }                  // VoterFE 对象
}
```

#### `POST /user/login-email-password`

```
Request: { "email": "...", "password": "..." }
```

#### `POST /user/login-email`

```
Request: { "email": "...", "code": "123456" }
```

#### `POST /user/login-phone`

```
Request: { "phone": "...", "code": "123456" }
```

### 2.3 信息更新

以下接口均需 userToken 鉴权，响应 `{ "ok": true }`。

| 接口 | Request |
|---|---|
| `POST /user/update-email` | `{ "email": "...", "code": "..." }` |
| `POST /user/update-phone` | `{ "phone": "...", "code": "..." }` |
| `POST /user/update-nickname` | `{ "nickname": "..." }` |
| `POST /user/update-password` | `{ "oldPassword": "...", "newPassword": "..." }` |
| `POST /user/remove-voter` | `{}` |
| `POST /user/token-status` | `{ "token": "..." }` |

### 2.4 获取当前用户

#### `GET /user/me`

Header: `Authorization: Bearer <userToken>`

```
Response 200: VoterFE 对象
{
  "id": "...",
  "nickname": "...",
  "email": "...",
  "phoneNumber": "...",
  "phoneVerified": true,
  "emailVerified": false,
  "pfp": null,
  "registerDate": "2025-07-01T00:00:00Z",
  ...
}
```

### 2.5 SSO 登录

| 接口 | 说明 |
|---|---|
| `GET /user/sso/qq/authorize` | QQ 登录跳转 |
| `GET /user/sso/qq/callback?code=...&state=...` | QQ 回调 |
| `POST /user/sso/qq/bind` | QQ 绑定 `{ "code": "..." }` |
| `GET /user/sso/thbwiki/authorize` | THBWiki 登录跳转 |
| `GET /user/sso/thbwiki/callback?code=...&state=...` | THBWiki 回调 |
| `POST /user/sso/thbwiki/bind` | THBWiki 绑定 `{ "code": "..." }` |

---

## 三、投票提交

### 3.1 写入投票

每个接口需要 voteToken 鉴权。request 中包含投票项和 meta 元数据。

```
Response 200: { "ok": true }
```

#### `POST /character/`

```typescript
interface CharacterSubmitRequest {
  characters: VoteSlot[];
  meta: SubmitMeta;
}

interface VoteSlot {
  id: number;            // candidateId ← 来自 /vote-objects/characters
  first: boolean;        // 是否本命
  reason: string | null;
}
```

#### `POST /music/`

```typescript
interface MusicSubmitRequest {
  music: VoteSlot[];
  meta: SubmitMeta;
}
// VoteSlot 同上，id = candidateId ← 来自 /vote-objects/music
```

#### `POST /cp/`

```typescript
interface CPSubmitRequest {
  cps: CPSlot[];
  meta: SubmitMeta;
}

interface CPSlot {
  id_a: string;
  id_b: string;
  id_c: string | null;
  active: string | null;
  first: boolean;
  reason: string | null;
}
```

#### `POST /paper/`

```typescript
interface PaperSubmitRequest {
  papers_json: string;   // JSON 字符串
  meta: SubmitMeta;
}
```

#### `POST /dojin/`

```typescript
interface DojinSubmitRequest {
  dojins: DojinSlot[];
  meta: SubmitMeta;
}

interface DojinSlot {
  dojin_type: string;
  url: string;
  title: string;
  author: string;
  reason: string;
  image_url: string | null;
}
```

### 3.2 公共 Metadata

```typescript
interface SubmitMeta {
  voteToken?: string;       // 也可放在 Header
  voteId: string;
  attempt: number | null;
  createdAt: string;        // ISO 8601
  userIp: string;
  additionalFingreprint?: string | null;
}
```

### 3.3 读取已提交的投票

需要 userToken 鉴权。

| 接口 | Request | Response |
|---|---|---|
| `POST /get-character/` | `{ "vote_id": "..." }` | `CharacterSubmitRequest` 或空 |
| `POST /get-music/` | `{ "vote_id": "..." }` | `MusicSubmitRequest` 或空 |
| `POST /get-cp/` | `{ "vote_id": "..." }` | `CPSubmitRequest` 或空 |
| `POST /get-paper/` | `{ "vote_id": "..." }` | `PaperSubmitRequest` 或空 |
| `POST /get-dojin/` | `{ "vote_id": "..." }` | `DojinSubmitRequest` 或空 |

### 3.4 投票状态

| 接口 | 说明 |
|---|---|
| `POST /voting-status/` `{ "vote_id": "..." }` | 返回 `{ hasCharacter, hasMusic, hasCP, hasPaper, hasDojin }` |
| `POST /voting-statistics/` `{}` | 返回总投票人数统计 |
| `GET /nominations/approved` | 已审核通过的同人提名列表 |

---

## 四、投票对象（Vote Objects）🚧 本次改动

### 4.1 获取角色列表

```
GET /vote-objects/characters?vote_year={year}
```

| Query | 类型 | 必填 | 说明 |
|---|---|---|---|
| `vote_year` | int | 否 | 默认当前年份 |

```typescript
// Response 200:
interface VoteObjectsCharacterResponse {
  voteYear: number;
  groups: CharacterGroup[];
  aliasMap: Record<string, number>;
}

interface CharacterGroup {
  group: string;          // origin（首登作品），空=未分类
  items: CharacterItem[];
}

interface CharacterItem {
  candidateId: number;    // 🔑 投票时作为 VoteSlot.id 提交
  name: string;
  nameJp: string;
  origin: string;
  type: string;
  firstAppearance: string | null;
}

// aliasMap:
//   key = 别名（含 name 本身、日文名、所有 aliases）
//   value = candidateId
//   前端用此 map 做本地即时匹配
```

### 4.2 获取音乐列表

```
GET /vote-objects/music?vote_year={year}
```

```typescript
interface VoteObjectsMusicResponse {
  voteYear: number;
  groups: MusicGroup[];
  aliasMap: Record<string, number>;
}

interface MusicGroup {
  group: string;          // album，空=未分类
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

### 4.3 获取单个详情

```
GET /vote-objects/{category}/{candidateId}
```

| Path | 类型 | 值 |
|---|---|---|
| `category` | enum | `"character"` 或 `"music"` |
| `candidateId` | int | 来自列表的 candidateId |

```typescript
interface VoteItemDetail {
  candidateId: number;
  voteYear: number;
  name: string;
  nameJp: string;
  origin: string;              // character 专属，music 为 ""
  firstAppearance: string | null;
  album: string | null;        // music 专属，character 为 null
}
```

---

## 五、投票结果

所有接口使用 POST，request body 中带查询参数。

### 5.1 `POST /result/ranking/`

```typescript
// Request:
{ "category": "character" | "music" | "cp", "vote_year"?: number, "names"?: string[] }

// Response:
{
  "rankings": [{
    "rank": [{ "rank": 1, "vote_count": 100, "favorite_vote_count": 30, ... }],
    "display_rank": 1,
    "name": "博麗靈夢",
    "voteableId": 5,         // 🆕
    "favorite_vote_count_weighted": 190,
    "type": "主角",
    "origin": "東方紅魔鄉",
    "name_jp": "博麗 霊夢",
    ...
  }],
  "global": { "total_unique_items": 150, "total_votes": 10000, ... }
}
```

### 5.2 `POST /result/trends/`

```typescript
// Request: { "category": "...", "name": "...", "vote_year"?: number }
// Response: { "trend": [...], "trend_first": [...] }
```

### 5.3 `POST /result/global-stats/`

```typescript
// Request: { "vote_year"?: number }
// Response: { "num_vote": 5000, "num_char": 4500, "num_music": 4000, "num_male": 3000, ... }
```

### 5.4 `POST /result/single/`

```typescript
// Request: { "category": "...", "name": "...", "vote_year"?: number }
// Response: 单个 ranking 条目（同 ranking 数组元素）
```

### 5.5 `POST /result/reasons/`

```typescript
// Request: { "category": "...", "name": "...", "vote_year"?: number }
// Response: { "reasons": ["因为...", "因为..."] }
```

### 5.6 `POST /result/covote/`

```typescript
// Request: { "category": "...", "vote_year"?: number }
// Response: { "items": [{ "a": "A", "b": "B", "cv": 0.85, ... }] }
```

### 5.7 `POST /result/completion-rates/`

```typescript
// Request: { "vote_year"?: number }
// Response: { "character": 0.9, "music": 0.8, "cp": 0.5, "questionnaire": 0.7 }
```

### 5.8 `POST /result/questionnaire/`

```typescript
// Request: { "question_id": "...", "vote_year"?: number }
// Response: { "answers_cat": [...], "answers_str": [...], "total": 500 }
```

### 5.9 `POST /result/questionnaire-trend/`

同 questionnaire，语义为历年趋势。

---

## 六、问卷

### `GET /questionnaire/structure`

```typescript
// Response 200:
{
  "voteYear": 2025,
  "groups": [{
    "id": "g1",
    "title": "基本信息",
    "order": 1,
    "questions": [{
      "id": "q1",
      "text": "性别",
      "type": "single",
      "order": 1,
      "options": [{ "id": "o1", "text": "男", "order": 1 }]
    }]
  }]
}
```

---

## 七、自动补全

### `POST /autocomplete/search`

```typescript
// Request:
{
  "query": "博麗",
  "categories": ["character", "music", "cp"],
  "limit": 10
}

// Response:
{
  "character": [{ "name": "博麗靈夢", "origin": "東方紅魔鄉", ... }],
  "music": [...],
  "cp": []
}
```

> 🚧 本次改动后，前端投票页改用 `/vote-objects` 返回的 `aliasMap` 做本地匹配。此接口保留，供其他场景使用。

---

## 八、爬虫

### `POST /scraper/scrape`

```typescript
// Request: { "url": "https://...", "force"?: false }
// Response: { "data": { "udid": "...", "title": "...", "ptime": "..." } }
// 缓存命中时返回 { "cached": true, "data": {...} }
```

---

## 九、Admin 管理后台

> 以下接口需要 admin 鉴权。

### 9.1 系统

| 接口 | 说明 |
|---|---|
| `GET /health` | 健康检查（公开） |
| `POST /admin/reload-config` | 热重载配置 |
| `GET /admin/discover/{service_name}` | Nacos 服务发现 |
| `GET /admin/stats` | 管理仪表盘统计 |

### 9.2 问卷管理

| 接口 | 说明 |
|---|---|
| `GET /admin/questionnaires` | 问卷列表 |
| `GET /admin/questionnaires/{qid}` | 问卷详情 |
| `POST /admin/questionnaires` | 新建问卷 |
| `PUT /admin/questionnaires/{qid}` | 编辑问卷 |
| `DELETE /admin/questionnaires/{qid}` | 删除问卷 |
| `POST /admin/question-groups` | 新建题组 |
| `PUT /admin/question-groups/{gid}` | 编辑题组 |
| `DELETE /admin/question-groups/{gid}` | 删除题组 |
| `POST /admin/questions` | 新建题目 |
| `PUT /admin/questions/{qid}` | 编辑题目 |
| `DELETE /admin/questions/{qid}` | 删除题目 |
| `POST /admin/options` | 新建选项 |
| `PUT /admin/options/{oid}` | 编辑选项 |
| `DELETE /admin/options/{oid}` | 删除选项 |
| `POST /admin/questionnaire/import` | 批量导入问卷 |

### 9.3 用户管理

| 接口 | Request / Response |
|---|---|
| `GET /admin/users` | Query: `email?`, `phone?`, `page`, `pageSize` → `{ items: User[], total }` |
| `GET /admin/users/{user_id}` | → 用户详情 + 投票提交状态 |
| `PATCH /admin/users/{user_id}/ban` | → `{ "ok": true }` |
| `PATCH /admin/users/{user_id}/unban` | → `{ "ok": true }` |

### 9.4 Candidate 管理 🚧

#### `GET /admin/candidates`

```
Query: category=character|music, voteYear=int, page, pageSize
```

```typescript
// Response 200:
{
  "items": [{ "candidateId": 42, "voteYear": 2025, "voteableId": 5, "name": "博麗靈夢" }],
  "total": 120
}
```

#### `POST /admin/candidates/import` 🚧

```typescript
// Request:
{
  "voteYear": 2025,
  "category": "character" | "music",
  "format": "csv" | "json" | "auto",
  "content": "...",       // 原始文本
  "dryRun": true          // true=仅预览
}

// Response:
{
  "valid": [{ ... }],
  "validCount": 10,
  "rejected": [{ "line": 3, "reason": "缺少 name" }],
  "createdVoteables": 3,   // 🆕 dryRun=false 时
  "linkedExisting": 7,     // 🆕
  "imported": 10
}
```

#### `POST /admin/candidates/{id}/relink` 🆕

```typescript
// Request: { "voteableId": 99 }
// Response 200: { "ok": true }
// Response 404: { "detail": "NOT_FOUND" }
// Response 409: { "detail": "CONFLICT" }
```

#### `DELETE /admin/candidates/{id}`

```
Response 200: { "ok": true }
```

> 只删 candidate 行，不删 voteable。其余 candidate 管理端点（fields/merges/merge-into/unmerge）🚧废弃。

### 9.5 Voteable 管理 🆕

#### `GET /admin/voteables`

```
Query: category=character|music, q?=, page, pageSize
```

```typescript
// Response 200:
{
  "items": [{
    "voteableId": 5,
    "name": "博麗靈夢",
    "nameJp": "博麗 霊夢",
    "origin": "東方紅魔鄉",     // character
    "album": null,              // music
    "type": "主角",
    "firstAppearance": "2002-08-11",
    "aliases": ["靈夢", "紅白"],
    "oldId": null,
    "candidateYears": [2024, 2025]
  }],
  "total": 150
}
```

#### `POST /admin/voteables/{id}`

```typescript
// Request (insertSelective):
{
  "name"?: "博麗靈夢",
  "nameJp"?: "博麗 霊夢",
  "type"?: "主角",
  "firstAppearance"?: "2002-08-11",
  "origin"?: "東方紅魔鄉",      // character
  "album"?: "東方幻奏響",       // music
  "aliases"?: ["靈夢", "紅白", "はくれい"]
}
// Response 200: { "ok": true }
```

### 9.6 计票

#### `POST /admin/compute-results`

```typescript
// Request: { "vote_year": 2025 }
// Response: { "ok": true, "vote_year": 2025, "duration_seconds": 3.5, "counts": { ... } }
```

#### `GET /admin/ranking/preview`

```
Query: category?, vote_year?
→ 排名列表（前 N 条预览）
```

#### `POST /admin/finalize-ranking`

```typescript
// Request: { "vote_year": 2025 }
// Response: { "ok": true, "count": 150 }
// 将 Redis 排名归档到 final_ranking 表
```

### 9.7 安全监控

| 接口 | 说明 |
|---|---|
| `GET /admin/monitor/overview` | 概览统计 |
| `GET /admin/monitor/groups` | 行为聚类 |
| `GET /admin/monitor/groups/{kind}/{key}/members` | 聚类成员 |
| `GET /admin/monitor/suspects` | 可疑用户列表 |
| `GET /admin/monitor/votes` | 投票记录 |
| `GET /admin/monitor/account/{vote_id}` | 用户详情 |
| `PATCH /admin/monitor/account/{vote_id}/review` | 标记审核 |

### 9.8 其他 Admin 功能

| 接口 | 说明 |
|---|---|
| `GET /admin/nominations` | 同人提名审核列表 |
| `PATCH /admin/nominations/{id}/approve` | 通过提名 |
| `PATCH /admin/nominations/{id}/reject` | 拒绝提名 |
| `GET /admin/activity-logs` | 活动日志 |
| `GET /admin/export/votes` | 导出投票 CSV |
| `POST /admin/sync/start` | 触发 MongoDB 同步 |
| `GET /admin/sync/status` | 同步状态 |
| `GET /admin/sync/history` | 同步历史 |
| `POST /admin/sync/cancel` | 取消同步 |
| `POST /admin/sync/retry/{run_id}` | 重试同步 |

---

## 十、改动标记

| 标记 | 含义 |
|---|---|
| 🆕 | 本次新增接口 |
| 🚧 | 本次改动接口（request/response 有变化） |
| 无标记 | 本次不改动 |

| 接口 | 标记 | 改动内容 |
|---|---|---|
| `GET /vote-objects/characters` | 🚧 | response 新增 `aliasMap`、`candidateId`、字段 camelCase |
| `GET /vote-objects/music` | 🚧 | 同上 |
| `GET /vote-objects/{category}/{id}` | 🚧 | 字段 camelCase |
| `POST /admin/candidates/import` | 🚧 | response 新增 `createdVoteables`/`linkedExisting` |
| `GET /admin/candidates` | 🚧 | response 精简 |
| `POST /admin/candidates/{id}/relink` | 🆕 | |
| `GET /admin/voteables` | 🆕 | |
| `POST /admin/voteables/{id}` | 🆕 | |
| `GET /admin/candidates/fields` | 🚧 废弃 | 改为 `/admin/voteables/fields` 或从 voteable 推导 |
| `GET /admin/candidates/merges` | 🚧 废弃 | |
| `POST /admin/candidates/{id}/merge-into/{target}` | 🚧 废弃 | |
| `POST /admin/candidates/{id}/unmerge` | 🚧 废弃 | |
| 其余所有接口 | 不改 | |
