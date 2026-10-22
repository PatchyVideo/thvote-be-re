# 后端公共读接口 Redis 缓存（vote-objects / 问卷 / 自动补全 / 提名）

> 状态：已实施
> 日期：2026-09-17

## 背景

`vote-objects` 每次请求都做 `candidate_* JOIN voteable_* LEFT JOIN work` 并序列化
100~255KB JSON；问卷结构每次多表查询；自动补全每次两条 ILIKE。项目里 Redis 一直
存在（限流/会话/计票锁/结果产物），但这几个公共读接口完全没用上。
`_clear_vote_objects_cache()` 早在 admin 里存在，却没有任何代码写 `vote_objects:*`，
是没接完的死代码。

## 决策

| 项 | 决策 |
|---|---|
| 缓存范围 | **仅全局公共数据**；带 `vote_token`/用户身份的读接口一律不缓存（共享缓存会串号） |
| 结果页 | 已是 Redis 计票产物（`result:*`，compute 重建），不纳入 |
| 管理端读 | 不缓存（低收益 + 隐私 + 实时性） |
| 失效策略 | **写入即失效 + TTL 兜底** |
| 失效实现 | `SCAN` 游标前缀删除，不用 `KEYS`（避免阻塞 Redis 单线程） |
| 失败处理 | 缓存 fail-open：Redis 异常时记 warning，读 miss、写跳过，绝不影响请求 |

## 键与 TTL

| 数据 | 键 | TTL | 失效触发 |
|---|---|---|---|
| 角色/曲目列表 | `vote_objects:{year}:characters|music` | 600s | work CRUD、voteable 导入/改归属/改资源、候选导入/改/删/合并（本次补齐） |
| 投票对象详情 | `vote_objects:detail:{category}:{id}` | 600s | 同上 |
| 问卷结构 | `questionnaire:structure:{year}` | 1800s | 问卷/题组/问题/选项 CRUD、整树导入 |
| 自动补全 | `autocomplete:{year}:{limit}:{q}` | 60s | 候选/作品变更 |
| 已通过提名 | `nominations:approved:{page}:{size}` | 60s | 提名 approve/reject |

## 实现

- 新增 `src/common/cache.py`：`cache_get_raw/cache_set_raw/cache_get_json/cache_set_json`
  + `invalidate_prefix`（SCAN）；全部 fail-open。
- `vote_objects/router.py`：命中直接返回缓存字节，`GZipMiddleware` 仍压缩（不双压）。
- `questionnaire/router.py`、`autocomplete/router.py`、`submit/router.py`（仅公开提名列表）。
- 失效：`admin/router.py` 的 `_clear_vote_objects_cache` 改为 SCAN 并同时清
  `autocomplete:`；补齐候选导入/改/删/合并/拆分；提名 approve/reject 清 `nominations:`；
  问卷 admin 全部 13 个写端点清 `questionnaire:`。
- 管理台：`GET /admin/cache/stats` + `POST /admin/cache/flush`（scope 白名单，
  杜绝任意 pattern），Dashboard 增加「缓存」卡片（计数 + 单项/一键刷新）。

## 效果

- `vote-objects` 命中时省掉 2 次 DB join（实测 RDS 往返 102~258ms）与 JSON 序列化，
  服务端处理降到 Redis GET（内网 ~1ms 级）。
- 结果页榜单不动；管理台写入后缓存立即失效，不会「配置了不生效」。

## 明确不缓存

`/submit/get-*`、`/voting-status/`、`/voting-statistics/`、`/user/me`、`/user/token-status`、
SSO 回调、所有写端点、管理端列表/日志/导出。

## 遗留

- `result:*` 由 `POST /admin/compute-results` 重建；未纳入手动刷缓存（避免刷完榜单 404）。
- 结果页前端仍有 5 分钟 sessionStorage「先渲染后台 revalidate」缓存；两层缓存互不冲突。
