# Block 1 安全 — 后端(含管理端)设计稿

> 创建日期：2026-06-08
> 最后更新：2026-06-08
> 配套前端设计稿：[`2026-06-08-security-frontend-design.md`](./2026-06-08-security-frontend-design.md)

## 一、背景与目标

需求文档要求"防止未满足条件的用户提交投票"与对二创提名做合法性校验。当前后端存在三处真·安全缺口(前端校验可被绕过):

1. **投票门禁缺失** —— `vote_token` 只看"已验证手机/邮箱 + 投票时间窗",不校验问卷是否完成。前端虽有路由守卫,但可绕过直接调 GraphQL 投票。
2. **二创提名零内容校验** —— 当前 `validate_dojin` 只校验字符串长度,无域名白名单、无发布时间窗、无去重、无人工审核。前端裸提交,明确依赖后端校验。
3. **无提名时间窗** —— 后端只有投票窗,没有独立的提名开放窗口。

本块解决这三项。**问卷门禁本期做"弱校验"(已提交问卷即放行),Block 3 问卷迁后端后升级为"校验必填题已答"。**

## 二、关键决策(brainstorm 结论)

| 决策 | 选定 |
|---|---|
| 提名内容审核 | **人工审核队列 + 自动域名/时间校验**;R18/版权/营销号由 admin 人工审核 |
| 投票门禁判定 | **分两步**:本块弱校验(检测到该 vote_id 已提交问卷即放行);Block 3 升级 |
| 提名去重依据 | **scraper 的 `udid`** 作为作品规范化唯一 id |

## 三、配置项(Settings 新增,均可选)

```
NOMINATION_START_ISO        # 提名开放窗口开始(ISO8601)
NOMINATION_END_ISO          # 提名开放窗口结束
WORK_ELIGIBLE_START_ISO     # 可提名作品的合格发布时间下限(可选,留空=不限)
WORK_ELIGIBLE_END_ISO       # 可提名作品的合格发布时间上限
DOJIN_DOMAIN_ALLOWLIST      # 允许提名的域名,逗号分隔(如 "bilibili.com,youtube.com,...")
```

- 未配置 `NOMINATION_START/END` 时,提名端点返回 `503 NOMINATION_NOT_CONFIGURED`(与 MongoDB 同步端点同样的"未配置即拒"策略)。
- `DOJIN_DOMAIN_ALLOWLIST` 留空时视为"不限域名"(仅做时间 + 去重 + 人工审核)。

通过 Nacos `thvote_be` 下发,与现有 `vote_start_iso` 等同等对待。

## 四、数据模型

### 新表 `dojin_nomination`(migration 0007)

每条提名一行(替代 `raw_dojin` 的不可审核 blob;`raw_dojin` 保留作原始留档,不动)。

```python
class DojinNomination(Base):
    __tablename__ = "dojin_nomination"
    id              # Integer PK autoincrement
    vote_id         # String(255) index — 提名人 user id
    udid            # String(255) nullable index — scraper 规范化作品 id(去重依据)
    url             # Text
    title           # String(512)
    author          # String(512)
    dojin_type      # String(32)        — '' / MUSIC / VIDEO / DRAWING / SOFTWARE / ARTICLE / CRAFT / OTHER
    image_url       # Text nullable
    reason          # Text nullable
    publish_date    # DateTime(timezone=True) nullable — scraper 抓到的作品发布时间
    status          # String(16) default "pending"  — pending / approved / rejected
    reject_reason   # String(512) nullable
    reviewed_by     # String(64) nullable — admin 标识
    reviewed_at     # DateTime(timezone=True) nullable
    created_at      # DateTime(timezone=True) server_default now()
    __table_args__  # UniqueConstraint(vote_id, udid) 防同人重复提名同作品(udid 为 NULL 时不约束)
```

> `UniqueConstraint(vote_id, udid)`:NULL udid(scraper 失败)不触发唯一约束,允许多条待人工处理。

## 五、二创提名提交流程(改造 submit dojin)

```
POST 提名(GraphQL submitDojin / REST 对应端点)
  1. 校验 vote_token 有效(现有)
  2. 校验当前时间 ∈ [NOMINATION_START, NOMINATION_END] → 否则 422 NOMINATION_CLOSED
  3. 逐条提名 item:
     a. 域名校验:解析 item.url 域名;若 DOJIN_DOMAIN_ALLOWLIST 非空且域名不在其中 → rejected(reason="域名不允许")
     b. 调 ScraperService.scrape_url(item.url)(带超时):
        - 成功 → 取 udid + ptime(publish_date)
        - 失败/超时 → udid=None, publish_date=None(仍入库,待人工)
     c. 发布时间校验:若配置了 WORK_ELIGIBLE 范围 且 publish_date 已知 且 不在范围内 → rejected(reason="作品发布时间不符")
     d. 去重:若该 vote_id 已存在同 udid 的提名(udid 非空)→ skipped(reason="重复提名")
     e. 通过 a/c 的 → 入 dojin_nomination,status=pending
  4. 返回逐条结果:{ accepted: [...], rejected: [{index, reason}], skipped: [{index, reason}] }
```

