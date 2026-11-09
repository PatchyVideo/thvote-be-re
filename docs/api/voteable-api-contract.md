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
  voteId?: string;          // 服务端忽略：写入时一律取 voteToken 的 user_id（2026-09-13 起）
  attempt: number | null;
  createdAt: string;        // ISO 8601
  userIp: string;
  additionalFingreprint?: string | null;
}
```

### 3.3 读取已提交的投票

需要 **voteToken** 鉴权（2026-09-13 起）：请求体带 `vote_token`，服务端解出 user_id 后只返回该用户自己的提交。缺失或无效 token 一律 `401`（`detail` = `VOTE_TOKEN_REQUIRED` 或校验错误码）。旧字段 `vote_id` 仍可传但被忽略，兼容期结束后移除。

| 接口 | Request | Response |
|---|---|---|
| `POST /get-character/` | `{ "vote_token": "..." }` | `CharacterSubmitRequest` 或空 |
| `POST /get-music/` | `{ "vote_token": "..." }` | `MusicSubmitRequest` 或空 |
| `POST /get-cp/` | `{ "vote_token": "..." }` | `CPSubmitRequest` 或空 |
| `POST /get-paper/` | `{ "vote_token": "..." }` | `PaperSubmitRequest` 或空 |
| `POST /get-dojin/` | `{ "vote_token": "..." }` | `DojinSubmitRequest` 或空 |

### 3.4 投票状态

| 接口 | 说明 |
|---|---|
| `POST /voting-status/` `{ "vote_token": "..." }` | 需 voteToken 鉴权，返回**该用户自己**的 `{ characters, musics, cps, papers, dojin }`（均为 bool） |
| `POST /voting-statistics/` `{}` | 返回总投票人数统计 |
| `GET /nominations/approved` | 已审核通过的同人提名列表 |

---

## 四、投票对象（Vote Objects）

> 🚧 2026-09-16（迁移 0019）：资源类 URL 从「前端静态表按 `name` 匹配」迁到后端，
> 与 voteable 1:1 绑定。item 新增 `imageUrl` / `aliases`（音乐再加 `musicUrl` / `include`），
> 前端直接使用，不再本地匹配资源。`_source` 数据见后端 `scripts/voteable_resources.json`。

### 4.1 获取角色列表

```
GET /vote-objects/characters?vote_year={year}
```

| Query | 类型 | 必填 | 说明 |
|---|---|---|---|
| `vote_year` | int | 否 | 默认 `settings.vote_year` |

```typescript
// Response 200:
interface VoteObjectsCharacterResponse {
  voteYear: number;
  groups: CharacterGroup[];
  filterMeta: FilterMeta;        // 前端筛选下拉用
  aliasMap: Record<string, number>;
}

interface CharacterGroup {
  group: string;                 // work 名（首登作品），空 = 未分类
  items: CharacterItem[];
}

interface CharacterItem {
  candidateId: number;           // 🔑 投票时作为 VoteSlot.id 提交
  name: string;
  nameJp: string;
  type: string;                  // old / new / book / CD / others
  firstAppearance: string | null; // YYYYMMDD
  workIds: number[];
  workTypes: string[];
  imageUrl: string | null;       // 🆕 0019：立绘；null → 前端占位图
  aliases: string[];             // 🆕 0019：别名（前端搜索语料）
}

interface FilterMeta {
  kinds: { type: string; label: string }[];
  works: { workId: number; name: string; type: string }[];
}
```

### 4.2 获取音乐列表

```
GET /vote-objects/music?vote_year={year}
```

```typescript
interface VoteObjectsMusicResponse {
  voteYear: number;
  groups: MusicGroup[];
  filterMeta: FilterMeta;
  aliasMap: Record<string, number>;
}

interface MusicGroup {
  group: string;                 // work 名（专辑），空 = 未分类
  items: MusicItem[];
}

