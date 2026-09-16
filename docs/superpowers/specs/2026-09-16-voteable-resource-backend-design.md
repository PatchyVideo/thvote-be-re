# 投票对象资源 URL 后端化（0019）

> 状态：已实施
> 日期：2026-09-16
> 涉及：`thvote-be-re`（`zfq_dev`）+ `Touhou-Vote`（`zfq_dev_fe`）

## 背景

角色立绘 / 曲目封面 / 试听 URL 历史上存在前端 `packages/shared/data/character.ts`
与 `music.ts`，由前端 `voteObjectsDataSource` **按 `name`** 匹配挂到后端候选上；
结果页也各自按 name 查同一份静态表。问题：

- 后端不掌握资源，管理台无法配置；改图必须改前端代码并发版。
- 按 name 匹配脆弱：后端改名 → 前端静默回退默认图。
- 两份 244/612 条数据靠人工同步。

## 决策

| # | 决策 |
|---|---|
| D1 | 只迁移真正携带数据的字段（见下表）；`color`（全表常量 `#FC4328`）与 `title`（全空）不建列，前端用常量/空串 |
| D2 | `altnames` → `aliases`（JSON 列已存在，此前全空）必须回填，否则拼音/别名搜索退化 |
| D3 | 结果页复用现有 REST `vote-objects`（走 `/res-be` 代理），**不改 GraphQL schema** |
| D4 | 仓库内占位图（`defaultCharacterImage.png`/`defaultMusicImage.jpg`）保留作 UI 兜底 |
| D5 | DB 用 voteable 表 1:1 加列，不建通用资源表 |
| D6 | 后端基线 `origin/main`；前端 `zfq_dev_fe` 以 merge（非 rebase）同步 `origin/dev` |
| D7 | 复用 `/admin/*` 已有 router 级 `require_admin`（secret + IP 白名单，fail-closed） |
| D8 | 前端 sessionStorage 缓存加 5 分钟 TTL，规避“管理台改了不生效” |

## 迁移字段（实测 244 角色 / 612 曲目，名称 100% 匹配）

| 源字段 | 目标列 | 源非空 | 说明 |
|---|---|---|---|
| `character.image` | `voteable_character.image_url` | 164/244 | 空 → 前端占位图 |
| `character.altnames` | `voteable_character.aliases`（已存在） | 175/244 | 并集回填 |
| `music.image` | `voteable_music.image_url` | 605/612 | |
| `music.music` | `voteable_music.music_url` | 612/612 | |
| `music.include` | `voteable_music.include`（JSON） | 231/612 | |

不迁移：`color`（唯一值 `#FC4328`）、`title`（全空）、`date`（与 `first_appearance`
100% 一致）、`origname`（与 `name_jp` 一致）、`kind`（由 `type`+`workTypes` 推导）、
`work/album`（由 `work_id`+`filterMeta` 推导）、`id`(8-hex，仅死代码用)、
`reason/honmei`（全空/全 false）。

## 实现

### 后端
- `alembic/versions/0019_voteable_resources.py`：新增 `image_url`(×2)、`music_url`、`include`（幂等、Postgres-only）。
- `src/db_model/voteable.py`：同步列。
- `src/apps/vote_objects/dao.py`：列表 / 详情下发 `imageUrl`、`aliases`（音乐另 `musicUrl`、`include`）。
- `src/apps/admin/router.py` + `schemas.py`：`GET /admin/voteables` 补资源字段；新增
  `PUT /admin/voteables/{id}/resources`（部分更新、URL 校验、写后清缓存）。
- `scripts/voteable_resources.json`：一次性迁移工件（由前端静态表导出，含来源 commit）。
- `scripts/import_voteable_resources.py`：按 name 导入（默认只填空值、dry-run；`--apply/--yes/--overwrite`）。

### 前端
- 新增 `packages/shared/api/voteObjects.ts`（类型 + fetch + index，vote/result 共用）。
- `packages/shared/model/character.ts` / `music.ts`：抽出 class 定义（数据数组删除）。
- 重写 `packages/vote/src/common/lib/voteObjectsDataSource.ts`：直接映射后端字段，删除按 name 匹配；
  缓存加 5 分钟 TTL。
- 结果页新增 `packages/result/src/lib/voteObjectResources.ts`；5 处静态表调用改为后端索引。
- 删除 `packages/shared/data/character.ts`、`music.ts`、`vote/common/lib/getNickName.ts`、
  `result/lib/getIDtoName.ts`、`result/pages/Test.vue`（及其路由）。

### 管理台
- 新增 `admin-ui/src/views/VoteableResourcesView.vue` + `api/voteables.ts` + 路由/导航。
- 顺带修复 origin/main 上已无法通过 `vue-tsc` 的 `WorksView.vue`（对不上现有 composables/DataTable API）。
- 产物 `pnpm build` 提交到 `src/admin_ui/`。

## 发布顺序

1. 后端先上（只增列/字段，旧前端不受影响）；
2. 对测试库执行导入脚本；
3. 校验公共接口返回资源；
4. 前端再上（新前端强依赖后端新字段）。

## 验收

- 后端：新增/修改测试全绿（`test_vote_objects`、`test_admin_voteables`、迁移工件单测）。
- E2E（测试环境）：投票页图片来自 CDN、别名搜索命中、曲目 include 正常、结果页有图、
  管理台改图后刷新生效、非法 URL 422、无 secret 403。

## 遗留

- 80 个角色 / 7 首曲目源数据本身无图 → 保持占位图，待管理台补录。
- `射命丸文` 的 DB `work`（东方花映塚）不在源 `work[]`（东方文花帖（书籍））内，属既有数据差异，另记。
- 旧单文件管理台（`src/admin_ui_legacy/`）仍在，承载 CP 投票 / 计算榜单 / 问卷嵌套编辑等未迁移工具，本次不下线。
