# 管理后台 Vue 重写 + 安全监控 设计（B-049）

> 状态：**设计稿，待评审**（2026-07-17）。
> 目标：把现有单文件 HTML 后台（`src/admin_ui/index.html`，1115 行，StaticFiles 挂 `/admin-ui`）重写为 Vue 3 后台，并加入投票期用的**安全监控**：流量概览、IP/设备聚类、可疑账号名单、可过滤投票浏览器、单账号钻取与处置。
> 基调（用户明确）：**面向少数管理员自己看，尽量轻量、便于快速迭代**。
> 数据基础：反刷票采集层已就绪（`raw_*.{user_ip, additional_fingreprint(设备), fill_duration_ms, attempt, client_env{ua,tz,screen,lang}}`、`user.{register_ip_address, register_device_id, register_date, SSO}`，见 B-044/045/046）。

## 一、范围与决策（评审结论）

| 决策点 | 结论 |
|---|---|
| 范围 | 全量 Vue 重写整个后台 + 加安全监控 |
| 时间 | 充裕,不赶投票期 |
| 监控能力 | ①流量概览 ②IP/设备分组聚类 ③可疑账号评分名单 ④**可过滤投票浏览器(分页表格,核心视图)** ⑤单账号钻取 |
| 聚类算法 | **精确共享分组**(按 IP/设备各自 GROUP BY),不上并查集连通分量(以后要更强再加) |
| 评分 | **固定加权**(权重集中在一处常量,好改),只排序供人工复核、**不自动处置** |
| 鉴权 | **X-Admin-Secret 强制必填**(未配→全 403,治 B-042 裸奔) + **IP 白名单**(Nacos `ADMIN_ALLOWED_IPS`,CIDR 感知) |
| 部署 | Vue 源码在**后端仓库** `admin-ui/`,Dockerfile 多阶段(node 构建→dist)→ StaticFiles 挂 `/admin-ui`;与后端同源、同一部署 |
| 计算/新鲜度 | 按需实时 SQL + Redis 轻缓存 30-60s;聚合视图缓存,投票表格单条索引查询可不缓存 |
| 处置动作 | 标记/备注(新)、封号(现有 ban/unban)、作废具体投票(新);**不做整簇批量**(易误伤) |
| API 风格 | 沿用现有 REST admin router(`/api/v1/admin/*` + `X-Admin-Secret`),不引入 GraphQL |

## 二、架构

```
浏览器(管理员) ──(同源)──► 后端 :backend
   /admin-ui         StaticFiles(Vue dist)
   /api/v1/admin/*   REST + X-Admin-Secret + IP 白名单
```

- 前端 Vue 3 + Vite,源码 `admin-ui/`;后端 Dockerfile 加 node 构建阶段产出 `dist/` 复制进 Python 镜像,现有 StaticFiles 继续服务。
- 前后端同源→无跨域、无需额外 CORS。
- 轻量:不上 Pinia,用 composables;一个轻 API 客户端(fetch 带 `X-Admin-Secret`);一个通用「分页+过滤表格」组件复用。

## 三、鉴权（顺带治 B-042）

- `_check_admin_secret` 反转为 **fail-closed**:`admin_secret` 未配置 → 所有 `/api/v1/admin/*` 一律 403(现状是未配则放行,方向错了)。
- 新增 IP 白名单:Nacos `ADMIN_ALLOWED_IPS`(JSON 字符串数组,IP 或 CIDR;复用 B-044 的 `_peer_is_trusted_proxy` + `get_client_ip` 取真实 IP)。空 → 不限(向后兼容);配了 → 非白名单来源 403。
- 前端:登录页输 secret 存 sessionStorage,每次请求带 `X-Admin-Secret` 头;401/403 跳回登录。
- **局限(刻意)**:单密钥无逐人身份/审计("谁封了谁"不记);IP 白名单对动态 IP 管理员需维护。

## 四、安全监控后端（只读端点）

新增 REST 端点(`/api/v1/admin/*`,X-Admin-Secret + IP 白名单)。计算纯 SQL,聚合结果 Redis 缓存 30-60s(缓存键含过滤参数)。

### 4.1 投票浏览器（核心视图）`GET /admin/votes`
分页表格,跨 `raw_*` 查询。**默认选定一个类别**(避免 5 表 UNION);过滤器:
- `category`(character/music/cp/paper/dojin;`all` 才 UNION)
- `vote_id`、`user_ip`(精确或网段前缀)、`device_id`
- `fill_duration_ms` 区间(如 `<2000`=太快)、`attempt`(=1 首投 / >1 改票)
- `client_env`:`ua_contains`、`missing_ua`、`tz`
- `created_at` 区间;`invalidated` 是否
- 排序 + `page`/`page_size`;返回 `total`(COUNT,毫秒级)
- 每行:vote_id、category、created_at、user_ip、device_id、fill_duration_ms、attempt、client_env、payload 摘要、invalidated、review_status

### 4.2 概览仪表盘 `GET /admin/monitor/overview`
注册数/投票数按小时或天分桶趋势、总量、分类别计数、异常峰提醒(简单阈值)。

### 4.3 IP/设备分组 `GET /admin/monitor/groups?by=ip|device&min_accounts=N`
`SELECT key, count(distinct vote_id) ... GROUP BY key HAVING count>=N ORDER BY count DESC`。列"每个 IP/设备下有多少不同账号",降序;点进 = 组内账号明细。

