# 新版答卷管理

状态：2026-11-10 本地实现，纳入本轮提交，未部署或执行云端迁移。管理台入口为“答卷管理”，独立于“问卷配置”。配套[设计](../superpowers/specs/2026-11-10-candidate-import-and-answer-admin-design.md)、[实施计划](../superpowers/plans/2026-11-10-candidate-import-and-answer-admin.md)。

## 数据与职责

答案保存在 `paper_answer`；一次提交是 `(vote_id, vote_year, attempt)` 对应的整套快照，不按问卷分别组成批次。旧 `attempt=NULL` 在管理接口中表示为 0，新提交从 1 递增。

管理接口使用原有 `require_admin`，要求 `X-Admin-Secret` 并应用已有 IP 白名单。router 处理请求和 404，service 解析题库及完成情况，DAO 查询最新批次、分页及更新整批状态。新 router 在 REST v1 组合入口注册，没有新增依赖。

## 接口

下列路径均以 `/api/v1` 开头。

### GET /admin/questionnaire-submissions

查询参数：`vote_year`（省略取服务端配置）、`vote_id`（完整匹配）、`invalidated`（可省略）、`page=1`、`page_size=50`（上限 200）。先选择最新批次，再筛选状态、排序和分页，不会将旧有效批次当作最新数据返回。

响应 `{items, total, page, page_size}`。每条包含：

- `vote_id`、`vote_year`、`attempt`、`created_at`、`row_count`。
- `invalidated`：批次是否作废；同批任意行作废即视为整批作废。
- `is_latest`：列表恒为 true，详情历史批次按实际判断。
- `completed`：原始填写内容是否满足整体完成规则，与作废状态独立。
- `eligible`：必须是最新批次、未作废且填写完成。这仅表示问卷条件，不代替账号、时间窗口等其他投票限制。
- `progress`：各问卷的 `id/key/title/required/completed`，复用既有后端完成判断。

### GET /admin/questionnaire-submissions/{vote_year}/{vote_id}

返回 `{vote_id, vote_year, batches}`，批次从新到旧排列。每批含列表字段及 `questionnaires`：

```json
{
  "id": 1,
  "title": "必填问卷",
  "answers": [{
    "id": 21,
    "group_id": 10,
    "active_question_id": 100,
    "question_content": "喜欢的季节",
    "question_type": "Single",
    "selected_options": [{"id": 1000, "content": "春天"}],
    "input_text": null,
    "missing_references": []
  }]
}
```

题文按当前定义解析，并非历史题库快照。已不存在或归属变化的引用保留 ID、选项和输入，不猜测名称。不存在的问卷标题、题目文字或选项文字返回 null，并提供引用问题提示。没有该届答卷返回 404。

### PATCH /admin/questionnaire-submissions/{vote_year}/{vote_id}/{attempt}

输入 `{"invalidated":true}` 或 `{"invalidated":false}`，必须是真正的布尔值。更新该账号、该届次、该次提交的全部答案行，不更改其他批次。成功返回：

```json
{"affected_rows":24,"invalidated":true,"detail":"已更新整次答卷状态；已有统计和筛选缓存需要重新计票后更新"}
```

目标批次不存在返回 404；`attempt=0` 管理旧 NULL 批次。操作不删除答案，不封禁账号，不连带作废角色、音乐或 CP 提交。

## 有效性与统计

- 最新批次作废时，服务端问卷门禁立即不通过，不回退旧批次。恢复后重新按完成规则判断；用户可以修改重交，新批次默认有效。
- 用户答卷回填仍返回原始最新内容，浏览器草稿不自动清空。回填有内容不等于满足服务端投票条件。
- 当前问卷统计、逐问卷完成集合及高级搜索的数据加载排除最新作废账号。趋势也排除该账号整段历史；最新有效时，单独作废的历史批次不进入趋势。
- 普通结果与已缓存的高级筛选依然使用现有计票快照/版本；作废、恢复后须手动重新计票刷新。没有新增自动重算或缓存恢复机制。
- 管理概览 `stats.submissions.paper` 统计本届保存过答案的账号数，包括未完成或作废答卷；它是提交人数，不是有效人数或投票资格。账号详情的 `vote_submitted.paper` 同样表示本届是否保存过 V2 答案。
- 设备/IP 通用监控已移除旧 paper 类别，V2 缺少这些采集字段，不进入相应聚类和可疑评分。账号取证页提供新版答卷入口。

## 迁移与回退

新增 Alembic `0023`，父版本 `0022`：仅新增 `paper_answer.invalidated BOOLEAN NOT NULL DEFAULT false`。现有行默认有效，不改写答案或 attempt，也不删除 `raw_paper`。

部署本版代码前必须先执行该迁移；本轮新增迁移文件并纳入提交，未在云端执行。临时 PostgreSQL 16 已验证升级、降级、再升级及原答案保留，并验证最新批次查询和整批状态更新。

回退时先回退应用代码；新列可以暂时保留。旧代码不会执行新版作废口径。如执行降级至 0022，会丢失全部作废标记，原始答案仍在；需要保留处置状态时应先备份，不能把降级视为无损回退。

## 剩余 raw_paper 退出工作

旧提交与回填、旧统计/登录状态的间接查询、CSV 导出、同步脚本及 ORM/物理表仍待后续退出。本轮没有删除登录接口、旧 API 或表。用户详情仍复用旧 `has_submit` 获取其他类别状态，但展示的 paper 状态已由本届 V2 答案覆盖，不使用其旧 paper 返回值。