- **逐条处理**:部分通过部分拒,不整单失败。
- scraper 同步调用 + 超时保护(如 5s/条);失败不阻断,降级为 udid=None 待人工。
- 仍写一份 `raw_dojin`(原始留档),与现有行为兼容。

## 六、管理端审核(随后端,管理端新「提名审核」Tab)

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/admin/nominations` | query: `status`(pending/approved/rejected/all)、`page`、`page_size`;返回分页列表 |
| `PATCH` | `/admin/nominations/{id}/approve` | 置 approved + reviewed_by/at |
| `PATCH` | `/admin/nominations/{id}/reject` | body: `{reason}`;置 rejected + reject_reason |

- 全部 `X-Admin-Secret` 鉴权。
- 列表项含:id、vote_id、title、author、url、udid、publish_date、status、reject_reason、created_at。
- 管理端 UI(白色主题,仿候选项 Tab):筛选状态 + 列表 + 行内 通过/驳回。

## 七、公开查询(已通过提名)

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/nominations/approved` | query: `page`、`page_size`;返回 status=approved 的提名,**按 udid 去重聚合**,带 `nomination_count`(被多少人提名) |

> 需求文档写"供组合部门投票页面使用"存疑(二创≠组合)。本端点按"已通过二创提名列表"实现;具体消费方等前端确认(见前端设计稿 §待确认)。

## 八、投票门禁(弱校验)

`submit` 服务在写**角色/音乐/CP**投票之前(paper/dojin 本身不门禁):

```
查 questionnaire 表(或 raw_paper)是否存在该 vote_id 的记录:
  无 → 422 QUESTIONNAIRE_NOT_COMPLETED
  有 → 放行
```

- 实现位置:`src/apps/submit/service.py` 各 submit 方法入口,或统一在 vote_token 解析后加一道 `_require_questionnaire(vote_id)`。
- 弱校验定义:"该用户存在任意问卷提交记录"。Block 3 升级为"所有必填题已答"。
- **作品投票(Block 2)上线后,作品投票同样套用此门禁。**

## 九、复用的现成资产

- **scraper**:`src/apps/scraper` 的 `ScraperService.scrape_url(url)` 已返回 `udid` + `ptime` + 解析域名 → 自动去重和发布时间校验几乎现成。
- **管理端**:审核 Tab 仿现有候选项 Tab(白色主题 + 列表 + 行内操作 + 弹窗)。
- **rate limit / audit log**:沿用现有中间件。
- **Settings/Nacos**:新配置项走现有下发链路。

## 十、错误码

| 场景 | 返回 |
|---|---|
| 提名时未配置提名窗 | `503 NOMINATION_NOT_CONFIGURED` |
| 提名时不在提名窗内 | `422 NOMINATION_CLOSED` |
| 投票时未完成问卷 | `422 QUESTIONNAIRE_NOT_COMPLETED` |
| 审核 id 不存在 | `404 NOMINATION_NOT_FOUND` |
| 单条提名被拒 | 不报错,进 response 的 `rejected[]` 带 reason |

## 十一、测试策略

| 层 | 覆盖 |
|---|---|
| unit | 域名白名单解析、时间窗判定、发布时间范围判定、udid 去重逻辑(纯函数,mock scraper) |
| unit | 门禁:有/无问卷记录的放行/拦截 |
| integration | submit dojin 全流程(mock ScraperService):全通过 / 部分拒 / scraper 失败降级 / 重复跳过 |
| integration | 审核 approve/reject 改状态;公开 approved 列表去重聚合 |
| integration | 投票门禁拦截(无问卷→422;有问卷→放行) |
| contract | `/admin/nominations*` 无 secret→403;`/nominations/approved` shape;submit dojin 新响应 shape |

## 十二、文件变更一览(后端 + 管理端)

| 文件 | 操作 |
|---|---|
| `src/common/config.py` | 加 5 个提名/作品配置字段 |
| `src/db_model/dojin_nomination.py` | 新建 |
| `src/db_model/__init__.py` | 导出 DojinNomination |
| `alembic/versions/0007_dojin_nomination.py` | 新建 migration |
| `src/apps/submit/nomination_service.py` | 新建(域名/时间/去重 纯逻辑 + 提交编排) |
| `src/apps/submit/service.py` | 改 dojin 提交走 nomination_service;角色/音乐/CP 加问卷门禁 |
| `src/apps/submit/dao.py` | 加 dojin_nomination 读写 |
| `src/apps/submit/schemas.py` | 加提名响应(逐条结果)模型 |
| `src/api/graphql/resolvers/submit_bridge.py` | submitDojin 返回逐条结果 |
| `src/apps/admin/router.py` `service.py` `schemas.py` | 加 nominations 审核端点 |
| `src/apps/result/router.py`(或新 nominations 路由) | 加 `/nominations/approved` |
| `src/admin_ui/index.html` | 加「提名审核」Tab |
| `tests/{unit,integration,contract}/...` | 新建对应测试 |

## 十三、关联

- 前端设计稿:[`2026-06-08-security-frontend-design.md`](./2026-06-08-security-frontend-design.md)
- BACKLOG:新增 B-037