### 4.4 可疑账号名单 `GET /admin/monitor/suspects`
每账号一个可疑分,固定加权(权重集中在 `admin/monitor/scoring.py` 常量,便于迭代),命中原因随行返回,降序分页。规则示例(初版):
- 首投耗时 `<2000ms`(+3)、`client_env` 缺失或无 `ua`(+3)、`ua` 含 headless/脚本特征(+3)
- 注册→首投 `<5s`(+2)、所在 IP 分组规模 `≥N`(+2)、payload 与他人完全雷同(+3)
- **只排序供人工复核,不自动处置**(延续"取证不拦截"原则)。

### 4.5 单账号钻取 `GET /admin/monitor/account/{vote_id}`
该账号各类别投票(全套取证字段)+ 注册信息(IP/设备/时间/SSO)+ 它出现在哪些 IP/设备分组 + `review_status/note`。

## 五、处置动作

- **标记/备注(新)** `PATCH /admin/monitor/account/{vote_id}/review` `{status, note}` → upsert `voter_review`。
- **封号(现有)** `PATCH /admin/users/{id}/ban` / `/unban`(`removed=true/false`)。
- **作废具体投票(新)** `PATCH /admin/monitor/vote/{category}/{row_id}/invalidate` / `/restore` → `raw_*.invalidated`(可逆,不删数据)。

> **⚠️ 作废/封号"生效于排名"这一步不在本设计范围内,依赖 B-050。**
> 2026-07-17 勘探发现后端有**两套并行投票存储**:**路径 A `raw_*`**(前端 GraphQL 提交的真实票,提交/回读/CSV/统计全走这)与**路径 B `character/music/cp/questionnaire`**(死表:无写入方、0 行,其写入模块 `vote_data` 已于 2026-07-17 删除)。而计票 `ComputeDAO` 偏偏只读**路径 B** → 当前 `compute-results` 产出**空排名**,且计票**从不读 `user.removed`** → 封号对排名毫无影响。把计票改读 `raw_*` 并尊重 `removed`/`invalidated` 是一项**独立大重写(BACKLOG B-050)**,已单独立项、本设计不做。
>
> 因此本后台对"作废/封号"的职责收敛为**如实记录 + 复核动作**:`raw_*.invalidated` 打标、`user.removed` 封号、`voter_review` 备注,均落库可查、可逆。**B-050 计票重写时读 `raw_*` 会一并尊重这些标记**,届时"重算即生效"。前端在处置后提示"该处置已记录;计票重写(B-050)上线后生效于排名",不误导管理员以为立刻改了排名。

## 六、数据模型改动（migration 0014「admin 监控支持」，幂等）

- `raw_*` ×6:`ADD COLUMN IF NOT EXISTS invalidated BOOLEAN NOT NULL DEFAULT false`
- 索引:`raw_*.user_ip` ×6、`user.register_date` ×1(`CREATE INDEX IF NOT EXISTS`)
- 新表 `voter_review`:`user_id`(PK,String)、`status`(String,默认 `''`)、`note`(Text,默认 `''`)、`updated_at`(TIMESTAMPTZ server_default now())
- Postgres-only(`ADD COLUMN/INDEX IF NOT EXISTS`);sqlite 测试库走 create_all,沿用现有约定。

## 七、性能（几万投票人量级）

- 每张 `raw_*` 每人每类一行 → 每表约 5 万行、5 类合计约 25 万行;user 约 5 万。**Postgres 小表量级**:GROUP BY/过滤/分页均亚秒。
- 保障项:①上述索引 ②聚合视图缓存 ③投票表格默认单类别避免 UNION ④返回 total、不做深翻页。
- 唯一略慢:`client_env` JSON 的 `ua_contains` 是顺序扫(5 万行几十毫秒,可接受;将来可加 `client_env->>'ua'` 函数索引)。
- **逃生舱(现在不做)**:数据真涨到实时算吃力,则把评分/聚类切成后台定时预算物化(前向兼容,不返工)。

## 八、前端页面

Vue 3 + Vite,轻量(无 Pinia,composables + 通用分页表格组件)。
- 登录页(secret→sessionStorage + 路由守卫)
- 概览仪表盘 / 投票浏览器(核心) / IP·设备分组 / 可疑名单 / 账号钻取(含处置按钮 + 二次确认)
- 旧工具迁移:用户、候选、提名审核、问卷编辑器、同步、计票/定榜
- **排期(plan 层)**:先 骨架+登录+监控页(优先/新价值),再逐个搬旧 HTML 工具进 Vue。spec 覆盖全量,plan 分阶段。

## 九、测试

- **后端(正式)**:监控端点(过滤/分组/评分/分页/缓存)、动作(review upsert / invalidate 打标 / ban)、鉴权(无 secret / 非白名单 IP → 403)。用现有 sqlite+fakeredis 夹具。
  - 注:"invalidate/ban **影响排名**"的测试属 **B-050**(计票重写),本设计只测"标记如实落库 + 可逆",不测排名效果。
- **前端(轻量)**:内部工具,CI 构建通过 + 人工验收为主,不铺自动化前端测试。

## 十、风险与开放项

- 后端仓库加 node 构建阶段:Dockerfile 多阶段 + CI 需装 node/pnpm;首次接入注意构建时长。
- IP 白名单误配可能把管理员自己挡在外面 → 支持"空=不限"兜底 + 文档写清。
- ~~compute 排除逻辑要覆盖所有计票 SELECT~~ → **移交 B-050**:计票读死表、封号无效,是独立大重写;本后台只负责如实记录处置标记,排名生效随 B-050 落地(见 §五 callout)。
- 全量重写工作量大,靠 plan 分阶段控制;监控优先。
