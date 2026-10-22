# 结果快照时间范围

状态：已实现，2026-10-22；尚未发布或重算线上结果。

## 计票与读取

保留现有流程：先人工完成反作弊处置，再调用管理端计票。新增时间信息不会自动触发计票。

每次 `ComputeService.compute_all` 与榜单一起在 Redis pipeline 中写入 `result:{vote_year}:timeline`：

| 字段 | 含义 |
|---|---|
| `vote_start` | 本次计算使用的投票开始时间 |
| `vote_end` | 本次计算使用的投票结束时间 |
| `statistics_end` | 计票启动时刻与投票结束时间的较早值；最早为投票开始时间 |
| `generated_at` | 本次结果计算完成、准备写入 Redis 的时间 |

时间保存为带时区的 ISO 8601 字符串。计算完成后修改配置不会改变既有快照日期。小时桶从投票开始时刻计为 `hrs=0`，范围采用 `[vote_start, statistics_end)`；不足一小时的末桶保留。开始前试算的显示范围为空。高级搜索重算使用主榜快照的时间边界；旧快照缺时间元信息时保留既有配置分桶行为，前端不显示未经核实的时间轴。

## GraphQL

新增可空字段，既有字段语义不变：

```graphql
query ResultDates($voteYear: Int) {
  queryResultTimeline(voteYear: $voteYear) {
    voteStart
    voteEnd
    statisticsEnd
    generatedAt
  }
}
```

返回类型为 `ResultTimeline`，四个字段均为非空 `DateTimeUtc`。届次沿用现有结果查询的解析与回落规则。该字段始终读取主榜时间元信息，筛选及所选实体不缩短横轴。未生成结果或旧快照没有时间信息时返回 `null`，不使用当前配置伪造历史日期。

前端在原趋势查询中同时请求此字段，六处趋势页统一按北京时间显示日期。空小时补零，累计曲线延续上一小时，改票负增量保留。无时间元信息显示“暂无趋势时间信息”，有时间范围但无票显示“暂无投票数据”。

## 发布与兼容

1. 先发布后端，确保 schema 包含 `queryResultTimeline`。
2. 前端基于新 schema 执行 `pnpm result:codegen` 后构建发布。生成产物沿用仓库现有忽略规则。
3. 新前端可读取旧结果，排名不变，但旧快照缺时间范围，趋势暂不显示；在人工反作弊与计票安排允许时重算，时间信息随新结果生成。

无数据库 schema、迁移或配置变更。回滚前端不影响新后端；回滚后端前先回滚前端，避免新查询在旧 schema 上校验失败。不清理、不自动重建既有结果缓存。