interface MusicItem {
  candidateId: number;
  name: string;
  nameJp: string;
  type: string;                  // game / book / CD / others
  firstAppearance: string | null;
  workIds: number[];
  workTypes: string[];
  imageUrl: string | null;       // 🆕 0019：封面
  musicUrl: string | null;       // 🆕 0019：试听（短音频）
  include: string[];             // 🆕 0019：收录专辑列表
  aliases: string[];
}
```

### 4.3 获取单个详情

```
GET /vote-objects/{category}/{candidateId}
```

| Path | 类型 | 值 |
|---|---|---|
| `category` | enum | `"character"` 或 `"music"` |
| `candidateId` | int | 列表里的 `candidateId` |

返回该 item 全部字段 + `voteYear`（`imageUrl/aliases`，音乐含 `musicUrl/include`）。不存在 → `404 NOT_FOUND`。

### 4.4 资源配置（管理端）

见 §9.5「Voteable 管理」的 `PUT /admin/voteables/{id}/resources`。

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

无年度参数，返回后台当前维护的定义。以下 ID/code 为格式示例，不代表线上题库：

```json
{
  "questionnaires": [{
    "id": 1, "key": "main_required", "title": "基础问卷",
    "introduction": "说明", "category": "main", "required": true, "order": 1,
    "questionGroups": [{
      "id": 10, "order": 1, "hiddenByDefault": false,
      "questions": [{
        "id": 100, "code": "11011", "order": 1, "type": "Single",
        "content": "题干", "introduction": "", "maxInputLen": 1000,
        "options": [{
          "id": 200, "code": "1101101", "order": 1, "content": "选项",
          "relatedQuestionIds": [], "mutexOptionIds": [], "optionGroup": 0
        }]
      }]
    }]
  }]
}
```

- id 为内部关联键；作答、related/mutex 保存真实 id。code 是可空字符串，结果查询/DSL 使用它，不按 id 截取层级或补造 code。
- 问卷结构后端缓存 1800 秒，管理写入触发失效。填写与结果应用各自运行期间内存复用；刷新重新请求，不用 sessionStorage 旧题库兜底。个人答案草稿继续单独存 localStorage。
- 管理题目/选项接口支持 code；省略字段的局部更新保留原值，null/空白清空；非空题目须 5 位 ASCII 数字、选项须 7 位。格式错误返回 `422 INVALID_QUESTIONNAIRE_CODE`，同表非空编码重复返回 `409 QUESTIONNAIRE_CODE_CONFLICT`。整树导入先检查编码再替换原树；仅应用层检查，无新增数据库约束。
- 缺 code 的题目仍可填写，结果和管理页提示其统计配置缺失；高级搜索不提供无法生成编码条件的题目/选项。无自动编号、回填或重算。
- `queryQuestionnaire` 返回计数/文本，不附题干与选项文案。结果端以结构的 code 映射关联，已计票但某题无数据时补零；整届未计票保留 RESULT_NOT_COMPUTED 错误。
- 修改 code 或题目含义后须人工核对旧结果与链接；结构编辑不自动更新计票快照。结构不分届次，未新增历史定义版本。

### V2 答案提交与完成判断

`submitPaperV2(voteToken, answers)` 的成功返回仍为 Boolean，表示合法快照已保存，不表示整套已完成；answers 仍是全量题组行数组。请求可包含其他未完成问卷、可见未答题和空隐藏组；没有增加单独预校验接口或完成字段。

- 后端一次加载定义、建立真实 ID 索引，检查 ID/归属、选项列表及文本类型、重复行/选项和长度，然后评估题型、分支及互斥。
- Single 允许零/一项，Multiple 已选项必须属于同一 optionGroup；选择题不能携带非空文本，Input 不能携带选项。零选项/空文本表示未答，不等于非法。
- 当前题必须属于实际可见分支；隐藏题组只接受空状态。related 仅由同一问卷内当前可见且分支匹配的作答触发，隐藏组不能自触发。多来源命中同组时，当前题在命中集合内可保留；无触发则采用默认题或隐藏。
- 显式 mutex 按声明方向检查，不能同时提交互斥选项。后端不替用户删选项或换题后再保存。
- 用户作答非法沿用 GraphQL `errors[].extensions.error_kind=INVALID_PAPER_ANSWER`，human_readable_message 提供题组及原因，error_message 提供内部原因码；不会写入新行或 attempt，旧批次保持。
- 关联无法在有界轮数内稳定时返回 `QUESTIONNAIRE_CONFIGURATION_ERROR`，提示联系管理员，不能作为完成或成功保存。没有追加完整管理端题库治理或修改前端规则。
- 合法部分答案可保存；完成判定按同一评估中可见且合法已答的组计算。整体投票条件为至少存在一份必填、全部required完成，并至少完成一份category=extra且非required的选填问卷；缺少配置不视为完成。raw_paper 不再授予投票资格。
- 角色/音乐/组合提交由 `SubmitService._require_questionnaire` 对已保存答案执行闸门；前端按当前草稿的完成预判不表示已经保存。提名服务未调用同一闸门，不能宣称所有提交入口均受此服务端条件限制。
- 问卷未完成时，角色/音乐/组合 REST 返回 HTTP 422，`detail=QUESTIONNAIRE_NOT_COMPLETED`；GraphQL 返回同名 `errors[].extensions.error_kind` 及中文补填提示，均在写票前拒绝。前端现有提交错误提示展示 human_readable_message。
- 已知题组的错误分支/互斥/题型答案不计对应问卷完成；其他合法问卷独立计算。历史孤立组继续忽略；没有题目或题组的问卷不计完成。raw_paper 直接放行与空配置行数兜底已按[整体闸门计划](../superpowers/plans/2026-11-09-questionnaire-completion-gate.md)本地移除；不清库或自动重算快照，也不一并删除身份和 legacy 路由。

---

## 七、自动补全

### `POST /autocomplete/search`（唯一候选搜索入口；本地实现，未部署）

2026-11-08 第二阶段统一接口：原 `{query, limit} → {suggestions}` 名称建议契约被替换为下面的候选搜索契约。第一阶段临时的 `/autocomplete/candidates/search` 路径已移除，无别名路由。仓库内未发现旧建议接口业务调用方；配套前端必须与后端使用同一阶段的路径及契约。

完整路径为 `/api/v1/autocomplete/search`；投票前端通过现有 API_PREFIX 转发。

```json
// Request（vote_year 可省略，默认服务配置年度）
{ "category": "character", "query": " MLS ", "vote_year": 12 }
// Response（ID 仅为格式示例）
{ "category": "character", "query": "mls", "vote_year": 12, "candidate_ids": [123] }
```

- `category` 限 `character` / `music`；CP 成员按 character 搜索，不推荐 CP 组合。
- query 原始长度最多 64 个 Unicode 码点，去首尾空白并转小写；vote_year 为正整数。非法输入返回 422。
- 搜索当年候选的名称、各别名和主作品／专辑名；各字段独立匹配，不跨字段拼接，不含 name_jp 或音乐 include。
- 支持原文、全拼、声母简拼、多音字、混输、末音节前缀及既有模糊音规则；详细规则见 [设计](../superpowers/specs/2026-11-08-pinyin-candidate-search-design.md)。
- 返回全部匹配的 **candidate ID**，升序去重，无 limit；空查询返回当年该分类全部 ID，未知年度返回空数组。
- 前端将整数 ID 转字符串，与当前候选求交；个人已选项排除、CP 可重复成员、作品／类别筛选及日期排序留在前端。空查询不发请求；等待与失败有提示，过期响应不会覆盖新查询。
- 派生拼音语料和查询结果（含空数组）各缓存 60 秒；Redis 失败直接读数据库计算，数据库失败正常报错。现有写入失效及 `scope=autocomplete` 同时清理两类缓存。绕过正常失效时，两层 TTL 叠加最多约 120 秒旧结果。
- 无数据库 schema 或数据迁移。发布需配套前后端；从第一阶段切换时两端须同步到本阶段，回滚也须使用同一阶段的配套版本。

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

### 9.5 Voteable 管理 🆕（0019 起含资源配置）

#### `GET /admin/voteables`

```
Query: category=character|music（必填）, q?, page?, page_size?
```

```typescript
// Response 200:
{
  "items": [{
    "id": 48,
    "name": "博丽灵梦",
    "nameJp": "博麗　霊夢",
    "type": "old",
    "firstAppearance": "19970815",
    "oldId": null,
    "workId": 1, "workName": "东方灵异传", "workType": "old",
    "imageUrl": "https://asset.lilywhite.cc/...@100px.png",  // 🆕 0019
    "aliases": ["博麗霊夢", "红白"],                          // 🆕 回填
    // category=music 时额外返回：
    "musicUrl": "https://asset.lilywhite.cc/...@10s.mp3",
    "include": ["幺乐团的历史"]
  }],
  "total": 244
}
```

> 鉴权：`/admin/*` 路由级 `require_admin`，`X-Admin-Secret` 必填且受 `ADMIN_ALLOWED_IPS` 白名单约束（fail-closed）。

#### `POST /admin/voteables/{id}`

```typescript
// Request: 改 work 归属
{ "category": "character" | "music", "work_id": 1 | null }
// work_id=null 清空；work 不存在 → 409；voteable 不存在 → 404
// Response 200: { "ok": true }
```

#### `PUT /admin/voteables/{id}/resources` 🆕

部分更新：**只改请求里显式出现的字段**；空串 → 清空为 `NULL` / `[]`；
URL 仅允许 `http(s)` 且 ≤ 2048；character 忽略 `music_url` / `include`。

```typescript
// Request:
{
  "category": "character" | "music",
  "image_url"?: "https://..." | "",       // 角色立绘 / 曲目封面
  "music_url"?: "https://..." | "",       // music 专属：试听
  "include"?: ["专辑A", "专辑B"],          // music 专属：收录专辑（整体替换）
  "aliases"?: ["别名1", "别名2"]           // 整体替换（管理台编辑全量列表）
}
// Response 200: { "ok": true }
// 非法 URL → 422 INVALID_URL:{field}；不存在 → 404 NOT_FOUND
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
| `GET /admin/cache/stats` | 🆕 各 scope 当前缓存键数量（管理台「缓存」卡片） |
| `POST /admin/cache/flush` | 🆕 手动失效缓存，body `{"scope": "all"\|"vote_objects"\|"questionnaire"\|"autocomplete"\|"nominations"}`；返回 `{ok, scope, deleted, total}`；未知 scope → 422 |

### 9.9 缓存策略 🆕

全局公共读接口在 Redis 缓存，写入即失效 + TTL 兜底：

| 数据 | 键 | TTL | 写入失效触发 |
|---|---|---|---|
| 投票对象列表/详情 | `vote_objects:{year}:{category}[:{id}]` | 600s | work CRUD、voteable 导入/改归属/改资源、候选导入/改/删/合并 |
| 问卷结构 | `questionnaire:structure:{year}` | 1800s | 问卷/题组/问题/选项 CRUD、整树导入 |
| 拼音候选语料／结果 | `autocomplete:pinyin:v1:{year}:{category}:corpus` / `...:q:{sha256(query)}` | 各 60s | 与自动补全共用失效前缀 |
| 已通过提名 | `nominations:approved:{page}:{size}` | 60s | 提名 approve/reject |

- 失效用 `SCAN` 前缀删除（非 `KEYS`）；管理台可用 `POST /admin/cache/flush` 手动强刷。
- **不缓存**：带 `vote_token`/用户身份的读接口（`/submit/get-*`、`/voting-status/`、`/user/me` 等）。
- 结果页榜单是计票产物（`result:*`，由 `POST /admin/compute-results` 重建），不纳入手动刷缓存。

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
| `GET /vote-objects/{category}/{id}` | 🚧 | 字段 camelCase；0019 增 `imageUrl`/`aliases`（音乐含 `musicUrl`/`include`） |
| `PUT /admin/voteables/{id}/resources` | 🆕 0019 | 资源类字段编辑 |
| `GET /admin/cache/stats`、`POST /admin/cache/flush` | 🆕 | 缓存计数/手动失效 |
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
